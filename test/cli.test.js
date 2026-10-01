'use strict';

const { execFileSync } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');
const { expect } = require('chai');
const json5 = require('json5');

const portinfBin = path.join(__dirname, '..', 'bin', 'duh-portinf.js');
const bundlerBin = path.join(__dirname, '..', 'bin', 'duh-portbundler.js');
const testBusSpecs = path.join(__dirname, '..', 'duhportinf', 'test', 'test-bus-specs');

describe('CLI Commands', () => {
  let tmpDir;
  let testJson5Path;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'portinf-cli-test-'));
    testJson5Path = path.join(tmpDir, 'test.json5');
    const doc = {
      component: {
        vendor: 'test.org',
        library: 'test',
        name: 'test_mod',
        version: '0.1.0',
        model: {
          ports: {
            axi0_ACLK: 1,
            axi0_ARESETn: 1,
            axi0_ARADDR: 32,
            axi0_ARVALID: 1,
            axi0_ARREADY: -1,
            axi0_AWADDR: 32,
            axi0_AWVALID: 1,
            axi0_AWREADY: -1,
            other_sig: 1
          }
        }
      }
    };
    fs.writeFileSync(testJson5Path, json5.stringify(doc), 'utf8');
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it('duh-portbundler produces clean JSON on stdout', () => {
    const stdout = execFileSync(bundlerBin, [testJson5Path], { encoding: 'utf8' });
    const parsed = JSON.parse(stdout);
    expect(parsed).to.have.property('definitions');
    expect(parsed.definitions).to.have.property('bundleDefinitions');
    expect(parsed.component.busInterfaces).to.be.an('array');
  });

  it('duh-portbundler writes to -o output file', () => {
    const outPath = path.join(tmpDir, 'bundle-out.json');
    execFileSync(bundlerBin, ['-o', outPath, testJson5Path]);
    expect(fs.existsSync(outPath)).to.be.true;
    const content = JSON.parse(fs.readFileSync(outPath, 'utf8'));
    expect(content.definitions.bundleDefinitions).to.exist;
  });

  it('duh-portbundler supports --debug report', () => {
    const stdout = execFileSync(bundlerBin, ['--debug', testJson5Path], { encoding: 'utf8' });
    const report = JSON.parse(stdout);
    expect(report.formatVersion).to.equal('1.0.0');
    expect(report.metadata.tool).to.equal('duh-portbundler');
  });

  it('duh-portinf matches interfaces with custom -b catalog', () => {
    const stdout = execFileSync(portinfBin, ['-b', testBusSpecs, testJson5Path], { encoding: 'utf8' });
    const parsed = JSON.parse(stdout);
    expect(parsed.definitions.busDefinitions).to.exist;
    expect(Object.keys(parsed.definitions.busDefinitions).length).to.be.greaterThan(0);
  });

  it('duh-portinf defaults to duh-bus catalog without -b', () => {
    const stdout = execFileSync(portinfBin, [testJson5Path], { encoding: 'utf8' });
    const parsed = JSON.parse(stdout);
    expect(parsed.definitions.busDefinitions).to.exist;
    expect(Object.keys(parsed.definitions.busDefinitions).length).to.be.greaterThan(0);
  });

  it('duh-portinf supports --debug structured report', () => {
    const stdout = execFileSync(portinfBin, ['--debug', testJson5Path], { encoding: 'utf8' });
    const report = JSON.parse(stdout);
    expect(report.formatVersion).to.equal('1.0.0');
    expect(report.metadata.tool).to.equal('duh-portinf');
    expect(report.portGroups).to.be.an('array');
    expect(report.selectedInterfaces).to.be.an('array');
  });

  it('returns non-zero exit code on invalid arguments', () => {
    expect(() => {
      execFileSync(portinfBin, ['/nonexistent/file.json5'], { stdio: 'pipe' });
    }).to.throw();
  });
});
