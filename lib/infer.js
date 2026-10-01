'use strict';

const fs = require('node:fs');
const { createCost, compareCost } = require('./match-cost');
const { createBundleTree } = require('./bundle');
const {
  getMappingFcostGlobal,
  getMappingFcostLocal,
  mapPortsToBus
} = require('./optimize');
const { commonPrefix } = require('./tokenize');
const { progressBar } = require('./duh-util');
const { createDebugReport } = require('./debug');

const getLowFcostBusDefs = (interfaceObj, busDefs) => {
  const getSortedFcosts = (fcostFunc) => (
    busDefs.map(bd => ({
      fcost: fcostFunc(interfaceObj, bd),
      busDef: bd
    })).sort((a, b) => compareCost(a.fcost, b.fcost))
  );

  const fcostsGlobal = getSortedFcosts(getMappingFcostGlobal);
  const fcostsLocal = getSortedFcosts(getMappingFcostLocal);

  const topGlobalBds = new Set(fcostsGlobal.slice(0, 5).map(item => item.busDef));
  const fcostsLocalFiltered = fcostsLocal.filter(item => !topGlobalBds.has(item.busDef)).slice(0, 4);

  return [...fcostsGlobal.slice(0, 5), ...fcostsLocalFiltered];
};

const getBusPairings = (bt, busDefs) => {
  const iBusPairings = [];
  const nidCostMap = {};

  for (const [nid, interfaceObj] of bt.get_initial_interfaces()) {
    const iBusDefs = getLowFcostBusDefs(interfaceObj, busDefs);
    if (iBusDefs.length === 0) continue;

    const lFcost = createCost(0, 0, iBusDefs[0].fcost.dc);

    iBusPairings.push([nid, lFcost, interfaceObj, iBusDefs]);
    nidCostMap[nid] = lFcost;
  }

  const optimalNids = bt.get_optimal_nids(nidCostMap);
  return iBusPairings
    .filter(([nid]) => optimalNids.has(nid))
    .sort((a, b) => compareCost(a[1], b[1]));
};

const getInitialBusMatches = (bt, iBusPairings, onProgress = progressBar) => {
  const iBusMappings = [];
  const nidCostMap = {};
  const ptot = iBusPairings.reduce((sum, item) => sum + item[3].length, 0);
  let pcurr = 0;

  if (onProgress) onProgress(pcurr, ptot);

  for (const [nid, , interfaceObj, busDefs] of iBusPairings) {
    const busMappings = [];
    for (const { fcost, busDef } of busDefs) {
      const bm = mapPortsToBus(interfaceObj, busDef);
      bm.fcost = fcost;
      busMappings.push(bm);
      pcurr++;
      if (onProgress) onProgress(pcurr, ptot);
    }

    busMappings.sort((a, b) => compareCost(a.cost, b.cost));
    const lcost = busMappings[0].cost;
    nidCostMap[nid] = lcost;

    iBusMappings.push([nid, lcost, interfaceObj, busMappings]);
  }

  const optimalNids = bt.get_optimal_nids(nidCostMap);
  return iBusMappings
    .filter(([nid]) => optimalNids.has(nid))
    .sort((a, b) => compareCost(a[1], b[1]));
};

const getBusMatches = (ports, busDefs, onProgress = progressBar) => {
  const bt = createBundleTree(ports);
  const optIBusPairings = getBusPairings(bt, busDefs);
  const optIBusMappings = getInitialBusMatches(bt, optIBusPairings, onProgress);
  return optIBusMappings.map(x => [x[2], x[3]]);
};

const expandIfVector = (interfaceObj, port) => {
  const portName = Array.isArray(port) ? port[0] : port;
  if (interfaceObj.is_vector(portName)) {
    return interfaceObj.get_vector(portName).map(p => p[0]);
  }
  return portName;
};

const dumpJsonBusCandidates = (output, componentDoc, iBusMappings, options = {}) => {
  const debug = Boolean(options.debug);
  const doc = JSON.parse(JSON.stringify(componentDoc));

  const definitions = doc.definitions || (doc.definitions = {});
  const pgCntBase = typeof definitions.pg_cnt === 'number' ? definitions.pg_cnt : 0;
  definitions.pg_cnt = pgCntBase + iBusMappings.length;

  const busDefinitions = definitions.busDefinitions || (definitions.busDefinitions = {});
  const busMappedPortGroups = definitions.busMappedPortGroups || (definitions.busMappedPortGroups = []);

  const comp = doc.component || (doc.component = {});
  const busInterfaces = comp.busInterfaces || (comp.busInterfaces = []);
  const busInterfaceAlts = comp.busInterfaceAlts || (comp.busInterfaceAlts = []);

  const sortedMappings = [...iBusMappings].sort((a, b) => b[0].size - a[0].size);

  const debugPortGroups = [];
  const debugSelectedInterfaces = [];
  const debugAlternateInterfaces = [];

  for (let i = 0; i < sortedMappings.length; i++) {
    const [interfaceObj, busMappings] = sortedMappings[i];
    const prefix = interfaceObj.prefix.replace(/^_+|_+$/g, '');

    for (let j = 0; j < busMappings.length; j++) {
      const bm = busMappings[j];
      const busintName = `busint-portgroup_${pgCntBase + i}-mapping_${j}-prefix_${prefix}-${bm.bus_def.driver_type}-${bm.bus_def.abstract_type.name}`;

      const portmapObj = {};
      for (const [pp, bp] of bm.mapping) {
        portmapObj[bp[0]] = expandIfVector(interfaceObj, pp[0]);
      }

      for (const [uport, uports] of bm.user_group_mapping.entries()) {
        portmapObj[uport[0]] = uports.map(p => expandIfVector(interfaceObj, p[0]));
      }

      if (bm.unmapped_ports.length > 0) {
        portmapObj.__UMAP__ = bm.unmapped_ports.map(p => expandIfVector(interfaceObj, p[0]));
      }

      const ifaceObj = {
        name: prefix,
        interfaceMode: bm.bus_def.driver_type,
        busType: bm.bus_def.bus_type,
        abstractionTypes: [
          {
            viewRef: 'RTLview',
            portMaps: portmapObj
          }
        ]
      };

      busDefinitions[busintName] = ifaceObj;

      const refObj = { $ref: `#/definitions/busDefinitions/${busintName}` };
      if (j === 0) {
        busInterfaces.push(refObj);
        debugSelectedInterfaces.push({ ref: refObj, interface: ifaceObj, cost: bm.cost });
      } else {
        busInterfaceAlts.push(refObj);
        debugAlternateInterfaces.push({ ref: refObj, interface: ifaceObj, cost: bm.cost });
      }
    }

    const bestBm = busMappings[0];
    const portNames = interfaceObj.ports.map(p => p[0]);
    const groupPrefix = commonPrefix(portNames);
    const costObj = [
      ['num_ports', interfaceObj.size],
      ['prefix', groupPrefix],
      ['num-direction-mismatch', Math.round(bestBm.cost.dc)],
      ['num-width-mismatch', Math.round(bestBm.cost.wc)]
    ];

    busMappedPortGroups.push([`portgroup_${i}`, costObj]);
    debugPortGroups.push({ id: `portgroup_${i}`, cost: costObj });
  }

  let resultStr;
  if (debug) {
    const report = createDebugReport({
      portGroups: debugPortGroups,
      selectedInterfaces: debugSelectedInterfaces,
      alternateInterfaces: debugAlternateInterfaces,
      busDefinitions
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
  getLowFcostBusDefs,
  getBusPairings,
  getInitialBusMatches,
  getBusMatches,
  dumpJsonBusCandidates
};
