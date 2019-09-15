#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

from __future__ import print_function
import subprocess
import json
import os
import zipfile
import shutil
import argparse
import six
import pkgutil
import uuid
import tempfile
import sys
from six.moves import urllib
from abc import abstractmethod, ABCMeta
from distutils.dir_util import copy_tree
from configparser import ConfigParser
try:
    from tempfile import TemporaryDirectory
except ImportError:
    from backports.tempfile import TemporaryDirectory

__version__ = '0.0.2'


@six.add_metaclass(ABCMeta)
class Generator(object):
    def init(self, config):
        self._config = config
        self._name = config['general']['name']
        self._executable = config['general']['executable']

        conan_build_info = os.path.join(tempfile.gettempdir(), "conanbuildinfo.json")
        if not os.path.isfile(conan_build_info):
            self._run(["conan", "install", ".", "-g", "json", "-if", tempfile.gettempdir()])

        data = json.load(open(conan_build_info))
        self._bin_dirs = set()
        self._lib_dirs = set()

        self._dep_lib_dirs = dict()
        self._dep_bin_dirs = dict()

        for dep in data["dependencies"]:
            root = dep["rootpath"]
            lib_paths = dep["lib_paths"]
            bin_paths = dep["bin_paths"]

            for lib_path in lib_paths:
                if os.listdir(lib_path):
                    lib_dir = os.path.relpath(lib_path, root)
                    self._lib_dirs.add(lib_dir)
                    self._dep_bin_dirs[lib_path] = lib_dir
            for bin_path in bin_paths:
                if os.listdir(bin_path):
                    bin_dir = os.path.relpath(bin_path, root)
                    self._bin_dirs.add(bin_dir)
                    self._dep_bin_dirs[bin_path] = bin_dir

    @abstractmethod
    def run(self):
        raise NotImplementedException('"run" method is abstract!')

    def _download(self, url, name):
        temp_name = path = os.path.join(tempfile.gettempdir(), name)
        if not os.path.isfile(temp_name):
            print("downloading %s into %s" % (url, temp_name))
            urllib.request.urlretrieve(url, temp_name)
        return temp_name

    def _chmod_plus_x(self, name):
        if os.name == 'posix':
            os.chmod(name, os.stat(name).st_mode | 0o111)

    def _run(self, command):
        print('running command: "%s"' % ' '.join(command))
        return subprocess.check_call(command)

    def _create_entry_point(self, filename, varname):
        directory = os.path.dirname(filename)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)

        def _format_dirs(dirs):
            return ":".join(["%s/%s" % (varname, d) for d in dirs])

        path = _format_dirs(self._bin_dirs)
        ld_library_path = _format_dirs(self._lib_dirs)
        exe = varname + "/" + self._executable

        content = """#!/usr/bin/env bash
set -ex
export PATH=$PATH:{path}
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:{ld_library_path}
pushd $(dirname {exe})
$(basename {exe})
popd
""".format(path=path,
           ld_library_path=ld_library_path,
           exe=exe)

        print(content)

        self._save(filename, content)
        self._chmod_plus_x(filename)

    def _save(self, filename, content):
        flags = "w" if isinstance(content, six.string_types) else "wb"
        with open(filename, flags) as f:
            f.write(content)


class DirectoryGenerator(Generator):
    def run(self):
        self.invoke(self._name)

    def invoke(self, destination):
        if not os.path.isdir(destination):
            os.makedirs(destination)
        for src_lib_dir, dst_bin_dir in self._dep_lib_dirs.items():
            copy_tree(src_lib_dir, os.path.join(destination, dst_lib_dir))
        for src_bin_dir, dst_bin_dir in self._dep_bin_dirs.items():
            copy_tree(src_bin_dir, os.path.join(destination, dst_bin_dir))
        self._run(["conan", "imports", "-if", tempfile.gettempdir(), "-imf", destination, "."])
        shutil.copy(self._executable, os.path.join(destination, self._executable))
        self._chmod_plus_x(os.path.join(destination, self._executable))


class ArchiveGenerator(DirectoryGenerator):
    def __init__(self, archive_format):
        super(ArchiveGenerator, self).__init__()
        self.archive_format = archive_format

    def run(self):
        with TemporaryDirectory() as temp_folder:
            super(ArchiveGenerator, self).invoke(temp_folder)
            shutil.make_archive(self._name, self.archive_format, temp_folder)


class MakeSelfGenerator(DirectoryGenerator):
    def run(self):
        with TemporaryDirectory() as temp_folder:
            super(MakeSelfGenerator, self).invoke(temp_folder)
            makeself = os.path.join(tempfile.gettempdir(), "makeself", "makeself.sh")
            if not os.path.isfile(makeself):
                filename = self._download("https://github.com/megastep/makeself/releases/download/release-2.4.0/makeself-2.4.0.run", "makeself.run")
                self._chmod_plus_x(filename)
                self._run([filename, "--target", os.path.join(tempfile.gettempdir(), "makeself")])
                os.unlink(filename)
            self._create_entry_point(os.path.join(temp_folder, "conan-entrypoint.sh"), "$PWD")
            self._run([makeself, temp_folder, self._name+ ".run", "conan-generated makeself.sh", "./conan-entrypoint.sh"])


class AppImageGenerator(DirectoryGenerator):
    def __init__(self):
        self._app_image_kit_version = 12
        super(AppImageGenerator, self).__init__()

    def run(self):
        with TemporaryDirectory() as temp_folder:
            super(AppImageGenerator, self).invoke(temp_folder)
            arch = "x86_64"
            apprun = "AppRun-%s" % arch
            appimagetool = "appimagetool-%s.AppImage" % arch
            base_url = "https://github.com/AppImage/AppImageKit/releases/download/%s/" % self._app_image_kit_version
            apprun = self._download(base_url + apprun, apprun)
            appimagetool = self._download(base_url + appimagetool, appimagetool)
            self._chmod_plus_x(appimagetool)
            self._create_entry_point(os.path.join(temp_folder, "usr", "bin", self._name), "$APPDIR")
            shutil.copy(apprun, os.path.join(temp_folder, "AppRun"))
            self._chmod_plus_x(os.path.join(temp_folder, "AppRun"))
            content = """[Desktop Entry]
Name={name}
Exec={name}
Icon={name}
Type=Application
Categories=Utility;
""".format(name=self._name)
            self._save(os.path.join(temp_folder, "%s.desktop" % self._name), content)
            icon = pkgutil.get_data(__name__, 'conan.png')
            self._save(os.path.join(temp_folder, "%s.png" % self._name), icon)
            self._run([appimagetool, temp_folder])


class FlatPakGenerator(DirectoryGenerator):
    def run(self):
        with TemporaryDirectory() as temp_folder:
            super(FlatPakGenerator, self).invoke(temp_folder)

            app_id = "org.flatpak.%s" % self._name
            manifest = {
                "app-id": app_id,
                "runtime": "org.freedesktop.Platform",
                "runtime-version": "18.08",
                "sdk": "org.freedesktop.Sdk",
                "command": "conan-entrypoint.sh",
                "modules": [
                    {
                        "name": self._name,
                        "buildsystem": "simple",
                        "build-commands": ["install -D conan-entrypoint.sh /app/bin/conan-entrypoint.sh"],
                        "sources": [
                            {
                                "type": "file",
                                "path": "conan-entrypoint.sh"
                            }
                        ]
                    }
                ]
            }
            sources = []
            build_commands = []
            for root, _, filenames in os.walk(temp_folder):
                for filename in filenames:
                    filepath = os.path.join(root, filename)
                    unique_name = str(uuid.uuid4())
                    source = {
                        "type": "file",
                        "path": filepath,
                        "dest-filename": unique_name
                    }
                    build_command = "install -D %s /app/%s" % (unique_name, os.path.relpath(filepath, temp_folder))
                    sources.append(source)
                    build_commands.append(build_command)

            manifest["modules"][0]["sources"].extend(sources)
            manifest["modules"][0]["build-commands"].extend(build_commands)

            manifest_file = os.path.join(tempfile.gettempdir(), "%s.json" % app_id)
            self._save(manifest_file, json.dumps(manifest))

            entry_point = os.path.join(tempfile.gettempdir(), "conan-entrypoint.sh")
            self._create_entry_point(entry_point, "/app")
            self._chmod_plus_x(entry_point)

            with TemporaryDirectory() as build_folder:
                self._run(["flatpak-builder", build_folder, manifest_file])
                self._run(["flatpak-builder", "--repo=repo", "--force-clean", build_folder, manifest_file])
                try:
                    self._run(["flatpak", "--user", "remote-add", "--no-gpg-verify", "conan-repo", "repo"])
                except subprocess.CalledProcessError:
                    pass
                self._run(["flatpak", "--user", "install", "-y", "--reinstall", "conan-repo", app_id])


def main(args):
    generators = {"dir": DirectoryGenerator(),
                  "zip": ArchiveGenerator(archive_format="zip"),
                  "tar": ArchiveGenerator(archive_format="tar"),
                  "tgz": ArchiveGenerator(archive_format="gztar"),
                  "tbz": ArchiveGenerator(archive_format="bztar"),
                  "txz": ArchiveGenerator(archive_format="xztar"),
                  "makeself": MakeSelfGenerator(),
                  "appimage": AppImageGenerator(),
                  "flatpak": FlatPakGenerator()}

    parser = argparse.ArgumentParser(description='conan deploy tool')
    parser.add_argument('-g', '--generator', type=str, action='append', dest='generators', required=True, help='deploy generator to use', choices=generators.keys())
    parser.add_argument('-v', '--version', action='version', version=__version__)
    parser.add_argument('-c', '--config', type=str, default='conan-deploy.conf', help='configuration file')
    args = parser.parse_args(args)

    conan_build_info = os.path.join(tempfile.gettempdir(), "conanbuildinfo.json")
    if os.path.isfile(conan_build_info):
        os.unlink(conan_build_info)

    if not os.path.isfile(args.config):
        print("couldn't open config file %s" % args.config)
        sys.exit(1)

    config = ConfigParser(allow_no_value=True)
    config.optionxform = str
    config.read(args.config)

    for generator in args.generators:
        print("running generator %s" % generator)
        generators[generator].init(config)
        generators[generator].run()
