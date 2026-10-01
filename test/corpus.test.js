'use strict';

const path = require('node:path');
const fs = require('node:fs');
const json5 = require('json5');
const { expect } = require('chai');

const {
  loadBusDefsFromCatalog,
  loadBusDefsFromDir,
  getUnassignedPorts,
  getBusMatches,
  bundlePorts,
  dumpJsonBusCandidates,
  dumpJsonBundles,
  setSilent
} = require('../index');

setSilent(true);

describe('Corpus Integration Tests', () => {
  let busDefs;

  before(() => {
    // Load modern duh-bus catalog
    try {
      const duhBus = require('duh-bus');
      busDefs = loadBusDefsFromCatalog(duhBus);
    } catch {
      const bsdir = path.join(__dirname, '..', 'duhportinf', 'test', 'test-bus-specs');
      busDefs = loadBusDefsFromDir(bsdir);
    }
  });

  it('runs on block-cadence-ddr3/ddr.json5', () => {
    const ddrPath = path.join(__dirname, '..', '..', 'block-cadence-ddr3', 'ddr.json5');
    if (!fs.existsSync(ddrPath)) return;

    const doc = json5.parse(fs.readFileSync(ddrPath, 'utf8'));
    const unassn = getUnassignedPorts(doc);
    expect(unassn.length).to.be.greaterThan(0);

    // Test bundler
    const bundles = bundlePorts(unassn);
    expect(bundles.length).to.be.greaterThan(0);
    const bundleJson = dumpJsonBundles(null, doc, bundles);
    const parsedBundle = JSON.parse(bundleJson);
    expect(parsedBundle.definitions.bundleDefinitions).to.exist;

    // Test portinf
    const matches = getBusMatches(unassn, busDefs);
    expect(matches.length).to.be.greaterThan(0);
    const infJson = dumpJsonBusCandidates(null, doc, matches);
    const parsedInf = JSON.parse(infJson);
    expect(parsedInf.definitions.busDefinitions).to.exist;
  });

  it('runs on block-nvdla/nvdla.json5', () => {
    const nvdlaPath = path.join(__dirname, '..', '..', 'block-nvdla', 'nvdla.json5');
    if (!fs.existsSync(nvdlaPath)) return;

    const doc = json5.parse(fs.readFileSync(nvdlaPath, 'utf8'));
    const unassn = getUnassignedPorts(doc);
    expect(unassn.length).to.be.greaterThan(0);

    const bundles = bundlePorts(unassn);
    expect(bundles.length).to.be.greaterThan(0);

    const matches = getBusMatches(unassn, busDefs);
    expect(matches.length).to.be.greaterThan(0);
  });

  it('runs on block-ark/ark.json5', () => {
    const arkPath = path.join(__dirname, '..', '..', 'block-ark', 'ark.json5');
    if (!fs.existsSync(arkPath)) return;

    const doc = json5.parse(fs.readFileSync(arkPath, 'utf8'));
    const unassn = getUnassignedPorts(doc);
    expect(unassn.length).to.be.greaterThan(0);

    const bundles = bundlePorts(unassn);
    expect(bundles.length).to.be.greaterThan(0);
  });

  it('runs on block-zipline-microsoft-extra/duh/cr_kme.json5', () => {
    const kmePath = path.join(__dirname, '..', '..', 'block-zipline-microsoft-extra', 'duh', 'cr_kme.json5');
    if (!fs.existsSync(kmePath)) return;

    const doc = json5.parse(fs.readFileSync(kmePath, 'utf8'));
    const unassn = getUnassignedPorts(doc);
    expect(unassn.length).to.be.greaterThan(0);

    const bundles = bundlePorts(unassn);
    expect(bundles.length).to.be.greaterThan(0);

    const matches = getBusMatches(unassn, busDefs);
    expect(matches.length).to.be.greaterThan(0);
  });
});
