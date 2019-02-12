import os
import unittest

from .. import _grouper 
from .. import _optimize 
from ..busdef import BusDef

def fun(x):
    return x + 1

class Grouper(unittest.TestCase):

    def test_grouping_basic(self):
        port_names = [
            'axi0_ACLK',
            'axi0_ARESETn',
            'axi0_ARQOS',
            'axi0_AWQOS',
            'axi0_AWID',
            'axi0_AWADDR',
            'axi0_AWLEN',
            'axi1_ACLK',
            'axi1_ARESETn',
            'axi1_ARQOS',
            'axi1_AWQOS',
            'axi1_AWID',
            'axi1_AWADDR',
            'axi1_AWLEN',
        ]
        ports = set([(p, 1, 1) for p in port_names])

        seen = set()
        port_groups = _get_init_port_groups(ports)
        for port_group in port_groups:
            seen |= port_group
            prefix = next(iter(port_group))[0][:len('axi1')]
            # all signals in group must have same prefix
            self.assertTrue(
                all([p[0].startswith(prefix) for p in port_group])
            )

        #self.assertEqual(2, len(port_groups))
        self.assertTrue(ports.issubset(seen))

    def test_grouping_nested(self):
        port_group_map = {
            'axi0': set([
                'axi0_ACLK',
                'axi0_ARESETn',
                'axi0_ARQOS',
                'axi0_AWQOS',
                'axi0_AWID',
                'axi0_AWADDR',
                'axi0_AWLEN',
            ]),
            'axi1_sub1': set([
                'axi1_sub1_ACLK',
                'axi1_sub1_ARESETn',
                'axi1_sub1_ARQOS',
                'axi1_sub1_AWQOS',
                'axi1_sub1_AWID',
                'axi1_sub1_AWADDR',
                'axi1_sub1_AWLEN',
            ]),
            'axi1_sub2': set([
                'axi1_sub2_ACLK',
                'axi1_sub2_ARESETn',
                'axi1_sub2_ARQOS',
                'axi1_sub2_AWQOS',
                'axi1_sub2_AWID',
                'axi1_sub2_AWADDR',
                'axi1_sub2_AWLEN',
            ]),
        }
        ports = set([(p, 1, 1) for pp in port_group_map.values() for p in pp ])

        seen_ports = set()
        seen_prefix = set()

        port_groups = _get_init_port_groups(ports)
        for port_group in port_groups:
            seen_ports |= port_group
            pname = next(iter(port_group))[0]
            prefix = (
                pname[:len('axi1_sub1')] 
                if pname.startswith('axi1_sub')
                else pname[:len('axi0')]
            )
            # a port group of the size expected must have all prefix match
            if len(port_group) == len(port_group_map[prefix]):
                self.assertTrue(
                    all([p[0].startswith(prefix) for p in port_group])
                )
                seen_prefix.add(prefix)
        self.assertTrue(ports.issubset(seen_ports))
        # must see all three full prefix groups
        self.assertEqual(len(seen_prefix), 3)

class BusMapping(unittest.TestCase):

    def setUp(self):
        self.bus_defs = []
        bsdir = os.path.join(
            os.path.dirname(__file__),
            'test-bus-specs',
        )
        spec_path = os.path.join(bsdir, 'AXI4_rtl.json5')
        self.bus_defs.extend(BusDef.bus_defs_from_spec(spec_path))                

    def test_ddr_axi4(self):
        true_sideband_ports = set([
            ('axi0_ARAPCMD', 1, 1),
            ('axi0_AWALLSTRB', 1, 1),
            ('axi0_WDATA_PARITY', 32, 1),
            ('axi0_RDATA_PARITY', 32, -1),
            ('axi0_AR_PARITY', 1, 1),
            ('axi0_RCTRL_PARITY', 1, -1),
        ])
        true_mappings = set([
            (('axi0_AWADDR', 37, 1), ('AWADDR', None, 1)),
            (('axi0_AWBURST', 2, 1), ('AWBURST', 2, 1)),
            (('axi0_AWVALID', 1, 1), ('AWVALID', 1, 1)),
            (('axi0_AWREADY', 1, -1), ('AWREADY', 1, -1)),
            (('axi0_WDATA', 256, 1), ('WDATA', None, 1)),
            (('axi0_WSTRB', 32, 1), ('WSTRB', None, 1)),
            (('axi0_WVALID', 1, 1), ('WVALID', 1, 1)),
            (('axi0_WREADY', 1, -1), ('WREADY', 1, -1)),
            (('axi0_BVALID', 1, -1), ('BVALID', 1, -1)),
            (('axi0_BREADY', 1, 1), ('BREADY', 1, 1)),
            (('axi0_ARADDR', 37, 1), ('ARADDR', None, 1)),
            (('axi0_ARLEN', 8, 1), ('ARLEN', 8, 1)),
            (('axi0_ARSIZE', 3, 1), ('ARSIZE', 3, 1)),
            (('axi0_ARBURST', 2, 1), ('ARBURST', 2, 1)),
            (('axi0_ARVALID', 1, 1), ('ARVALID', 1, 1)),
            (('axi0_ARREADY', 1, -1), ('ARREADY', 1, -1)),
            (('axi0_AWLOCK', 1, 1), ('AWLOCK', 1, 1)),
            (('axi0_AWQOS', 1, 1), ('AWQOS', 4, 1)),
            (('axi0_ARLOCK', 1, 1), ('ARLOCK', 1, 1)),
            (('axi0_ARQOS', 1, 1), ('ARQOS', 4, 1)),
            (('axi0_ACLK', 1, 1), ('ACLK', 1, 1)),
            (('axi0_ARID', 12, 1), ('ARID', None, 1)),
            (('axi0_AWID', 12, 1), ('AWID', None, 1)),
            (('axi0_RID', 12, -1), ('RID', None, -1)),
        ])
        axi0_ports = [pp for pp, bp in true_mappings]
        axi0_ports.extend(true_sideband_ports)

        bus_mappings = list(sorted([
            _optimize.map_ports_to_bus(axi0_ports, bd)
            for bd in self.bus_defs
        ], key=lambda bm: bm.cost))
        bm = bus_mappings[0]

        self.assertEqual(bm.bus_def.driver_type, 'slave')
        self.assertTrue(set(bm.m.items()).issubset(true_mappings))
        self.assertTrue(set(bm.sbm.keys()).issubset(true_sideband_ports))


    def test_sifive_core(self):
        true_mappings = set([
            (('front_port_axi4_0_ar_bits_id', 8, 1), ('ARID', None, 1)),
            (('front_port_axi4_0_aw_bits_addr', 40, 1), ('AWADDR', None, 1)),
            (('front_port_axi4_0_ar_ready', 1, -1), ('ARREADY', 1, -1)),
            (('front_port_axi4_0_r_bits_id', 8, -1), ('RID', None, -1)),
            (('front_port_axi4_0_w_bits_strb', 8, 1), ('WSTRB', None, 1)),
            (('front_port_axi4_0_aw_bits_id', 8, 1), ('AWID', None, 1)),
            (('front_port_axi4_0_aw_ready', 1, -1), ('AWREADY', 1, -1)),
            (('front_port_axi4_0_aw_bits_qos', 4, 1), ('AWQOS', 4, 1)),
            (('front_port_axi4_0_ar_bits_cache', 4, 1), ('ARCACHE', 4, 1)),
            (('front_port_axi4_0_ar_bits_size', 3, 1), ('ARSIZE', 3, 1)),
            (('front_port_axi4_0_aw_bits_burst', 2, 1), ('AWBURST', 2, 1)),
            (('front_port_axi4_0_ar_bits_addr', 40, 1), ('ARADDR', None, 1)),
            (('front_port_axi4_0_aw_bits_lock', 1, 1), ('AWLOCK', 1, 1)),
            (('front_port_axi4_0_w_bits_data', 64, 1), ('WDATA', None, 1)),
            (('front_port_axi4_0_ar_bits_lock', 1, 1), ('ARLOCK', 1, 1)),
            (('front_port_axi4_0_ar_bits_qos', 4, 1), ('ARQOS', 4, 1)),
            (('front_port_axi4_0_ar_bits_burst', 2, 1), ('ARBURST', 2, 1)),
            (('front_port_axi4_0_b_valid', 1, -1), ('BVALID', 1, -1)),
            (('front_port_axi4_0_ar_valid', 1, 1), ('ARVALID', 1, 1)),
            (('front_port_axi4_0_ar_bits_prot', 3, 1), ('ARPROT', 3, 1)),
            (('front_port_axi4_0_w_valid', 1, 1), ('WVALID', 1, 1)),
            (('front_port_axi4_0_w_ready', 1, -1), ('WREADY', 1, -1)),
            (('front_port_axi4_0_ar_bits_len', 8, 1), ('ARLEN', 8, 1)),
            (('front_port_axi4_0_b_ready', 1, 1), ('BREADY', 1, 1)),

        ])
        core_ports = [pp for pp, bp in true_mappings]
        bus_mappings = list(sorted([
            _optimize.map_ports_to_bus(core_ports, bd)
            for bd in self.bus_defs
        ], key=lambda bm: bm.cost))
        bm = bus_mappings[0]

        self.assertEqual(bm.bus_def.driver_type, 'slave')
        self.assertTrue(set(bm.m.items()).issubset(true_mappings))
        self.assertEqual(len(bm.sbm), 0)
        
    def tearDown(self):
        pass

#--------------------------------------------------------------------------
# helpers
#--------------------------------------------------------------------------
def _get_init_port_groups(ports):
    pg, _, _ = _grouper.get_port_grouper(ports)
    port_groups = [port_group for _, port_group in pg.get_initial_port_groups()]
    return port_groups

# quick function to shrink full mappings to smaller ones for test bus defs
def _filt_inputs(input_mappings, bus_defs):
    all_bd_portnames = set([p[0] for bd in bus_defs for p in bd.all_ports])
    filt_mappings = filter(
        lambda x: x[1][0] in all_bd_portnames,
        input_mappings,
    )
    print('filtered')
    for x in filt_mappings:
        print('{},'.format(x))

