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
from distutils.dir_util import copy_tree

try:
    from backports import tempfile
except ImportError:
    import tempfile

__version__ = '0.0.1'


class Generator(object):
    pass


class DirectoryGenerator(Generator):
    def __init__(self):
        super(DirectoryGenerator, self).__init__()

    def run(self, destination):

        if not os.path.isdir(destination):
            os.makedirs(destination)
        with tempfile.TemporaryDirectory() as install_folder:
            subprocess.check_call(["conan", "install", ".", "-g", "json", "-if", install_folder])
            conan_build_info = os.path.join(install_folder, "conanbuildinfo.json")
            data = json.load(open(conan_build_info))

            bin_dirs = set()
            lib_dirs = set()

            for dep in data["dependencies"]:
                root = dep["rootpath"]
                lib_paths = dep["lib_paths"]
                bin_paths = dep["bin_paths"]
                print(dep["name"], bin_paths, lib_paths)

                for lib_path in lib_paths:
                    if os.listdir(lib_path):
                        lib_dir = os.path.relpath(lib_path, root)
                        lib_dirs.add(lib_dir)
                        copy_tree(lib_path, os.path.join(destination, lib_dir))
                for bin_path in bin_paths:
                    if os.listdir(bin_path):
                        bin_dir = os.path.relpath(bin_path, root)
                        bin_dirs.add(bin_dir)
                        copy_tree(bin_path, os.path.join(destination, bin_dir))

            print(bin_dirs, lib_dirs)


class ArchiveGenerator(DirectoryGenerator):
    def __init__(self, archive_format):
        self.archive_format = archive_format
        self.name = archive_format

    def run(self, destination):
        with tempfile.TemporaryDirectory() as temp_folder:
            super(ArchiveGenerator, self).run(temp_folder)
            shutil.make_archive(destination, self.archive_format, temp_folder)


def main(args):
    generators = {"dir": DirectoryGenerator(),
                  "zip": ArchiveGenerator(archive_format="zip"),
                  "tar": ArchiveGenerator(archive_format="tar"),
                  "tgz": ArchiveGenerator(archive_format="gztar"),
                  "tbz": ArchiveGenerator(archive_format="bztar")}

    parser = argparse.ArgumentParser(description='conan deploy tool')
    parser.add_argument('-n', '--name', type=str, default='conan_deploy', help='name of the output file')
    parser.add_argument('-g', '--generator', type=str, action='append', dest='generators', required=True, help='deploy generator to use', choices=generators.keys())
    args = parser.parse_args(args)

    for generator in args.generators:
        print("running generator %s" % generator)
        generators[generator].run(args.name)
