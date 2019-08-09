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
from six.moves import urllib
from abc import abstractmethod, ABCMeta
from distutils.dir_util import copy_tree

try:
    from backports import tempfile
except ImportError:
    import tempfile

__version__ = '0.0.1'


@six.add_metaclass(ABCMeta)
class Generator(object):
    def __init__(self):
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
    def run(self, destination):
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

    def _create_entrypoint(self, directory, varname):
        def _format_dirs(dirs):
            return ":".join(["$%s/%s" % (varname, d) for d in dirs])

        path = _format_dirs(self._bin_dirs)
        ld_library_path = _format_dirs(self._lib_dirs)
        exe = "bin/camera"

        contents = """#!/usr/bin/env bash
set -ex
export PATH=$PATH:{path}
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:{ld_library_path}
pushd $(dirname {exe})
{exe}
popd
""".format(path=path,
           ld_library_path=ld_library_path,
           exe=exe)

        filename = os.path.join(directory, "conan-entrypoint.sh")
        with open(filename, "w") as f:
            f.write(contents)
        self._chmod_plus_x(filename)


class DirectoryGenerator(Generator):
    def run(self, destination):
        if not os.path.isdir(destination):
            os.makedirs(destination)
        for src_lib_dir, dst_bin_dir in self._dep_lib_dirs.items():
            copy_tree(src_lib_dir, os.path.join(destination, dst_lib_dir))
        for src_bin_dir, dst_bin_dir in self._dep_bin_dirs.items():
            copy_tree(src_bin_dir, os.path.join(destination, dst_bin_dir))


class ArchiveGenerator(DirectoryGenerator):
    def __init__(self, archive_format):
        super(ArchiveGenerator, self).__init__()
        self.archive_format = archive_format

    def run(self, destination):
        with tempfile.TemporaryDirectory() as temp_folder:
            super(ArchiveGenerator, self).run(temp_folder)
            shutil.make_archive(destination, self.archive_format, temp_folder)


class MakeSelfGenerator(DirectoryGenerator):
    def run(self, destination):
        with tempfile.TemporaryDirectory() as temp_folder:
            super(MakeSelfGenerator, self).run(temp_folder)
            makeself = os.path.join(tempfile.gettempdir(), "makeself", "makeself.sh")
            if not os.path.isfile(makeself):
                filename = self._download("https://github.com/megastep/makeself/releases/download/release-2.4.0/makeself-2.4.0.run", "makeself.run")
                self._chmod_plus_x(filename)
                self._run([filename, "--target", os.path.join(tempfile.gettempdir(), "makeself")])
                os.unlink(filename)
            self._create_entrypoint(temp_folder, "USER_PWD")
            self._run([makeself, temp_folder, destination + ".run", "conan-generated makeself.sh", "./conan-entrypoint.sh"])


def main(args):
    conan_build_info = os.path.join(tempfile.gettempdir(), "conanbuildinfo.json")
    if os.path.isfile(conan_build_info):
        os.unlink(conan_build_info)

    generators = {"dir": DirectoryGenerator(),
                  "zip": ArchiveGenerator(archive_format="zip"),
                  "tar": ArchiveGenerator(archive_format="tar"),
                  "tgz": ArchiveGenerator(archive_format="gztar"),
                  "tbz": ArchiveGenerator(archive_format="bztar"),
                  "makeself": MakeSelfGenerator()}

    parser = argparse.ArgumentParser(description='conan deploy tool')
    parser.add_argument('-n', '--name', type=str, default='conan_deploy', help='name of the output file')
    parser.add_argument('-g', '--generator', type=str, action='append', dest='generators', required=True, help='deploy generator to use', choices=generators.keys())
    args = parser.parse_args(args)

    for generator in args.generators:
        print("running generator %s" % generator)
        generators[generator].run(args.name)
