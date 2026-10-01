'use strict';

const fs = require('node:fs');
const { createBundleTree, getBundles } = require('./bundle');
const { createDebugReport } = require('./debug');

const bundlePorts = (ports = []) => {
  const bt = createBundleTree(ports);
  return getBundles(bt);
};

const dumpJsonBundles = (output, componentDoc, bundles, options = {}) => {
  const debug = Boolean(options.debug);
  const doc = JSON.parse(JSON.stringify(componentDoc));

  const definitions = doc.definitions || (doc.definitions = {});
  const bundleDefinitions = definitions.bundleDefinitions || (definitions.bundleDefinitions = {});

  const comp = doc.component || (doc.component = {});
  const busInterfaces = comp.busInterfaces || (comp.busInterfaces = []);

  const bnames = new Set();
  const bundleObjs = [];

  for (const bundle of bundles) {
    if (bnames.has(bundle.name)) {
      throw new Error(`Duplicate bundle name: ${bundle.name}`);
    }
    bnames.add(bundle.name);

    const refname = `bundle-${bundle.name}`;
    const o = {
      name: bundle.name,
      interfaceMode: null,
      busType: 'bundle',
      abstractionTypes: [
        {
          viewRef: 'RTLview',
          portMaps: bundle.tree
        }
      ]
    };

    bundleDefinitions[refname] = o;
    busInterfaces.push({ $ref: `#/definitions/bundleDefinitions/${refname}` });
    bundleObjs.push({ refname, definition: o });
  }

  let resultStr;
  if (debug) {
    const report = createDebugReport({
      metadata: { tool: 'duh-portbundler' },
      bundles: bundleObjs
    });
    resultStr = JSON.stringify(report, null, 2);
  } else {
    resultStr = JSON.stringify(doc, null, 2);
  }

  if (typeof output === 'string') {
    fs.writeFileSync(output, resultStr + '\n', 'utf8');
  } else if (output && typeof output.write === 'function') {
    output.write(resultStr + '\n');
  }
  return resultStr;
};

module.exports = {
  bundlePorts,
  dumpJsonBundles
};
