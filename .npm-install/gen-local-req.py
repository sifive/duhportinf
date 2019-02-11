#! /usr/bin/env python3
import sys
import subprocess
from distutils.version import LooseVersion as version

assert len(sys.argv) == 3
inreq_path, outreq_path = sys.argv[1:]

def libv(s):
    s = str(s).strip()
    return s.split('==') if '==' in s else s.split('>=')

txt = subprocess.check_output(['pip3', 'list', '--format=freeze'])
txt = txt.decode('ascii', 'ignore')
installed = {}
for line in txt.split():
    lib, v = libv(line)
    installed[lib] = version(v)
with open(inreq_path) as fin, \
     open(outreq_path, 'w') as fout:
    for line in fin:
        rlib, rv = libv(line)
        if (
            rlib not in installed or
            version(rv) > installed[rlib]
        ):
            fout.write(line)

