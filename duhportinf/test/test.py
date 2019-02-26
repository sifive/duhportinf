import os
import unittest

from .. import util
from .. import main
from .. import _grouper 
from .. import _optimize 
from ..busdef import BusDef
from .. import _interface

class BundleRecognizer(unittest.TestCase):

    def test_recognize_vector(self):
       
        def check_type(ports, cls):
            bundle = _grouper.get_bundle_designation(ports)
            self.assertEqual(type(bundle), cls)
        def check_prefix(ports, prefix):
            bundle = _grouper.get_bundle_designation(ports)
            self.assertEqual(bundle.prefix, prefix)

        vector_ports = [('test_bit{}_n'.format(i), 1, 1) for i in range(20)]
        bundle1 = _grouper.get_bundle_designation(vector_ports)
        self.assertEqual(type(bundle1), _interface.VectorBundle)
        self.assertEqual(min(bundle1.range), 0)
        self.assertEqual(max(bundle1.range), 19)
        self.assertEqual(bundle1.prefix, 'test_bit')

        # skip indices so designation should be directed bundle, *not*
        # vector
        directed_ports1 = list(vector_ports)
        directed_ports1.append(('test_bit30_n', 1, 1))
        check_type(directed_ports1, _grouper.DirectedBundle)

        directed_ports2 = list(vector_ports)
        # change width of one port so designation should be directed
        # bundle, *not* vector
        directed_ports2[0] = ('test_bit0_n', 2, 1)
        check_type(directed_ports2, _grouper.DirectedBundle)

        directed_ports2 = list(vector_ports)
        # change direction of another port so designation should be
        # undirected bundle
        directed_ports2[1] = ('test_bit1_n', 2, -1)
        check_type(directed_ports2, _interface.UndirectedBundle)

        # test prefixing
        ports3 = list(vector_ports)
        ports3.append(('test_bad', 1, 1))
        check_prefix(ports3, 'test_b')
        ports3.append(('ntest_bad', 1, 1))
        check_prefix(ports3, '')

    def test_label_vector(self):
        ports = [('test_bit{}_n'.format(i), 1, 1) for i in range(2, 20)]
        pg, _, _ = _grouper.get_port_grouper(ports)
        interfaces = list([inter for _, inter in pg.get_initial_interfaces()])
        self.assertEqual(len(interfaces), 1)
        interface = next(iter(interfaces))
        bundles = list(interface.bundles)
        self.assertEqual(len(bundles), 1)
        bundle = next(iter(bundles))
        self.assertEqual(type(bundle), _interface.VectorBundle)

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
        pg, _, _ = _grouper.get_port_grouper(ports)
        wide_interfaces = [
            inter 
            for _, inter in pg.get_initial_interfaces() 
                if len(list(inter.bundles)) == 3
        ]
        self.assertEqual(len(wide_interfaces), 1)
        root_interface = next(iter(wide_interfaces))
        vbundles = list(filter(
            lambda b: type(b) == _interface.VectorBundle, 
            root_interface.bundles,
        ))
        # all three vectors must appear in their own designated interface
        # as a vector bundle
        self.assertEqual(len(vbundles), 3)
        b1, b2, b3 = sorted(vbundles, key=lambda b: b.size)
        self.assertEqual(b1.prefix, 'test2_bit_')
        self.assertEqual(min(b1.range), 0)
        self.assertEqual(max(b1.range), 4)
        self.assertEqual(b2.prefix, 'test_bit_sub')
        self.assertEqual(min(b2.range), 0)
        self.assertEqual(max(b2.range), 9)
        self.assertEqual(b3.prefix, 'test_bit')
        self.assertEqual(min(b3.range), 2)
        self.assertEqual(max(b3.range), 19)

    def test_structify_vectors(self):
        p1 = [('test_bit_1field{}_n'.format(i), 1, 1) for i in range(10)]
        p2 = [('test_bit_2field{}_n'.format(i), 1, 1) for i in range(10)]
        ports = [p for pp in [p1, p2] for p in pp]
        # temporary fix so that a structed interface is yielded
        ports.append(('background_signal', 1, 1))

        def get_type_bundles(inter, btype):
            return list(filter(
                lambda b: type(b) == btype,
                inter.bundles_structed,
            ))

        pg, _, _ = _grouper.get_port_grouper(ports)
        structed_interfaces = list(filter(
            lambda inter: inter.structed_width > 0,
            map(lambda x: x[1], pg.get_initial_interfaces()),
        ))
        #for _, inter in pg.get_initial_interfaces():
        #    print('interface ports')
        #    for p in inter.ports:
        #        print('  - ', p)
        # precisely one structed interface
        self.assertEqual(len(structed_interfaces), 1)
        sinter = next(iter(structed_interfaces))
        svbundles = list(sinter.struct_bundles)
        # with a single vector struct
        self.assertEqual(len(svbundles), 1)
        svbundle = next(iter(svbundles))
        self.assertEqual(max(svbundle.range), 9)
        self.assertEqual(min(svbundle.range), 0)
        self.assertEqual(
            tuple(sorted(svbundle.attributes)),
            tuple(sorted([
                ('test_bit_1field', 1, 1), ('test_bit_2field', 1, 1)
            ])),
        )
        self.assertEqual(
            tuple(sorted(svbundle.attributes_short)),
            tuple(sorted([
                ('1field', 1, 1), ('2field', 1, 1)
            ])),
        )
        
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
        pg, _, _ = _grouper.get_port_grouper(ports)
        for nid, inter in pg.get_initial_interfaces():
            self.assertEqual(len(list(inter.vector_bundles)), 0)
            self.assertEqual(len(list(inter.nonvector_bundles)), 1)
            seen |= set(inter.ports)
            prefix = next(iter(inter.ports))[0][:len('axi1')]
            # all signals in group must have same prefix
            self.assertTrue(
                all([p[0].startswith(prefix) for p in inter.ports])
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

        pg, _, _ = _grouper.get_port_grouper(ports)
        for nid, inter in pg.get_initial_interfaces():
            seen_ports |= set(inter.ports)
            pname = next(iter(inter.ports))[0]
            prefix = (
                pname[:len('axi1_sub1')] 
                if pname.startswith('axi1_sub')
                else pname[:len('axi0')]
            )
            # a port group of the size expected must have all prefix match
            if inter.size == len(port_group_map[prefix]):
                self.assertTrue(
                    all([p[0].startswith(prefix) for p in inter.ports])
                )
                seen_prefix.add(prefix)
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
        pg, _, _ = _grouper.get_port_grouper(ports)
        for nid, inter in pg.get_initial_interfaces():
            # for each port group, only pair the 5 bus defs with the lowest fcost
            l_fcost = next(iter(main._get_lfcost_bus_defs(inter, self.bus_defs)))[0]
            nid_cost_map[nid] = l_fcost
        optimal_nids = pg.get_optimal_nids(nid_cost_map)
        self.assertTrue(len(optimal_nids) > 0)

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
        interface = _interface.Interface.get_undirected(ports)
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
        axi0_interface = _interface.Interface.get_undirected(axi0_ports)

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
        core_interface = _interface.Interface.get_undirected([pp for pp, bp in true_mappings])
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

