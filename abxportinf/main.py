import os
import numpy as np
import json5
from .busdef import BusDef
from ._optimize import map_ports_to_bus, get_mapping_fcost
from ._grouper import get_port_grouper
from . import busdef

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
            print('Warning', (name, pw), 'not correctly parsed')
            w, d = None, np.sign(-1) if pw[0] == '-' else np.sign(1)
        ports.append( (name, w, d) )
    return ports

def get_bus_defs(spec_path):
    assert os.path.isfile(spec_path)
    assert BusDef.is_spec_bus_def(spec_path), \
        "{} does not describe a proper bus abstractionDefinition in JSON5".format(spec_path)
    
    return BusDef.bus_defs_from_spec(spec_path)

def get_bus_matches(ports, bus_defs):
    pg, Z, wire_names = get_port_grouper(ports)
    
    # pass over all port groups and compute fcost to prioritize potential
    # bus pairings to optimize
    pg_bus_pairings = []
    for port_group in pg.get_port_groups():
        if len(port_group) < 20:
            continue
        
        # for each port group, only pair the 5 bus defs with the lowest fcost
        pg_bus_defs = list(sorted(
            [(get_mapping_fcost(port_group, bus_def), bus_def) for bus_def in bus_defs],
            key=lambda x:x[0].value,
        ))[:5]
        pg_bus_pairings.append((port_group, pg_bus_defs))
    
    # perform bus mappings for chosen subset
    pg_bus_mappings = []
    stime = time.time()
    for i, (port_group, bus_defs) in enumerate(pg_bus_pairings):
        #print('{}/{}, {}s'.format(i, len(pg_bus_pairings), time.time()-stime))
        #print('  - size port_group', len(port_group))
        if len(port_group) > 60:
            #print('    - skipping large')
            continue
        bus_mappings = []
        for fcost, bus_def in bus_defs:
            cost, mapping, match_cost_func = map_ports_to_bus(port_group, bus_def)
            bus_mappings.append((
                cost,
                fcost,
                mapping,
                match_cost_func,
                bus_def,
            ))
        bus_mappings.sort(key=lambda x: x[0])
        lcost = bus_mappings[0][0]
    
        pg_bus_mappings.append((
            lcost,
            port_group,
            bus_mappings,
        ))
    return list(sorted(pg_bus_mappings, key=lambda x: x[0]))

def debug_bus_mapping(
    port_group,
    bus_mapping,
):
    (
        cost,
        fcost,
        mapping,
        match_cost_func,
        bus_def,
    ) = bus_mapping

    print(bus_def)
    print('  - fcost:{}, cost:{}'.format(fcost, cost))
    print('  - mapped')
    for (is_opt, cost), pp, bp in sorted(
        [((bp in set(bus_def.opt_ports), match_cost_func(pp, bp)), pp, bp) \
            for pp, bp in mapping.items()
        ],
        key=lambda x: x[0],
    ):
        print('    - cost:{}, {:15s}:{:15s} {}'.format(
            match_cost_func(pp, bp),
            str(pp), str(bp),
            'opt' if is_opt else 'req',
        ))
    umap_ports = set(port_group) - set(mapping.keys())
    umap_busports = set(bus_def.req_ports) - set(mapping.values())
    print('  - umap phy ports')
    for port in sorted(umap_ports):
        print('    - ', port)
    print('  - umap bus ports')
    for port in sorted(umap_busports):
        print('    - ', port)
    
