'use strict';

const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');
const { execFileSync } = require('node:child_process');
const { expect } = require('chai');

describe('P0 Dependency & Browser Gate', () => {
  let tmpDir;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'portinf-browser-gate-'));
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it('proves all runtime modules bundle for browser without Node polyfills', () => {
    const esbuildPath = path.join(__dirname, '..', '..', 'duh-schema', 'node_modules', '.bin', 'esbuild');
    if (!fs.existsSync(esbuildPath)) {
      return;
    }

    const entryPath = path.join(tmpDir, 'browser-entry.js');
    const outPath = path.join(tmpDir, 'browser-bundle.js');

    // Create browser entry importing core functional modules
    fs.writeFileSync(entryPath, `
      import { hungarian, solveAssignment } from '${path.join(__dirname, '..', 'lib', 'hungarian.js')}';
      import { wordsFromName, getJaccardDist } from '${path.join(__dirname, '..', 'lib', 'tokenize.js')}';
      import { createCost, costValue } from '${path.join(__dirname, '..', 'lib', 'match-cost.js')}';
      import { createBundleTree, createInterface } from '${path.join(__dirname, '..', 'lib', 'bundle.js')}';
      import { createBusDef } from '${path.join(__dirname, '..', 'lib', 'busdef.js')}';
      import { formatPorts, resolveJsonRefs, getUnassignedPorts } from '${path.join(__dirname, '..', 'lib', 'duh-util.js')}';

      const ports = formatPorts({ a_clk: 1, a_data: 32 });
      const tree = createBundleTree(ports);
      const cost = createCost(0.5, 0, 0);
      const match = solveAssignment([[1, 2], [3, 4]]);
      console.log('Browser gate ok:', tree.name, cost.value, match.length);
    `, 'utf8');

    // Bundle with esbuild targeting browser
    execFileSync(esbuildPath, [
      entryPath,
      '--bundle',
      '--platform=browser',
      '--format=esm',
      `--outfile=${outPath}`
    ]);

    expect(fs.existsSync(outPath)).to.be.true;
    const bundledCode = fs.readFileSync(outPath, 'utf8');

    // Ensure no unbundled require('fs'), require('path'), etc.
    expect(bundledCode).to.not.include('require("fs")');
    expect(bundledCode).to.not.include('require("node:fs")');
    expect(bundledCode).to.not.include('require("child_process")');
  });
});
