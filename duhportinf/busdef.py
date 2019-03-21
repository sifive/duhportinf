import numpy as np
import json5
import logging
from collections import defaultdict
from itertools import combinations
from ._optimize import MatchCost
from . import util

class dotdict(dict):
    """
    quick and dirty addition to allow access to bus defs using just dot operator
    dot.notation access to dictionary attributes
    """
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

class BusDef(object):
    
    @classmethod
    def is_spec_bus_def(cls, spec_path):
        if not spec_path.endswith('json5'):
            return False
        try:
            with open(spec_path) as fin:
                spec = json5.load(fin)
        except:
            logging.warn('Warning, could not load {} with json5 parser'.format(spec_path))
            return False
        return 'abstractionDefinition' in spec

    @classmethod
    def bus_defs_from_spec(cls, spec_path):
        """
        parse spec def and create the described slave+master bus interfaces 
        """
        with open(spec_path) as fin:
            spec = json5.load(fin)
        adkey = 'abstractionDefinition'
        bus_type = dotdict(spec[adkey]['busType'])
        abstract_type = dotdict({
            'vendor'  : spec[adkey]['vendor'],
            'library' : spec[adkey]['library'],
            'name'    : spec[adkey]['name'],
            'version' : spec[adkey]['version'],
        })
        
        master_req_ports = []
        master_opt_ports = []
        master_user_port_groups = []
        slave_req_ports = []
        slave_opt_ports = []
        slave_user_port_groups = []
        
        user_groups = []
        for portname, portdef in spec[adkey]['ports'].items():
            (
                is_user,
                user_group, 
                req_port_map, 
                opt_port_map,
            ) = cls.parse_port(portname, portdef)
            if is_user:
                user_groups.append(user_group)
            if 'onMaster' in req_port_map: master_req_ports.append(req_port_map['onMaster'])
            if 'onMaster' in opt_port_map: 
                if is_user:
                    master_user_port_groups.append((user_group, opt_port_map['onMaster']))
                else:
                    master_opt_ports.append(opt_port_map['onMaster'])
            if 'onSlave' in req_port_map: slave_req_ports.append(req_port_map['onSlave'])
            if 'onSlave' in opt_port_map: 
                if is_user:
                    slave_user_port_groups.append((user_group, opt_port_map['onSlave']))
                else:
                    slave_opt_ports.append(opt_port_map['onSlave'])
        
        if len(user_groups) > 1:
            # cannot have an anonymous ('') user group if there is more
            # than one specified
            assert not any([g == '' for g in user_groups])
            prefix_match = False
            for p1, p2 in combinations(user_groups, 2):
                prefix_match |= (p1.startswith(p2) or p2.startswith(p1))
            assert not prefix_match, \
                "ambiguous user_groups specified:{}".format(user_groups)

        bus_defs = []
        if master_req_ports != []:
            bus_defs.append(
                BusDef(
                    bus_type,
                    abstract_type, 
                    'master',
                    master_req_ports,
                    master_opt_ports,
                    master_user_port_groups,
                )
            )
        if slave_req_ports != []:
            bus_defs.append(
                BusDef(
                    bus_type,
                    abstract_type, 
                    'slave',
                    slave_req_ports,
                    slave_opt_ports,
                    slave_user_port_groups,
                )
            )
        return bus_defs
            
    @classmethod
    def parse_port(cls, portname, portdef):
        assert set([
            # NOTE was only required for IP-XACT, will be removed for
            # component.json5
            #'logicalName',
            'wire',
        ]).issubset(set(portdef.keys())), \
            "required keys missing in description of port {}".format(portname)
        req_port_map = defaultdict(lambda: None)
        opt_port_map = defaultdict(lambda: None)

        is_user = 'isUser' in portdef and portdef['isUser']
        user_group = '' if 'group' not in portdef else portdef['group'].lower()

        for type_key in ['onMaster', 'onSlave']:
            if type_key not in portdef['wire']:
                continue
            subportdef = portdef['wire'][type_key]
            assert (
                set([
                    #'presence',
                    'direction',
                    #'width',
                ]).issubset(set(subportdef.keys())) 
                or
                ('presence' in subportdef and subportdef['presence'] == 'illegal')
            ), \
                "required keys missing in {} description of port {}".format(
                    type_key, portname,
                )
            if 'presence' in subportdef:
                assert subportdef['presence'] in ['required', 'optional', 'illegal']
                # FIXME handle illegal separately
                if subportdef['presence'] == 'illegal':
                    continue
                
            width = None 
            if 'width' in subportdef and type(subportdef['width']) == int:
                width = subportdef['width']
            #direction = np.sign(-1) if subportdef['direction'] == 'in' else np.sign(1)
            direction = np.sign(1) if subportdef['direction'] == 'in' else np.sign(-1)
            desc = (portname, width, direction)
            # FIXME memory spec does not include 'presence' attr at the
            # moment
            if 'presence' not in subportdef:
                req_port_map[type_key] = desc
            elif subportdef['presence'] == 'required':
                req_port_map[type_key] = desc
            else:
                opt_port_map[type_key] = desc
                
        return (
            is_user,
            user_group,
            req_port_map,
            opt_port_map,
        )
    
    @property
    def num_req_ports(self): return len(self._req_ports)
    @property
    def num_opt_ports(self): return len(self._opt_ports)
    @property
    def req_ports(self): return list(self._req_ports)
    @property
    def opt_ports(self): return list(self._opt_ports)
    @property
    def user_port_groups(self): return list(self._user_port_groups)
    @property
    def all_ports(self): 
        l = list(self._req_ports)
        l.extend(self._opt_ports)
        return l
    
    def words_from_name(self, port_name):
        attrs = [
            # FIXME there's a subtlety as to why this does not work well
            # need to figure thit out
            #self.bus_type.name, 
            #self.bus_type.library, 
            port_name,
        ]
        # split each attribute
        return [sw.lower() for w in attrs for sw in util.words_from_name(w)]
    
    def __str__(self):
        return \
'bus_def{{\n\tbus_type:{},\n\tabstract_type:{},\n\tdriver_type:{},\n\tnum_req:{},\n\tnum_opt:{},\n}}'.format(
            self.bus_type,
            self.abstract_type, 
            self.driver_type,
            self.num_req_ports,
            self.num_opt_ports,
        )
    def __init__(
        self,
        bus_type,
        abstract_type, 
        driver_type,
        req_ports,
        opt_ports,
        user_port_groups,
    ):
        self.bus_type      = bus_type
        self.abstract_type = abstract_type
        self.driver_type   = driver_type
        self._req_ports    = req_ports
        self._opt_ports    = opt_ports
        # prefixes must all be lowercase
        self._user_port_groups = [(p.lower(), pp) for p, pp in user_port_groups]

#--------------------------------------------------------------------------
# debug
#--------------------------------------------------------------------------
def debug_bus_mapping(bm):
    debug_str = ''
    debug_str += str(bm.bus_def)+'\n'
    debug_str += ('  - cost:{}, fcost:{}'.format(bm.cost, bm.fcost))+'\n'
    debug_str += ('  - mapped')+'\n'
    # display mapped signals in order of best match, staring with required
    # signals
    for (is_opt, cost), pp, bp in sorted(
        [
            (
                (
                    bp in set(bm.bus_def.opt_ports), 
                    bm.match_cost_func(pp, bp),
                ), 
                pp, 
                bp,
            ) 
            for pp, bp in bm.mapping.items()
        ],
        key=lambda x: x[0],
    ):
        debug_str += ('    - cost:{}, {:15s}:{:15s} {}'.format(
            bm.match_cost_func(pp, bp),
            str(pp), str(bp),
            'opt' if is_opt else 'req',
        ))+'\n'

    if len(bm.sideband_mapping) > 0:
        debug_str += ('  - sideband')+'\n'
    for (is_umap, is_opt, cost), pp, bp in sorted(
        [
            (
                (
                    bp == None,
                    bp in set(bm.bus_def.opt_ports), 
                    MatchCost(1,1,1,) if bp == None else bm.match_cost_func(pp, bp),
                ), 
                pp, 
                bp,
            ) 
            for pp, bp in bm.sideband_mapping.items()
        ],
        key=lambda x: x[0],
    ):
        debug_str += ('    - cost:{}, {:15s}:{:15s} {}'.format(
            MatchCost(1,1,1) if is_umap else bm.match_cost_func(pp, bp),
            str(pp), str(bp),
            '' if is_umap else ('opt' if is_opt else 'req'),
        ))+'\n'

    # busports unmapped in either primary or sideband mapping
    umap_busports = (
        set(bm.bus_def.req_ports) 
        - set(bm.mapping.values())
        - set(bm.sideband_mapping.values())
    )
    if len(umap_busports) > 0:
        debug_str += ('  - umap bus ports')+'\n'
        for port in sorted(umap_busports):
            debug_str += ('    - {}'.format(port))+'\n'

    return debug_str

