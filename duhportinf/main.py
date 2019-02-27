#! /usr/bin/env python3

import os
import sys
import numpy as np
import shutil
import json5
import argparse
import subprocess
import logging
from .busdef import BusDef
from ._optimize import map_ports_to_bus, get_mapping_fcost, MatchCost
from ._grouper import get_port_grouper
from . import busdef
from . import util

def get_bus_defs(spec_path):
    assert os.path.isfile(spec_path)
    assert BusDef.is_spec_bus_def(spec_path), \
        "{} does not describe a proper bus abstractionDefinition in JSON5".format(spec_path)
    
    return BusDef.bus_defs_from_spec(spec_path)

def load_bus_defs(rootdir):
    spec_paths = []
    for root, dirs, fnames in os.walk(rootdir):
        for fname in fnames:             
            spec_path = os.path.join(root, fname)
            if BusDef.is_spec_bus_def(spec_path):     
                spec_paths.append(spec_path)

    bus_defs = []                
    logging.info('loading {} bus specs'.format(len(spec_paths)))
    for spec_path in spec_paths:
        bus_defs.extend(BusDef.bus_defs_from_spec(spec_path))                

    logging.info('  - done, loaded {} bus defs with {} required and {} optional ports '.format(
        len(bus_defs),
        sum([bd.num_req_ports for bd in bus_defs]),
        sum([bd.num_opt_ports for bd in bus_defs]),
    ))
    return bus_defs


def _get_lfcost_bus_defs(interface, bus_defs, penalize_umap=True):
    return list(sorted(
        [(
            get_mapping_fcost(interface, bus_def, penalize_umap), 
            bus_def,
        ) for bus_def in bus_defs],
        key=lambda x:x[0].value,
    ))

def _get_bus_pairings(pg, bus_defs):
    # pass over all initial port groups and compute fcost to prioritize
    # potential bus pairings to optimize
    # NOTE need to keep track of node id in port group tree to pass back
    # costs and figure out optimal port groupings to expose
    i_bus_pairings = []
    nid_cost_map = {}

    for nid, interface in pg.get_initial_interfaces():
        # for each port group, only pair the 5 bus defs with the lowest fcost
        i_bus_defs = _get_lfcost_bus_defs(interface, bus_defs)[:5]
        l_fcost = i_bus_defs[0][0]
        i_bus_pairings.append((nid, l_fcost, interface, i_bus_defs))
        nid_cost_map[nid] = l_fcost
    
    # prune port groups in which the lowest fcost is too high to warrant
    # more expensive bus matching 
    # NOTE don't bother trying to match a particular port group if all the
    # ports in that group potentially have a better assignment within
    # different groups based on fcost
    optimal_nids = pg.get_optimal_nids(nid_cost_map)
    opt_i_bus_pairings = list(sorted(filter(
        # must be on an optimal path for some port
        lambda x : x[0] in optimal_nids,
        i_bus_pairings,
    ), key=lambda x: x[1]))
    #print('optimal_nids', len(optimal_nids))
    #print('initial i_bus_pairings', len(i_bus_pairings))
    #print('opt i_bus_pairings', len(opt_i_bus_pairings))

    return opt_i_bus_pairings
    
def _get_initial_bus_matches(pg, i_bus_pairings):
    
    # perform bus mappings for chosen subset to determine lowest cost bus
    # mapping for each port group
    i_bus_mappings = []
    nid_cost_map = {}
    ptot = sum([len(bd) for _, _, _, bd in i_bus_pairings])
    plen = min(ptot, 50)
    pcurr = 0
    util.progress_bar(pcurr, ptot, length=plen)
    for i, (nid, l_fcost, interface, bus_defs) in enumerate(i_bus_pairings):
        bus_mappings = []
        for fcost, bus_def in bus_defs:
            bm = map_ports_to_bus(interface, bus_def)
            bm.fcost = fcost
            bus_mappings.append(bm)
            util.progress_bar(pcurr+1, ptot, length=plen)
            pcurr += 1

        bus_mappings.sort(key=lambda bm: bm.cost)
        lcost = bus_mappings[0].cost
        nid_cost_map[nid] = lcost
    
        i_bus_mappings.append((
            nid,
            lcost,
            interface,
            bus_mappings,
        ))

    optimal_nids = pg.get_optimal_nids(nid_cost_map)
    opt_i_bus_mappings = list(sorted(filter(
        lambda x : x[0] in optimal_nids,
        i_bus_mappings,
    ), key=lambda x: x[1]))

    # append interfaces for all ports that are not included in an
    # interface that is mapped to a described bus interface
    covered_nids = optimal_nids
    for nid, interface in pg.get_remaining_interfaces(covered_nids):
        opt_i_bus_mappings.append((
            nid,
            MatchCost.zero(),
            interface, 
            [],
        ))

    return opt_i_bus_mappings

def _map_residual(interface, _src_bm, bus_defs):
    """
    map flat port group against bus_defs and assign sideband signals
    optimally amongst the new bus_mappings and the input src bus mapping

    NOTE not used right now
    NOTE residual must be in the form of Interface (presumeably with some
    ports removed from the source)
    """
    src_bm = BusMapping.duplicate(_src_bm)
    i_bus_defs = _get_lfcost_bus_defs(
        interface,
        bus_defs,
        penalize_umap=False,
    )[:30]
    bus_mappings = list(sorted([
        map_ports_to_bus(interface, bus_def, penalize_umap=False) 
        for fcost, bus_def in i_bus_defs
    ], key=lambda bm: bm.cost))
    
    # greedily accept new bus mappings in which bus_def.req_ports have not
    # already been accepted
    assn_ports = set()
    sel_bus_mappings = [src_bm]
    for bm in bus_mappings:
        mapped_ports = set(bm.mapping.keys())
        # skip if any mapped ports have already been assigned
        if len(mapped_ports & assn_ports) > 0:
            continue
        sel_bus_mappings.append(bm)
        assn_ports |= mapped_ports
    
    def get_port_cost(port, bm):
        umap = (port in bm.sbm and bm.sbm[port] == None)
        sb_map = (port in bm.sbm and bm.sbm[port] != None)
        prim_map = (port in bm.m)
        return (
            not prim_map,
            umap,
            MatchCost.zero() if not sb_map else bm.mc_func(port, bm.sbm[port]),
            MatchCost.zero() if not prim_map else bm.mc_func(port, bm.m[port]),
        )
    
    # assign src sideband ports to best possible destination
    # if none of the selected bus mappings map it is a primary port, pick
    # the sideband mapping with the lowest cost
    port_bmcosts = defaultdict(list)
    mapping_ports = interface.get_ports_to_map()
    for port in mapping_ports:
        port_bmcosts[port].append(
            (get_port_cost(port, src_bm), src_bm)
        )
    for bm in sel_bus_mappings:
        for port in mapping_ports:
            port_bmcosts[port].append(
                (get_port_cost(port, bm), bm)
            )
    for port in mapping_ports:
        _, sel_bm = min(port_bmcosts[port], key=lambda x: x[0])
        # remove port from sideband designation in the rest of the bus mappings
        for bm in sel_bus_mappings:
            if bm != sel_bm:
                assert port not in bm.mapping, \
                    "port can only be assigned to one primary mapping"
                del bm.sbm[port]
                
    return list(sorted(sel_bus_mappings, key=lambda bm: bm.cost))


def get_bus_matches(ports, bus_defs):
    logging.info('hierarchically clustering ports and selecting port groups')
    pg, Z, wire_names = get_port_grouper(ports)
    logging.info('  - done')

    logging.info('initial bus pairing with port groups')
    opt_i_bus_pairings = _get_bus_pairings(pg, bus_defs)
    logging.info('  - done')
    
    logging.info('bus mapping')
    opt_i_bus_mappings = _get_initial_bus_matches(pg, opt_i_bus_pairings)
    logging.info('  - done')

    # return pairings of <interface, bus_mapping>
    return list(map(lambda x: x[2:], opt_i_bus_mappings))

#--------------------------------------------------------------------------
# main
#--------------------------------------------------------------------------
def main():
    logging.basicConfig(format='%(message)s', level=logging.DEBUG)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-b', '--duh-bus',
        default=None,
        required=False,
        help='duh-bus root directory that contains bus specifications.  will default to $(duh-bus-which), which requires duh-bus to be installed',)
    parser.add_argument(
        '-o', '--output',
        default=sys.stdout,
        required=False,
        help='output path to busprop.json with proposed bus mappings for select groups of ports',
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

    # try to invoke duh-bus-which to load bus specs if not specified with -b
    if args.duh_bus == None:
        if shutil.which('duh-bus-which'):
            duh_bus_path = subprocess.check_output('duh-bus-which').strip()
            duh_bus_path = duh_bus_path.decode('ascii')
            assert os.path.isdir(duh_bus_path), \
                "duh-bus not properly installed, please use -b/--duh-bus"
        else:
            logging.error('error: duh-bus not installed and -b/--duh-bus not specified')
            sys.exit(1)
    else:
        assert os.path.isdir(args.duh_bus), '{} not a directory'.format(args.duh_bus)
        duh_bus_path = args.duh_bus

    with open(args.component_json5) as fin:
        block = json5.load(fin)
    all_ports = util.format_ports(block['definitions']['ports'])
    bus_defs = load_bus_defs(duh_bus_path)
    i_bus_mappings = get_bus_matches(all_ports, bus_defs)
    util.dump_json_bus_candidates(
        args.output,
        args.component_json5,
        i_bus_mappings,
        args.debug,
    )

if __name__ == '__main__':
    main()
    
