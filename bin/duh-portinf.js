#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { parseArgs } = require('node:util');
const json5 = require('json5');
const {
  loadDefaultBusDefs,
  getUnassignedPorts,
  getBusMatches,
  dumpJsonBusCandidates,
  progressBar
} = require('../index');

function printHelp() {
  process.stderr.write(`usage: duh-portinf [-h] [-b DUH_BUS] [-o OUTPUT] [--debug] component_json5

positional arguments:
  component_json5       input component.json5 with port list of top-level module

options:
  -h, --help            show this help message and exit
  -b, --duh-bus DUH_BUS duh-bus root directory that contains bus specifications
  -o, --output OUTPUT   output path to busprop.json with proposed bus mappings (default: stdout)
  --debug               dump debug format
`);
}

function main() {
  let parsed;
  try {
    parsed = parseArgs({
      options: {
        'duh-bus': { type: 'string', short: 'b' },
        output: { type: 'string', short: 'o' },
        debug: { type: 'boolean', default: false },
        help: { type: 'boolean', short: 'h', default: false }
      },
      allowPositionals: true
    });
  } catch (err) {
    process.stderr.write(`error: ${err.message}\n`);
    printHelp();
    process.exit(1);
  }

  const { values, positionals } = parsed;

  if (values.help || positionals.length === 0) {
    printHelp();
    process.exit(values.help ? 0 : 1);
  }

  const componentPath = positionals[0];
  if (!fs.existsSync(componentPath)) {
    process.stderr.write(`error: ${componentPath} does not exist\n`);
    process.exit(1);
  }

  const outputPath = values.output;
  if (outputPath) {
    const dn = path.dirname(outputPath);
    if (dn && dn !== '.' && !fs.existsSync(dn)) {
      process.stderr.write(`error: output directory ${dn} does not exist\n`);
      process.exit(1);
    }
  }

  let componentRaw;
  try {
    const text = fs.readFileSync(componentPath, 'utf8');
    componentRaw = json5.parse(text);
  } catch (err) {
    process.stderr.write(`error reading ${componentPath}: ${err.message}\n`);
    process.exit(1);
  }

  let busDefs;
  try {
    busDefs = loadDefaultBusDefs(values['duh-bus']);
  } catch (err) {
    process.stderr.write(`error: ${err.message}\n`);
    process.exit(1);
  }

  process.stderr.write(`loaded ${busDefs.length} bus defs\n`);

  const unassnPorts = getUnassignedPorts(componentRaw);
  process.stderr.write(`mapping ${unassnPorts.length} unassigned ports\n`);

  if (unassnPorts.length === 0) {
    process.stderr.write('no unassigned ports to map\n');
    process.exit(0);
  }

  const iBusMappings = getBusMatches(unassnPorts, busDefs, progressBar);

  dumpJsonBusCandidates(
    outputPath || process.stdout,
    componentRaw,
    iBusMappings,
    { debug: values.debug }
  );
}

main();
