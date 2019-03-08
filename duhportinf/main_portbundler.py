#! /usr/bin/env python3

import os
import sys
import numpy as np
import shutil
import json5
import argparse
import subprocess
import logging
from itertools import chain
from collections import defaultdict
from . import util
from ._bundle import BundleTree

#--------------------------------------------------------------------------
# main
#--------------------------------------------------------------------------
def main():
    logging.basicConfig(format='%(message)s', level=logging.DEBUG)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-o', '--output',
        default=sys.stdout,
        required=False,
        help='output path to component.json with bundles for all ports not already specified in a bus interface',
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='dump debug format',
    
    )
    parser.add_argument(
        'component_json5',
        help='input component.json5 with port list of top-level module',
    
    )
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    args = parser.parse_args()

    assert os.path.isfile(args.component_json5), '{} does not exist'.format(args.component_json5)
    if args.output != sys.stdout and os.path.dirname(args.output) != '':
        dn = os.path.dirname(args.output)
        assert os.path.isdir(dn), 'output directory {} does not exist'.format(dn)

    unassn_ports = util.get_unassigned_ports(args.component_json5)

    if len(unassn_ports) == 0:
        logging.info('no unassigned ports to bundle')
        sys.exit(0)

    logging.info('bundling {} unassigned ports'.format(len(unassn_ports)))
    bt = BundleTree(unassn_ports)
    util.dump_json_bundles(
        args.output,
        args.component_json5,
        bt.get_bundles(),
        args.debug,
    )
    logging.info('  - done')

if __name__ == '__main__':
    main()
    
