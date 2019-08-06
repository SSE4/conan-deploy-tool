#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

import sys
if sys.version_info.major == 3:
    from conan_deploy_tool import conan_deploy_tool
else:
    import conan_deploy_tool


def run():
    conan_deploy_tool.main(sys.argv[1:])


if __name__ == '__main__':
    run()
