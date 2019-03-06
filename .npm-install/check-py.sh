#! /usr/bin/env bash

PYTHON=python3
PIP=pip3

if ! ${PYTHON} --version > /dev/null ; then 
    echo "python3 not properly set up"
    exit 1
fi
if ! ${PIP} --version > /dev/null ; then
    echo "pip3 (for python3) not properly set up"; 
    exit 2
fi
