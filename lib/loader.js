'use strict';

const fs = require('node:fs');
const path = require('node:path');
const json5 = require('json5');
const { busDefsFromSpec, loadBusDefsFromCatalog } = require('./busdef');

const walkDir = (dir, fileList = []) => {
  if (!fs.existsSync(dir)) return fileList;
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walkDir(fullPath, fileList);
    } else if (entry.isFile() && entry.name.endsWith('.json5')) {
      fileList.push(fullPath);
    }
  }
  return fileList;
};

const loadBusDefsFromDir = (dirPath) => {
  const files = walkDir(dirPath);
  const busDefs = [];
  for (const file of files) {
    try {
      const content = fs.readFileSync(file, 'utf8');
      const spec = json5.parse(content);
      if (spec && spec.abstractionDefinition) {
        busDefs.push(...busDefsFromSpec(spec));
      }
    } catch {
      // ignore non-spec files
    }
  }
  return busDefs;
};

const loadDefaultBusDefs = (busPath) => {
  if (busPath) {
    if (!fs.existsSync(busPath)) {
      throw new Error(`Specified duh-bus path does not exist: ${busPath}`);
    }
    const stat = fs.statSync(busPath);
    if (stat.isFile()) {
      const content = fs.readFileSync(busPath, 'utf8');
      const spec = json5.parse(content);
      return busDefsFromSpec(spec);
    }
    return loadBusDefsFromDir(busPath);
  }

  // Fallback to duh-bus package
  try {
    const duhBus = require('duh-bus');
    return loadBusDefsFromCatalog(duhBus);
  } catch (err) {
    throw new Error(`duh-bus not installed and -b/--duh-bus not specified: ${err.message}`);
  }
};

module.exports = {
  loadBusDefsFromDir,
  loadDefaultBusDefs
};
