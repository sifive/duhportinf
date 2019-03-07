#! /usr/bin/env python3

import os
import sys
import numpy as np
import shutil
import json5
from jsonref import JsonRef
import argparse
import subprocess
import logging
from itertools import chain
from collections import defaultdict
from . import util
from ._bundle import BundleTree

def _get_unassigned_ports(all_ports, bus_interfaces):
    def get_portnames(interface):
        atkey = 'abstractionTypes'
        pmkey = 'portMaps'
        vkey = 'viewRef'
        pns_ = util.flatten([
            at[pmkey].values() for at in interface[atkey] 
                if at[vkey] == 'RTLview'
        ])
        nv_pns = [p for p in pns_ if type(p) == str]
        # flatten vectors
        v_pns = util.flatten([p for p in pns_ if type(p) != str])
        return set(chain(v_pns, nv_pns))

    portname_sets = [
        set(get_portnames(interface)) for interface in bus_interfaces
    ]
    seen = set()
    dups = set()
    for pns in portname_sets:
        dups |= (pns & seen)
        seen |= pns
    if len(dups) > 0:
        logger.error('ports illegally belong to multiple bus interfaces:{}'.format(list(dups)))

    assn_portnames = set(seen)
    unassn_ports = [p for p in all_ports if p[0] not in assn_portnames]
    return unassn_ports

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

    with open(args.component_json5) as fin:
        block = json5.load(fin)
        block = JsonRef.replace_refs(block)
    all_ports = util.format_ports(block['component']['model']['ports'])
    bus_interfaces = block['component']['busInterfaces']
    unassn_ports = _get_unassigned_ports(all_ports, bus_interfaces)
    bt = BundleTree(unassn_ports)
    util.dump_json_bundles(
        args.output,
        args.component_json5,
        bt.get_bundles(),
        args.debug,
    )

if __name__ == '__main__':
    main()
    
