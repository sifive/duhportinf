'use strict';

const path = require('node:path');
const fs = require('node:fs');
const json5 = require('json5');
const { expect } = require('chai');

const {
  createBusDef,
  busDefsFromSpec,
  createBundleTree,
  createInterface,
  compareCost,
  mapPortsToBus,
  setSilent
} = require('../index');

const {
  getMappingFcostGlobal,
  getUserGroupAssignment
} = require('../lib/optimize');
const { getLowFcostBusDefs } = require('../lib/infer');


setSilent(true);

function loadTestBusDefs() {
  const bsdir = path.join(__dirname, '..', 'duhportinf', 'test', 'test-bus-specs');
  const axi4Spec = json5.parse(fs.readFileSync(path.join(bsdir, 'AXI4_rtl.json5'), 'utf8'));
  const dpramSpec = json5.parse(fs.readFileSync(path.join(bsdir, 'DPRAM_rtl.json5'), 'utf8'));

  const busDefs = busDefsFromSpec(axi4Spec);
  const memBusDefs = busDefsFromSpec(dpramSpec);
  return { busDefs, memBusDefs };
}

describe('Bundler', () => {
  it('test_basic', () => {
    const names = [
      'foo',
      'foo_bat1',
      'foo_bat2',
      'foo_bar1',
      'foo_bar2',
      'foo_bar3',
      'foo_baz1',
      'foo_baz3',
      'background'
    ];
    const ports = names.map(n => [n, 1, 1]);
    const bundle = createBundleTree(ports);
    const tree = bundle.tree;

    // foo.bar should be vector
    expect(Array.isArray(tree.foo.bar)).to.be.true;
    expect(tree.foo.bar).to.have.lengthOf(3);

    // foo.baz should *not* be a vector
    expect(typeof tree.foo.baz).to.equal('object');
    expect(Array.isArray(tree.foo.baz)).to.be.false;
    expect(Object.keys(tree.foo.baz)).to.have.lengthOf(2);
  });

  it('test_main_bundler', () => {
    const names = [
      'foo',
      'foo_bar1',
      'foo_bar2',
      'baz_sub',
      'baz_subby',
      'background'
    ];
    const ports = names.map(n => [n, 1, 1]);

    const bt = createBundleTree(ports);
    const bundles = bt.get_bundles();
    expect(bundles).to.have.lengthOf(3);
    const bnames = bundles.map(b => b.name).sort();
    expect(bnames).to.deep.equal(['baz', 'foo', 'root']);

    // singleton bundles should all be merged into rest
    const names2 = [
      'foo_bar_lol',
      'foo_bar_ex',
      'rando',
      'background',
      'signals'
    ];
    const ports2 = names2.map(n => [n, 1, 1]);
    const bt2 = createBundleTree(ports2);
    const bundles2 = bt2.get_bundles();
    expect(bundles2).to.have.lengthOf(2);

    const bb = bundles2.filter(b => Object.keys(b.tree).length === 3);
    expect(bb).to.have.lengthOf(1);
    const b = bb[0];
    const values = Object.values(b.tree).sort();
    expect(values).to.deep.equal(['background', 'rando', 'signals']);
  });

  it('test_flatten_passthrus', () => {
    const names = [
      'foo_bar',
      'foo_bar_long_name_1',
      'foo_bar_longy_name_2'
    ];
    const ports = names.map(n => [n, 1, 1]);
    const bundle = createBundleTree(ports);
    const tree = bundle.tree;

    expect(bundle.name).to.equal('foo_bar');
    expect(tree._[0]).to.equal('foo_bar');
    expect(tree.long_name_1[0]).to.equal('foo_bar_long_name_1');
    expect(tree.longy_name_2[0]).to.equal('foo_bar_longy_name_2');
  });

  it('test_label_vector', () => {
    const vectorPorts = Array.from({ length: 20 }, (_, i) => [`test_bit${i}_n`, 1, 1]);
    const bundle1 = createBundleTree(vectorPorts);
    const tree1 = bundle1.tree;

    expect(bundle1.name).to.equal('root');
    expect(Array.isArray(tree1.test_bit)).to.be.true;

    // skip indices -> directed bundle, not vector
    const directedPorts1 = [...vectorPorts, ['test_bit30_n', 1, 1]];
    const bundle2 = createBundleTree(directedPorts1);
    const tree2 = bundle2.tree;
    expect(bundle2.name).to.equal('test_bit');
    expect(typeof tree2).to.equal('object');
    expect(Array.isArray(tree2)).to.be.false;

    // change width -> directed bundle, not vector
    const directedPorts2 = [...vectorPorts];
    directedPorts2[0] = ['test_bit0_n', 2, 1];
    const bundle3 = createBundleTree(directedPorts2);
    const tree3 = bundle3.tree;
    expect(bundle3.name).to.equal('test_bit');
    expect(typeof tree3).to.equal('object');
    expect(Array.isArray(tree3)).to.be.false;
  });

  it('test_label_multiple_vectors', () => {
    const p1 = Array.from({ length: 18 }, (_, i) => [`test_bit${i + 2}_n`, 1, 1]);
    const p2 = Array.from({ length: 10 }, (_, i) => [`test_bit_sub${i}_n`, 1, 1]);
    const p3 = Array.from({ length: 5 }, (_, i) => [`test2_bit_${i}_n_y`, 1, 1]);
    const ports = [...p1, ...p2, ...p3];
    ports.push(
      ['testy_unrelated', 1, 1],
      ['unrelated1', 1, 1],
      ['unrelated_sub1', 1, 1]
    );

    const bt = createBundleTree(ports);
    const tree = bt.tree;

    expect(Array.isArray(tree.test.bit._)).to.be.true;
    expect(Array.isArray(tree.test.bit.sub)).to.be.true;
    expect(Array.isArray(tree.test['2_bit'])).to.be.true;
  });
});

describe('Grouper', () => {
  let busDefs;

  before(() => {
    const loaded = loadTestBusDefs();
    busDefs = loaded.busDefs;
  });

  it('test_grouping_basic', () => {
    const portNames = [
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
      'axi1_AWLEN'
    ];
    const ports = portNames.map(p => [p, 1, 1]);

    const seen = new Set();
    const bt = createBundleTree(ports);
    for (const [, inter] of bt.get_initial_interfaces()) {
      expect(inter.vectors).to.have.lengthOf(0);
      for (const p of inter.all_ports) seen.add(p[0]);
      const prefix = inter.prefix.slice(0, 4);
      for (const p of inter.ports) {
        expect(p[0].startsWith(prefix)).to.be.true;
      }
    }

    for (const p of portNames) {
      expect(seen.has(p)).to.be.true;
    }
  });

  it('test_grouping_nested', () => {
    const portGroupMap = {
      axi0_A: [
        'axi0_ACLK',
        'axi0_ARESETn',
        'axi0_ARQOS',
        'axi0_AWQOS',
        'axi0_AWID',
        'axi0_AWADDR',
        'axi0_AWLEN'
      ],
      axi1_sub1_A: [
        'axi1_sub1_ACLK',
        'axi1_sub1_ARESETn',
        'axi1_sub1_ARQOS',
        'axi1_sub1_AWQOS',
        'axi1_sub1_AWID',
        'axi1_sub1_AWADDR',
        'axi1_sub1_AWLEN'
      ],
      axi1_sub2_A: [
        'axi1_sub2_ACLK',
        'axi1_sub2_ARESETn',
        'axi1_sub2_ARQOS',
        'axi1_sub2_AWQOS',
        'axi1_sub2_AWID',
        'axi1_sub2_AWADDR',
        'axi1_sub2_AWLEN'
      ]
    };
    const allPorts = Object.values(portGroupMap).flat().map(p => [p, 1, 1]);

    const seenPorts = new Set();
    const seenPrefix = new Set();

    const bt = createBundleTree(allPorts);
    for (const [, inter] of bt.get_initial_interfaces()) {
      for (const p of inter.ports) seenPorts.add(p[0]);
      if (inter.prefix in portGroupMap) {
        expect(inter.size).to.equal(portGroupMap[inter.prefix].length);
        seenPrefix.add(inter.prefix);
      }
    }

    for (const p of allPorts) {
      expect(seenPorts.has(p[0])).to.be.true;
    }
    expect(seenPrefix.size).to.equal(3);
  });

  it('test_filter_optimal_groups', () => {
    const portNames = [
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
      'result_rsc_rdy'
    ];
    const ports = portNames.map(name => [name, 1, 1]);
    const bt = createBundleTree(ports);
    const nidCostMap = {};
    for (const [nid, inter] of bt.get_initial_interfaces()) {
      const lowFcostBds = getLowFcostBusDefs(inter, busDefs);
      nidCostMap[nid] = lowFcostBds[0].fcost;
    }
    const optimalNids = bt.get_optimal_nids(nidCostMap);
    expect(optimalNids.size).to.be.greaterThan(0);

    const portNames2 = [
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
      'background_3'
    ];
    const ports2 = portNames2.map(name => [name, 1, 1]);
    const dport = 'test_sub1_a';
    const bt2 = createBundleTree(ports2);
    const nidCostMap2 = {};
    const requireNids = new Set();

    for (const [nid, inter] of bt2.get_initial_interfaces()) {
      if (inter.ports.some(p => p[0] === dport)) {
        if (inter.prefix.startsWith('test')) {
          requireNids.add(nid);
          nidCostMap2[nid] = 1;
        } else {
          nidCostMap2[nid] = 5;
        }
      }
    }
    const optNids = bt2.get_optimal_nids(nidCostMap2, 2);
    expect(Array.from(optNids).sort()).to.deep.equal(Array.from(requireNids).sort());
  });
});

describe('Fcost', () => {
  let memBusDefs;

  before(() => {
    ({ memBusDefs } = loadTestBusDefs());
  });

  it('test_pcie_dpram', () => {
    const ports = [
      ['scram_wren', null, -1],
      ['scram_wraddr', null, -1],
      ['scram_rden', null, -1],
      ['scram_rdaddr', null, -1],
      ['scram_wrdata', null, -1],
      ['scram_rddata', null, 1],
      ['scram_rdderr', null, 1]
    ];
    const iface = createInterface(ports, []);
    const dpramMasterBd = memBusDefs.find(
      bd => bd.abstract_type.name === 'DPRAM_rtl' && bd.isInitiator
    );
    expect(dpramMasterBd).to.exist;
    const fcost = getMappingFcostGlobal(iface, dpramMasterBd);
    expect(fcost.dc).to.equal(1);
    expect(fcost.wc).to.equal(2);
  });

  it('test_multi_prefixgroup', () => {
    function getBd(tag, pList) {
      return createBusDef({ name: tag }, {}, 'master', pList, [], []);
    }
    const corrBd1Reqports = [
      ['ready', 1, -1],
      ['valid', 1, 1],
      ['data', 1, 1]
    ];
    const corrBd2Reqports = [
      ['blockalign', 1, 1],
      ['ctrl', 1, -1],
      ['burst', 1, -1]
    ];
    const incorrBdReqports = [
      ['complete', 1, 1],
      ['and', 1, 1],
      ['utter', 1, 1],
      ['garbage', 1, -1],
      ['ports', 1, -1],
      ['not', 1, -1],
      ['to', 1, 1],
      ['map', 1, 1]
    ];
    const corrBd1 = getBd('corr1', corrBd1Reqports);
    const corrBd2 = getBd('corr2', corrBd2Reqports);

    const bds = Array.from({ length: 10 }, () => getBd('incorr', incorrBdReqports));
    bds.push(corrBd1, corrBd2);

    const iface = createInterface([
      ['pl_ready', 1, -1],
      ['pl_valid', 1, 1],
      ['pl_data', 1, 1],
      ['pl_blockalign', 1, 1],
      ['pl_ctrl', 1, -1],
      ['pl_burst', 1, -1]
    ], []);

    const iBusDefs = getLowFcostBusDefs(iface, bds);
    const selBusDefs = iBusDefs.map(item => item.busDef);

    expect(selBusDefs).to.include(corrBd1);
    expect(selBusDefs).to.include(corrBd2);
  });
});

describe('BusMapping', () => {
  let busDefs;

  before(() => {
    const loaded = loadTestBusDefs();
    busDefs = loaded.busDefs;
  });

  it('test_ddr_axi4', () => {
    const trueSidebandPorts = new Set([
      'axi0_ARAPCMD',
      'axi0_AWALLSTRB',
      'axi0_WDATA_PARITY',
      'axi0_RDATA_PARITY',
      'axi0_AR_PARITY',
      'axi0_RCTRL_PARITY'
    ]);
    const trueMappings = [
      [['axi0_AWADDR', 37, 1], ['AWADDR', null, 1]],
      [['axi0_AWBURST', 2, 1], ['AWBURST', 2, 1]],
      [['axi0_AWVALID', 1, 1], ['AWVALID', 1, 1]],
      [['axi0_AWREADY', 1, -1], ['AWREADY', 1, -1]],
      [['axi0_WDATA', 256, 1], ['WDATA', null, 1]],
      [['axi0_WSTRB', 32, 1], ['WSTRB', null, 1]],
      [['axi0_WVALID', 1, 1], ['WVALID', 1, 1]],
      [['axi0_WREADY', 1, -1], ['WREADY', 1, -1]],
      [['axi0_BVALID', 1, -1], ['BVALID', 1, -1]],
      [['axi0_BREADY', 1, 1], ['BREADY', 1, 1]],
      [['axi0_ARADDR', 37, 1], ['ARADDR', null, 1]],
      [['axi0_ARLEN', 8, 1], ['ARLEN', 8, 1]],
      [['axi0_ARSIZE', 3, 1], ['ARSIZE', 3, 1]],
      [['axi0_ARBURST', 2, 1], ['ARBURST', 2, 1]],
      [['axi0_ARVALID', 1, 1], ['ARVALID', 1, 1]],
      [['axi0_ARREADY', 1, -1], ['ARREADY', 1, -1]],
      [['axi0_AWLOCK', 1, 1], ['AWLOCK', 1, 1]],
      [['axi0_AWQOS', 1, 1], ['AWQOS', 4, 1]],
      [['axi0_ARLOCK', 1, 1], ['ARLOCK', 1, 1]],
      [['axi0_ARQOS', 1, 1], ['ARQOS', 4, 1]],
      [['axi0_ACLK', 1, 1], ['ACLK', 1, 1]],
      [['axi0_ARID', 12, 1], ['ARID', null, 1]],
      [['axi0_AWID', 12, 1], ['AWID', null, 1]],
      [['axi0_RID', 12, -1], ['RID', null, -1]]
    ];

    const axi0Ports = trueMappings.map(([pp]) => pp);
    axi0Ports.push(
      ['axi0_ARAPCMD', 1, 1],
      ['axi0_AWALLSTRB', 1, 1],
      ['axi0_WDATA_PARITY', 32, 1],
      ['axi0_RDATA_PARITY', 32, -1],
      ['axi0_AR_PARITY', 1, 1],
      ['axi0_RCTRL_PARITY', 1, -1]
    );
    const axi0Interface = createInterface(axi0Ports, []);

    const busMappings = busDefs.map(bd => mapPortsToBus(axi0Interface, bd))
      .sort((a, b) => compareCost(a.cost, b.cost));
    const bm = busMappings[0];

    expect(bm.bus_def.isTarget).to.be.true;

    const trueMapKeys = new Set(trueMappings.map(([pp, bp]) => `${pp[0]}:${bp[0]}`));
    for (const [pp, bp] of bm.mapping) {
      expect(trueMapKeys.has(`${pp[0]}:${bp[0]}`)).to.be.true;
    }

    for (const sName of Object.keys(bm.sideband_mapping)) {
      expect(trueSidebandPorts.has(sName)).to.be.true;
    }
  });

  it('test_sifive_core', () => {
    const trueMappings = [
      [['front_port_axi4_0_ar_bits_id', 8, 1], ['ARID', null, 1]],
      [['front_port_axi4_0_aw_bits_addr', 40, 1], ['AWADDR', null, 1]],
      [['front_port_axi4_0_ar_ready', 1, -1], ['ARREADY', 1, -1]],
      [['front_port_axi4_0_r_bits_id', 8, -1], ['RID', null, -1]],
      [['front_port_axi4_0_w_bits_strb', 8, 1], ['WSTRB', null, 1]],
      [['front_port_axi4_0_aw_bits_id', 8, 1], ['AWID', null, 1]],
      [['front_port_axi4_0_aw_ready', 1, -1], ['AWREADY', 1, -1]],
      [['front_port_axi4_0_aw_bits_qos', 4, 1], ['AWQOS', 4, 1]],
      [['front_port_axi4_0_ar_bits_cache', 4, 1], ['ARCACHE', 4, 1]],
      [['front_port_axi4_0_ar_bits_size', 3, 1], ['ARSIZE', 3, 1]],
      [['front_port_axi4_0_aw_bits_burst', 2, 1], ['AWBURST', 2, 1]],
      [['front_port_axi4_0_ar_bits_addr', 40, 1], ['ARADDR', null, 1]],
      [['front_port_axi4_0_aw_bits_lock', 1, 1], ['AWLOCK', 1, 1]],
      [['front_port_axi4_0_w_bits_data', 64, 1], ['WDATA', null, 1]],
      [['front_port_axi4_0_ar_bits_lock', 1, 1], ['ARLOCK', 1, 1]],
      [['front_port_axi4_0_ar_bits_qos', 4, 1], ['ARQOS', 4, 1]],
      [['front_port_axi4_0_ar_bits_burst', 2, 1], ['ARBURST', 2, 1]],
      [['front_port_axi4_0_b_valid', 1, -1], ['BVALID', 1, -1]],
      [['front_port_axi4_0_ar_valid', 1, 1], ['ARVALID', 1, 1]],
      [['front_port_axi4_0_ar_bits_prot', 3, 1], ['ARPROT', 3, 1]],
      [['front_port_axi4_0_w_valid', 1, 1], ['WVALID', 1, 1]],
      [['front_port_axi4_0_w_ready', 1, -1], ['WREADY', 1, -1]],
      [['front_port_axi4_0_ar_bits_len', 8, 1], ['ARLEN', 8, 1]],
      [['front_port_axi4_0_b_ready', 1, 1], ['BREADY', 1, 1]]
    ];
    const coreInterface = createInterface(trueMappings.map(([pp]) => pp), []);

    const busMappings = busDefs.map(bd => mapPortsToBus(coreInterface, bd))
      .sort((a, b) => compareCost(a.cost, b.cost));
    const bm = busMappings[0];

    expect(bm.bus_def.isTarget).to.be.true;
    const trueMapKeys = new Set(trueMappings.map(([pp, bp]) => `${pp[0]}:${bp[0]}`));
    for (const [pp, bp] of bm.mapping) {
      expect(trueMapKeys.has(`${pp[0]}:${bp[0]}`)).to.be.true;
    }
    expect(Object.keys(bm.sideband_mapping)).to.have.lengthOf(0);
  });

  it('test_assign_user_group_ports', () => {
    const answerUserGroupMap = {
      AR: [
        ['axi0_AR_PARITY_EN', 1, 1],
        ['axi0_AR_PARITY', 2, 1],
        ['axi0_ARAPCMD', 1, 1]
      ],
      AW: [
        ['axi0_AW_PARITY', 1, 1],
        ['axi0_AW_PARITY_EN', 1, -1],
        ['axi0_AWCOBUF', 3, 1],
        ['axi0_AWAPCMD', 1, 1],
        ['axi0_AWALLSTRB', 4, 1]
      ],
      W: [
        ['axi0_WDATA_PARITY', 1, 1],
        ['axi0_WCTRL_PARITY', 4, 1],
        ['axi0_WPARITY_EN', 1, 1]
      ],
      B: [
        ['axi0_BPARITY', 1, 1],
        ['axi0_BPARITY_EN', 1, 1]
      ],
      R: [
        ['axi0_RDATA_PARITY', 1, 1],
        ['axi0_RCTRL_PARITY', 1, -1],
        ['axi0_RPARITY_EN', 1, 1]
      ]
    };
    const allPorts = Object.values(answerUserGroupMap).flat();
    const answerUmapPorts = new Set(allPorts.filter(p => p[2] === -1).map(p => p[0]));

    const iface = createInterface(allPorts, []);
    const userGroups = Object.keys(answerUserGroupMap).map(k => [k, [k, null, 1]]);
    const busDef = createBusDef({}, {}, 'master', [], [], userGroups);

    const { userGroupMapping, unmappedPorts } = getUserGroupAssignment(iface, allPorts, busDef);

    let totalGroups = 0;
    for (const [uport, ports] of userGroupMapping.entries()) {
      if (uport === null) continue;
      totalGroups++;
      const expectedPorts = answerUserGroupMap[uport[0]]
        .filter(p => !answerUmapPorts.has(p[0]))
        .map(p => p[0])
        .sort();
      const actualPorts = ports.map(p => p[0]).sort();
      expect(actualPorts).to.deep.equal(expectedPorts);
    }
    expect(totalGroups).to.equal(Object.keys(answerUserGroupMap).length);

    const actualUmap = new Set(unmappedPorts.map(p => p[0]));
    expect(actualUmap).to.deep.equal(answerUmapPorts);
  });
});
