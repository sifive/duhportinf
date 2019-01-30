import numpy as np
import json5
from collections import defaultdict

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
            print('Warning, could not load {} with json5 parser'.format(spec_path))
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
        slave_req_ports = []
        slave_opt_ports = []
        
        for portname, portdef in spec[adkey]['ports'].items():
            req_port_map, opt_port_map = cls.parse_port(portname, portdef)
            if 'onMaster' in req_port_map: master_req_ports.append(req_port_map['onMaster'])
            if 'onMaster' in opt_port_map: master_opt_ports.append(opt_port_map['onMaster'])
            if 'onSlave'  in req_port_map: slave_req_ports.append(req_port_map['onSlave'])
            if 'onSlave'  in opt_port_map: slave_opt_ports.append(opt_port_map['onSlave'])
        
        #print('num master req ports', len(master_req_ports))
        #print('num master opt ports', len(master_opt_ports))
        #print('num slave req ports', len(slave_req_ports))
        #print('num slave opt ports', len(slave_opt_ports))
        
        bus_defs = []
        if master_req_ports != []:
            bus_defs.append(
                BusDef(
                    bus_type,
                    abstract_type, 
                    'master',
                    master_req_ports,
                    master_opt_ports,
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
                )
            )
        return bus_defs
            
    @classmethod
    def parse_port(cls, portname, portdef):
        assert set([
            'logicalName',
            'wire',
        ]).issubset(set(portdef.keys())), \
            "required keys missing in description of port {}".format(portname)
        logical_name = portdef['logicalName']
        req_port_map = defaultdict(lambda: None)
        opt_port_map = defaultdict(lambda: None)
        for type_key in ['onMaster', 'onSlave']:
            if type_key not in portdef['wire']:
                continue
            subportdef = portdef['wire'][type_key]
            assert (
                set([
                    'presence',
                    'direction',
                    #'width',
                ]).issubset(set(subportdef.keys())) 
                or
                ('presence' in subportdef and subportdef['presence'] == 'illegal')
            ), \
                "required keys missing in {} description of port {}".format(
                    type_key, logical_name,
                )
            assert subportdef['presence'] in ['required', 'optional', 'illegal']
            # FIXME handle illegal separately
            if subportdef['presence'] == 'illegal':
                continue
                
            width = None if 'width' not in subportdef else int(subportdef['width'])
            #direction = np.sign(-1) if subportdef['direction'] == 'in' else np.sign(1)
            direction = np.sign(1) if subportdef['direction'] == 'in' else np.sign(-1)
            desc = (logical_name, width, direction)
            if subportdef['presence'] == 'required':
                req_port_map[type_key] = desc
            else:
                opt_port_map[type_key] = desc
                
        return req_port_map, opt_port_map
    
    @property
    def num_req_ports(self): return len(self._req_ports)
    @property
    def num_opt_ports(self): return len(self._opt_ports)
    @property
    def req_ports(self): return list(self._req_ports)
    @property
    def opt_ports(self): return list(self._opt_ports)
    
    def words_from_name(self, port_name):
        return [
            self.bus_type.name, 
            #self.bus_type.library, 
            port_name,
        ]
    
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
    ):
        self.bus_type      = bus_type
        self.abstract_type = abstract_type
        self.driver_type   = driver_type
        self._req_ports    = req_ports
        self._opt_ports    = opt_ports

