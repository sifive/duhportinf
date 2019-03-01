#! /usr/bin/env python3
import os
import sys

# prepend directory ../pylib, which contains both locally installed python
# deps and also the duhportinf pyhton package, to PYTHONPATH
rootdir = os.path.abspath(
    os.path.join(os.path.dirname(os.path.realpath(__file__)), '..')
)
pylib = os.path.join(rootdir, 'pylib')
assert os.path.isdir(pylib), \
    "something wrong in npm setup, `npm link` or `npm install` not properly run"
sys.path = [pylib] + sys.path

import duhportinf
duhportinf.main_portbundler.main()

