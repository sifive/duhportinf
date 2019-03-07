import os
import unittest
import json

from .. import util
from .. import main_portinf
from .. import main_portbundler
from .. import _optimize 
from ..busdef import BusDef
from .. import _bundle

util.silent = True

class Bundler(unittest.TestCase):

    def setUp(self):
        pass

    def test_basic(self):
        names = [
            'foo',
            'foo_bat1',
            'foo_bat2',
            'foo_bar1',
            'foo_bar2',
            'foo_bar3',
            'foo_baz1',
            'foo_baz3',
            'background',
        ]
        ports = [(n, 1, 1) for n in names]
        bundle = _bundle.BundleTree(ports)
        tree = bundle.tree
        # foo.bar should be vector
        self.assertTrue(type(tree['foo']['bar']) == list)
        self.assertEqual(len(tree['foo']['bar']), 3)
        # foo.baz should be *not* be a vector
        self.assertTrue(type(tree['foo']['baz']) == dict)
        self.assertEqual(len(tree['foo']['baz']), 2)

    def test_main_bundler(self):
        names = [
            'foo',
            'foo_bar1',
            'foo_bar2',
            'baz_sub',
            'baz_subby',
            'background',
        ]
        ports = [(n, 1, 1) for n in names]

        # main bundler should give three separate bundles for groups of ports that
        # differ at their root word in the name
        bt = _bundle.BundleTree(ports)
        bundles = bt.get_bundles()
        self.assertEqual(len(bundles), 3)
        names = [b.name for b in bundles]
        self.assertEqual(
            list(sorted(names)),
            ['baz', 'foo', 'root'],
        )

        # singleton bundles should all be merged into rest
        names = [
            'foo_bar_lol',
            'foo_bar_ex',
            'rando',
            'background',
            'signals',
        ]
        ports = [(n, 1, 1) for n in names]
        bt = _bundle.BundleTree(ports)
        bundles = bt.get_bundles()
        self.assertEqual(len(bundles), 2)
        # singleton signals should all be placed in one bundle
        bb = list(filter(lambda b: len(b.tree) == 3, bundles))
        self.assertEqual(len(bb), 1)
        b = next(iter(bb))
        self.assertEqual(
            list(sorted([p for p in b.tree.values()])),
            ['background', 'rando', 'signals'],
        )

    def test_flatten_passthrus(self):
        names = [
            'foo_bar',
            'foo_bar_long_name_1',
            'foo_bar_longy_name_2',
        ]
        ports = [(n, 1, 1) for n in names]
        bundle = _bundle.BundleTree(ports)
        tree = bundle.tree
        #print(json.dumps(bundle.tree, indent=2))
        self.assertEqual(bundle.name, 'foo_bar')
        self.assertEqual('foo_bar', tree['_'][0])
        self.assertEqual('foo_bar_long_name_1',  tree['long_name_1'][0])
        self.assertEqual('foo_bar_longy_name_2', tree['longy_name_2'][0])

    def test_label_vector(self):
        vector_ports = [('test_bit{}_n'.format(i), 1, 1) for i in range(20)]
        bundle1 = _bundle.BundleTree(vector_ports)
        tree = bundle1.tree
        # should be a vector
        self.assertEqual(bundle1.name, 'root')
        self.assertEqual(type(tree['test_bit']), list)

        # skip indices so designation should be directed bundle, *not*
        # vector
        directed_ports1 = list(vector_ports)
        directed_ports1.append(('test_bit30_n', 1, 1))
        bundle2 = _bundle.BundleTree(directed_ports1)
        tree2 = bundle2.tree
        # should *not* be a vector
        self.assertEqual(bundle2.name, 'test_bit')
        self.assertTrue(type(tree2), dict)

        directed_ports2 = list(vector_ports)
        # change width of one port so designation should be directed
        # bundle, *not* vector
        directed_ports2[0] = ('test_bit0_n', 2, 1)
        bundle3 = _bundle.BundleTree(directed_ports1)
        tree3 = bundle3.tree
        # should *not* be a vector
        self.assertEqual(bundle3.name, 'test_bit')
        self.assertTrue(type(tree3), dict)

    def test_label_multiple_vectors(self):
        # create three vector groups and some background ports, which
        # should *not* be zipped into structs
        p1 = [('test_bit{}_n'.format(i), 1, 1) for i in range(2, 20)]
        p2 = [('test_bit_sub{}_n'.format(i), 1, 1) for i in range(10)]
        p3 = [('test2_bit_{}_n_y'.format(i), 1, 1) for i in range(5)]
        ports = [p for pp in [p1, p2, p3] for p in pp]
        ports.extend([(name, 1, 1) for name in [
            'testy_unrelated',
            'unrelated1',
            'unrelated_sub1',
        ]])
        bt = _bundle.BundleTree(ports)
        tree = bt.tree
        # test all three vectors properly grouped and tagged
        self.assertEqual(type(tree['test']['bit']['_']), list)
        self.assertEqual(type(tree['test']['bit']['sub']), list)
        self.assertEqual(type(tree['test']['2_bit']), list)

    def tearDown(self):
        pass

class Grouper(unittest.TestCase):

    def setUp(self):
        self.bus_defs, self.mem_bus_defs = _load_test_bus_defs()

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
        bt = _bundle.BundleTree(ports)
        for nid, inter in bt.get_initial_interfaces():
            self.assertEqual(len(inter.vectors), 0)
            seen |= set(inter.all_ports)
            prefix = inter.prefix[:len('axi1')]
            # all signals in group must have same prefix
            self.assertTrue(
                all([p[0].startswith(prefix) for p in inter.ports])
            )

        self.assertTrue(ports.issubset(seen))

    def test_grouping_nested(self):
        port_group_map = {
            'axi0_A': set([
                'axi0_ACLK',
                'axi0_ARESETn',
                'axi0_ARQOS',
                'axi0_AWQOS',
                'axi0_AWID',
                'axi0_AWADDR',
                'axi0_AWLEN',
            ]),
            'axi1_sub1_A': set([
                'axi1_sub1_ACLK',
                'axi1_sub1_ARESETn',
                'axi1_sub1_ARQOS',
                'axi1_sub1_AWQOS',
                'axi1_sub1_AWID',
                'axi1_sub1_AWADDR',
                'axi1_sub1_AWLEN',
            ]),
            'axi1_sub2_A': set([
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

        bt = _bundle.BundleTree(ports)
        for nid, inter in bt.get_initial_interfaces():
            seen_ports |= set(inter.ports)
            pname = next(iter(inter.ports))[0]
            # a port group of the size expected must have all prefix match
            if inter.prefix in port_group_map:
                self.assertEqual(inter.size, len(port_group_map[inter.prefix]))
                seen_prefix.add(inter.prefix)
        self.assertTrue(ports.issubset(seen_ports))
        # must see all three full prefix groups
        self.assertEqual(len(seen_prefix), 3)

    def test_filter_optimal_groups(self):
        port_names = [
            'clk',
            'arst_n',
            'f0_rsc_dat',
            'f0_rsc_vld',
            'f0_rsc_rdy',
            'f1_rsc_dat',
            'f1_rsc_vld',
            'f1_rsc_rdy',
            't0_rsc_dat',
            't0_rsc_vld',
            't0_rsc_rdy',
            'result_rsc_dat',
            'result_rsc_vld',
            'result_rsc_rdy',
        ]
        nid_cost_map = {}
        ports = [(name, 1, 1) for name in port_names]
        bt = _bundle.BundleTree(ports)
        for nid, inter in bt.get_initial_interfaces():
            # for each port group, only pair the 5 bus defs with the lowest fcost
            l_fcost = next(iter(main_portinf._get_lfcost_bus_defs(inter, self.bus_defs)))[0]
            nid_cost_map[nid] = l_fcost
        optimal_nids = bt.get_optimal_nids(nid_cost_map)
        # there should be at least one optimal nid yielded for mapping
        self.assertTrue(len(optimal_nids) > 0)

        port_names = [
            'test_sub1_a',
            'test_sub1_b',
            'test_sub1_c',
            'test_sub1_d',
            'test_sub2_a',
            'test_sub2_b',
            'test_sub2_c',
            'test_sub2_d',
            'background_1',
            'background_2',
            'background_3',
        ]
        nid_cost_map = {}
        ports = [(name, 1, 1) for name in port_names]
        dport = ('test_sub1_a', 1, 1)
        bt = _bundle.BundleTree(ports)
        nid_interface_map = {}
        require_nids = set()
        nid_inter_map = {}
        for nid, inter in bt.get_initial_interfaces():
            nid_inter_map[nid] = inter
            # for all interfaces (except the root), assign an equal cost
            nid_interface_map[nid] = inter
            if dport in inter.ports:
                if inter.prefix.startswith('test'):
                    require_nids.add(nid)
                    nid_cost_map[nid] = 1
                else:
                    nid_cost_map[nid] = 5
        opt_nids = bt.get_optimal_nids(nid_cost_map, min_num_leaves=2)
        self.assertEqual(
            list(sorted(opt_nids)),
            list(sorted(require_nids)),
        )

    def tearDown(self):
        pass

class Fcost(unittest.TestCase):

    def setUp(self):
        self.bus_defs, self.mem_bus_defs = _load_test_bus_defs()
    
    def test_pcie_dpram(self):
        # these are not going to map well to the logical definitions, but
        # fcost computation was previously broken due to hardcoded
        # constant
        ports = [
            ('scram_wren', None, -1),
            ('scram_wraddr', None, -1),
            ('scram_rden', None, -1),
            ('scram_rdaddr', None, -1),
            ('scram_wrdata', None, -1),
            ('scram_rddata', None, 1),
            ('scram_rdderr', None, 1),
        ]
        interface = _bundle.Interface(ports, [])
        dpram_master_bd = next(filter(
            lambda bd: (
                bd.abstract_type.name == 'DPRAM_rtl' and 
                bd.driver_type == 'master'
            ),
            self.mem_bus_defs,
        ))
        fcost = _optimize.get_mapping_fcost(interface, dpram_master_bd)
        self.assertEqual(fcost.dc, 1)
        self.assertEqual(fcost.wc, 2)

    def tearDown(self):
        pass

class BusMapping(unittest.TestCase):

    def setUp(self):
        self.bus_defs, self.mem_bus_defs = _load_test_bus_defs()

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
        axi0_interface = _bundle.Interface(axi0_ports, [])

        bus_mappings = list(sorted([
            _optimize.map_ports_to_bus(axi0_interface, bd)
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
        core_interface = _bundle.Interface([pp for pp, bp in true_mappings], [])
        bus_mappings = list(sorted([
            _optimize.map_ports_to_bus(core_interface, bd)
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

# load test bus defs
def _load_test_bus_defs():
    bus_defs = []
    bsdir = os.path.join(
        os.path.dirname(__file__),
        'test-bus-specs',
    )
    spec_path = os.path.join(bsdir, 'AXI4_rtl.json5')
    bus_defs.extend(BusDef.bus_defs_from_spec(spec_path))
    spec_path = os.path.join(bsdir, 'DPRAM_rtl.json5')
    mem_bus_defs = BusDef.bus_defs_from_spec(spec_path)
    return bus_defs, mem_bus_defs

