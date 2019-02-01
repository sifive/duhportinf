import os
import sys
import numpy as np
import json5
import argparse
from .busdef import BusDef
from ._optimize import map_ports_to_bus, get_mapping_fcost
from ._grouper import get_port_grouper
from . import busdef
from . import util

# FIXME remove
import time

def get_ports_from_json5(comp_json5_path):
    with open(comp_json5_path) as fin:
        block = json5.load(fin)
    ports = []
    for name, pw in block['definitions']['ports'].items():
        try:
            w, d = np.abs(pw), np.sign(pw)
        except Exception as e:
            #print('Warning', (name, pw), 'not correctly parsed')
            w, d = None, np.sign(-1) if pw[0] == '-' else np.sign(1)
        ports.append( (name, w, d) )
    return ports

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
    print('loading {} bus specs'.format(len(spec_paths)))
    for spec_path in spec_paths:
        #print('  - loading ', spec_path)
        bus_defs.extend(BusDef.bus_defs_from_spec(spec_path))                

    print('  - done, loaded {} bus defs with {} required and {} optional ports '.format(
        len(bus_defs),
        sum([bd.num_req_ports for bd in bus_defs]),
        sum([bd.num_opt_ports for bd in bus_defs]),
    ))
    return bus_defs

def get_bus_matches(ports, bus_defs):
    # perform hierarchical clustering over ports to get tree grouping
    print('hierarchically clustering ports and selecting port groups')
    pg, Z, wire_names = get_port_grouper(ports)
    print('  - done')
    
    # pass over all port groups and compute fcost to prioritize potential
    # bus pairings to optimize
    # NOTE need to keep track of node id in port group tree to pass back
    # costs and figure out optimal port groupings to expose
    pg_bus_pairings = []
    nid_cost_map = {}

    print('initial bus pairing with port groups')
    for nid, port_group in pg.get_initial_port_groups():
        # for each port group, only pair the 5 bus defs with the lowest fcost
        pg_bus_defs = list(sorted(
            [(get_mapping_fcost(port_group, bus_def), bus_def) for bus_def in bus_defs],
            key=lambda x:x[0].value,
        ))[:5]
        l_fcost = pg_bus_defs[0][0]
        pg_bus_pairings.append((nid, l_fcost, port_group, pg_bus_defs))
        nid_cost_map[nid] = l_fcost
    
    # prune port groups in which the lowest fcost is too high to warrant
    # more expensive bus matching
    # NOTE don't bother trying to match a particular port group if all the
    # ports in that group potentially have a better assignment based on
    # fcost
    optimal_nids = pg.get_optimal_groups(nid_cost_map)
    opt_pg_bus_pairings = list(sorted(filter(
        lambda x : (
            # must be on an optimal path for some port
            x[0] in optimal_nids and
            # must have less than 5 direction mismatches in the best case
            # from fcost computation
            x[1].dc < 5 and
            # at least 4 ports in a group
            len(x[2]) > 3
        ),
        pg_bus_pairings,
    ), key=lambda x: x[1]))
    #print('initial pg_bus_pairings', len(pg_bus_pairings))
    #print('opt pg_bus_pairings', len(opt_pg_bus_pairings))

    # perform bus mappings for chosen subset to determine lowest cost bus
    # mapping for each port group
    pg_bus_mappings = []
    nid_cost_map = {}
    stime = time.time()
    print('bus mapping')
    ptot = sum([len(bd) for _, _, _, bd in opt_pg_bus_pairings])
    plen = min(ptot, 50)
    pcurr = 0
    util.progress_bar(pcurr, ptot, length=plen)
    for i, (nid, l_fcost, port_group, bus_defs) in enumerate(opt_pg_bus_pairings):
        #print('pairing: {}, lcost:{}, port group size: {}'.format(
        #    i, l_fcost, len(port_group)))
        #print('      ', list(sorted(port_group))[:5])
        bus_mappings = []
        for fcost, bus_def in bus_defs:
            cost, mapping, sideband_ports, match_cost_func = \
                map_ports_to_bus(port_group, bus_def)
            bus_mappings.append((
                cost,
                fcost,
                mapping,
                sideband_ports,
                match_cost_func,
                bus_def,
            ))
            util.progress_bar(pcurr+1, ptot, length=plen)
            pcurr += 1

        bus_mappings.sort(key=lambda x: x[0])
        lcost = bus_mappings[0][0]
        nid_cost_map[nid] = lcost
    
        pg_bus_mappings.append((
            nid,
            lcost,
            port_group,
            bus_mappings,
        ))

    # choose optimal port groups to expose to the user
    optimal_nids = pg.get_optimal_groups(nid_cost_map)
    opt_pg_bus_mappings = list(sorted(filter(
        lambda x : x[0] in optimal_nids,
        pg_bus_mappings,
    ), key=lambda x: x[1]))

    # return pairings of <port_group, bus_mapping>
    return list(map(lambda x: x[2:], opt_pg_bus_mappings))

#--------------------------------------------------------------------------
# main
#--------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-b', '--duh-bus',
        default=None,
        required=True,
        help='duh-bus root direcotry that contains bus specifications',
    )
    parser.add_argument(
        '-o', '--output',
        default=sys.stdout,
        required=False,
        help='output path to busprop.json with proposed bus mappings for select groups of ports',
    )
    parser.add_argument(
        'component_json5',
        help='input component.json5 with port list of top-level module',
    
    )
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    args = parser.parse_args()

    assert os.path.isdir(args.duh_bus), '{} not a directory'.format(args.duh_bus)
    assert os.path.isfile(args.component_json5), '{} does not exist'.format(args.component_json5)
    if args.output != sys.stdout and os.path.dirname(args.output) != '':
        dn = os.path.dirname(args.output)
        assert os.path.isdir(dn), 'output directory {} does not exist'.format(dn)

    all_ports = get_ports_from_json5(args.component_json5)
    bus_defs = load_bus_defs(args.duh_bus)
    pg_bus_mappings = get_bus_matches(all_ports, bus_defs)
    util.dump_json_bus_candidates(args.output, pg_bus_mappings)

if __name__ == '__main__':
    main()
    
