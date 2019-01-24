import os
import numpy as np
import json5
from .busdef import BusDef
from ._optimize import map_ports_to_bus
from ._grouper import get_port_grouper
from . import busdef

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

    assn_ports = set()
    all_bus_mappings = []
    for ii, port in enumerate(ports):
        #if port[0] != 'axi0_BREADY':
        #    continue

        if ii % 10 == 0:
            print('{}/{} {}'.format(ii, len(ports), port))
        # do not reassign portsonly assign ports to a single bus definition
        if port in assn_ports: 
            continue
        mappings = []
        ccost = None
        for i, port_group in enumerate(pg.get_port_groups(port)):
            (cost, mapping), bus_def = min([
                (map_ports_to_bus(port_group, bus_def), bus_def) for bus_def in bus_defs 
            ])
            mappings.append((cost, bus_def, mapping))
            if ccost and cost > ccost:
                break
            ccost = cost
        min_mapping = min(mappings)
        all_bus_mappings.append(min_mapping)
        # do not reassign ports already assigned to their 'best' bus mapping
        _, _, cmapping = min_mapping
        assn_ports |= set(cmapping.keys())

    return sorted(all_bus_mappings)
