'use strict';

const {
  createCost,
  zeroCost,
  addCost,
  mulCost,
  normalizeCost
} = require('./match-cost');
const { wordsFromName, getJaccardDist, getFracMissingTokens, getNumMissingTokens } = require('./tokenize');
const { solveAssignment } = require('./hungarian');

const getDupWords = (ports = []) => {
  const portsList = Array.isArray(ports) ? ports : Array.from(ports);
  const n = portsList.length;
  if (n === 0) return new Set();

  const wordCounts = new Map();
  for (const p of portsList) {
    const words = new Set(wordsFromName(p[0]));
    for (const w of words) {
      wordCounts.set(w, (wordCounts.get(w) || 0) + 1);
    }
  }

  const dupWords = new Set();
  for (const [w, cnt] of wordCounts.entries()) {
    if (cnt === n) {
      dupWords.add(w);
    }
  }
  return dupWords;
};

const getPortWords = (interfaceObj, busDef) => {
  const dupWords = getDupWords(interfaceObj.ports);
  const pWords = new Set();
  for (const p of interfaceObj.ports) {
    for (const w of wordsFromName(p[0])) {
      if (!dupWords.has(w)) {
        pWords.add(w);
      }
    }
  }

  const bWords = new Set();
  for (const p of [...busDef.req_ports, ...busDef.opt_ports]) {
    for (const w of busDef.wordsFromName(p[0])) {
      bWords.add(w);
    }
  }
  return [pWords, bWords];
};

const getNameFcost1 = (interfaceObj, busDef) => {
  const [pWords, bWords] = getPortWords(interfaceObj, busDef);
  return getJaccardDist(pWords, bWords);
};

const getNameFcost2 = (interfaceObj, busDef) => {
  const [pWords, bWords] = getPortWords(interfaceObj, busDef);
  return getFracMissingTokens(bWords, pWords);
};

const keyFor = (width, dir) => `${width === null ? 'null' : width}:${dir}`;

const parseKey = (key) => {
  const [wStr, dStr] = key.split(':');
  const width = wStr === 'null' ? null : parseInt(wStr, 10);
  const dir = parseInt(dStr, 10);
  return [width, dir];
};

const getMappingFcostBase = (interfaceObj, busDef, penalizeUmap = true) => {
  const ports = interfaceObj.get_ports_to_map();

  const phyPortCnts = new Map();
  for (const p of ports) {
    const k = keyFor(p[1], p[2]);
    phyPortCnts.set(k, (phyPortCnts.get(k) || 0) + 1);
  }

  const busReqPortCnts = new Map();
  for (const p of busDef.req_ports) {
    const k = keyFor(p[1], p[2]);
    busReqPortCnts.set(k, (busReqPortCnts.get(k) || 0) + 1);
  }

  const busOptPortCnts = new Map();
  for (const p of busDef.opt_ports) {
    const k = keyFor(p[1], p[2]);
    busOptPortCnts.set(k, (busOptPortCnts.get(k) || 0) + 1);
  }

  const allKeys = new Set([
    ...phyPortCnts.keys(),
    ...busReqPortCnts.keys(),
    ...busOptPortCnts.keys()
  ]);

  for (const k of allKeys) {
    let ppc = phyPortCnts.get(k) || 0;
    let brc = busReqPortCnts.get(k) || 0;
    let boc = busOptPortCnts.get(k) || 0;

    // 1. match required ports
    const numReqMatched = Math.min(ppc, brc);
    ppc -= numReqMatched;
    brc -= numReqMatched;

    // 2. match optional ports
    const numOptMatched = Math.min(ppc, boc);
    ppc -= numOptMatched;
    boc -= numOptMatched;

    phyPortCnts.set(k, ppc);
    busReqPortCnts.set(k, brc);
    busOptPortCnts.set(k, boc);
  }

  const inKeys = [];
  const outKeys = [];
  for (const k of allKeys) {
    const [, dir] = parseKey(k);
    if (dir === 1) inKeys.push(k);
    else if (dir === -1) outKeys.push(k);
  }

  const sumAcross = (keys, cntMap) => {
    let sum = 0;
    for (const k of keys) {
      sum += cntMap.get(k) || 0;
    }
    return sum;
  };

  let cost = zeroCost();
  for (const [, keys] of [['in', inKeys], ['out', outKeys]]) {
    let ppc = sumAcross(keys, phyPortCnts);
    let brc = sumAcross(keys, busReqPortCnts);
    let boc = sumAcross(keys, busOptPortCnts);

    // match required ports by direction
    const numDirReqMatched = Math.min(ppc, brc);
    ppc -= numDirReqMatched;
    brc -= numDirReqMatched;

    cost = addCost(cost, mulCost(createCost(0, 1, 0), numDirReqMatched));
    cost = addCost(cost, mulCost(createCost(0, 1, 1), brc));

    // match optional ports by direction
    const numDirOptMatched = Math.min(ppc, boc);
    ppc -= numDirOptMatched;
    boc -= numDirOptMatched;

    cost = addCost(cost, mulCost(createCost(0, 1, 0), numDirOptMatched));

    if (penalizeUmap) {
      cost = addCost(cost, mulCost(createCost(0, 1, 1), ppc));
    }
  }

  return cost;
};

const getMappingFcostGlobal = (interfaceObj, busDef) => {
  const baseCost = getMappingFcostBase(interfaceObj, busDef, true);
  const nameCost = getNameFcost1(interfaceObj, busDef);
  return createCost(nameCost * interfaceObj.size, baseCost.wc, baseCost.dc);
};

const getMappingFcostLocal = (interfaceObj, busDef) => {
  const baseCost = getMappingFcostBase(interfaceObj, busDef, false);
  const nameCost = getNameFcost2(interfaceObj, busDef);
  return createCost(nameCost, baseCost.wc, baseCost.dc);
};

const getCostFuncs = (interfaceObj, busDef) => {
  const dupWords = getDupWords(interfaceObj.ports);

  const matchCostFunc = (phyPort, busPort) => {
    const pWords = new Set();
    for (const w of wordsFromName(phyPort[0])) {
      if (!dupWords.has(w)) {
        pWords.add(w);
      }
    }
    const bWords = busDef.wordsFromName(busPort[0]);
    const costN = getJaccardDist(pWords, bWords);

    const widthMismatch = (phyPort[1] !== busPort[1]) && (phyPort[1] !== null && busPort[1] !== null);
    const dirMismatch = phyPort[2] !== busPort[2];

    return createCost(
      costN,
      widthMismatch ? 1 : 0,
      dirMismatch ? 1 : 0
    );
  };

  const mappingCostFunc = (bm, penalizeUmap) => {
    let cost = zeroCost();
    for (const [pp, bp] of bm.mapping) {
      cost = addCost(cost, matchCostFunc(pp, bp));
    }
    if (penalizeUmap) {
      const sbmCount = Object.keys(bm.sideband_mapping).length;
      cost = addCost(cost, mulCost(createCost(0, 1, 1), sbmCount));
    }

    const mappedBusPorts = new Set(bm.mapping.map(item => item[1]));
    let umapBusReqCount = 0;
    for (const bp of bm.bus_def.req_ports) {
      if (!mappedBusPorts.has(bp)) {
        umapBusReqCount++;
      }
    }
    cost = addCost(cost, mulCost(createCost(0, 1, 1), umapBusReqCount));
    return cost;
  };

  return { matchCostFunc, mappingCostFunc };
};

const median = (values) => {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) {
    return sorted[mid];
  }
  return (sorted[mid - 1] + sorted[mid]) / 2;
};

const getSidebandPorts = (mapping, ports) => {
  const numMissingTokens = mapping.map(([pp, bp]) => getNumMissingTokens(bp[0], pp[0]));
  const cutoff = median(numMissingTokens) + 1;

  const sidebandPorts = new Set();
  for (const [pp, bp] of mapping) {
    if (getNumMissingTokens(bp[0], pp[0]) > cutoff) {
      sidebandPorts.add(pp);
    }
  }

  const mappedPhyPorts = new Set(mapping.map(item => item[0]));
  for (const p of ports) {
    if (!mappedPhyPorts.has(p)) {
      sidebandPorts.add(p);
    }
  }

  return sidebandPorts;
};

const getUserGroupAssignment = (interfaceObj, ports, busDef) => {
  const sprefix = interfaceObj.prefix;
  const bdUserPortGroups = busDef.user_port_groups;
  if (bdUserPortGroups.length === 0) {
    return { userGroupMapping: new Map(), unmappedPorts: Array.from(ports) };
  }

  const getUserGroupPort = (port) => {
    const remainder = port[0].slice(sprefix.length);
    for (const w of wordsFromName(remainder)) {
      for (const [prefix, uport] of bdUserPortGroups) {
        if (w.startsWith(prefix) && port[2] === uport[2]) {
          return uport;
        }
      }
    }
    return null;
  };

  const userGroupMapping = new Map();
  const unmappedPorts = [];

  for (const port of ports) {
    const uport = getUserGroupPort(port);
    if (uport === null) {
      unmappedPorts.push(port);
    } else {
      if (!userGroupMapping.has(uport)) {
        userGroupMapping.set(uport, []);
      }
      userGroupMapping.get(uport).push(port);
    }
  }

  return { userGroupMapping, unmappedPorts };
};

const createBusMapping = (options = {}) => {
  const mapping = options.mapping || [];
  const sidebandMapping = options.sideband_mapping || {};
  const mapDict = new Map();
  for (const [pp, bp] of mapping) {
    mapDict.set(pp, bp);
  }

  return {
    cost: options.cost || null,
    fcost: options.fcost || null,
    mapping,
    m: mapDict,
    sideband_mapping: sidebandMapping,
    sbm: sidebandMapping,
    user_group_mapping: options.user_group_mapping || new Map(),
    unmapped_ports: options.unmapped_ports || [],
    umap: options.unmapped_ports || [],
    match_cost_func: options.match_cost_func || null,
    mc_func: options.match_cost_func || null,
    bus_def: options.bus_def || null,
    get_ports: () => {
      const ports = new Set(mapping.map(item => item[0]));
      for (const pp of Object.values(sidebandMapping)) {
        if (pp) ports.add(pp);
      }
      return ports;
    }
  };
};

const mapPortsToBus = (interfaceObj, busDef, penalizeUmap = true) => {
  const { matchCostFunc, mappingCostFunc } = getCostFuncs(interfaceObj, busDef);

  const ports = interfaceObj.get_ports_to_map();
  const ports1 = [...ports];
  const ports2 = [...busDef.req_ports, ...busDef.opt_ports];

  const m = ports1.length;
  const n = ports2.length;
  const C = [];
  for (let i = 0; i < m; i++) {
    C.push(new Array(n));
    for (let j = 0; j < n; j++) {
      C[i][j] = matchCostFunc(ports1[i], ports2[j]).value;
    }
  }

  const assigned = solveAssignment(C);
  let mapping = assigned.map(([i, j]) => [ports1[i], ports2[j]]);

  const sidebandPorts = getSidebandPorts(mapping, ports);

  const sidebandMapping = {};
  for (const [pp, bp] of mapping) {
    if (sidebandPorts.has(pp)) {
      sidebandMapping[pp[0]] = bp;
    }
  }
  for (const p of sidebandPorts) {
    if (!(p[0] in sidebandMapping)) {
      sidebandMapping[p[0]] = null;
    }
  }

  mapping = mapping.filter(([pp]) => !sidebandPorts.has(pp));

  const { userGroupMapping, unmappedPorts } = getUserGroupAssignment(
    interfaceObj,
    sidebandPorts,
    busDef
  );

  const busMapping = createBusMapping({
    mapping,
    sideband_mapping: sidebandMapping,
    user_group_mapping: userGroupMapping,
    unmapped_ports: unmappedPorts,
    match_cost_func: matchCostFunc,
    bus_def: busDef
  });

  const rawCost = mappingCostFunc(busMapping, penalizeUmap);
  busMapping.cost = normalizeCost(rawCost, ports.length);

  return busMapping;
};

module.exports = {
  getDupWords,
  getPortWords,
  getNameFcost1,
  getNameFcost2,
  getMappingFcostBase,
  getMappingFcostGlobal,
  getMappingFcostLocal,
  getCostFuncs,
  getSidebandPorts,
  getUserGroupAssignment,
  createBusMapping,
  mapPortsToBus
};
