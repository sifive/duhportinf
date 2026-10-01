'use strict';

const {
  createBusDef,
  busWordsFromName,
  formatBusDef,
  parsePort,
  busDefsFromSpec,
  loadBusDefsFromCatalog,
} = require('./lib/busdef');

const {
  createInterface,
  mergeInterfaces,
  createBundle,
  createTreeNode,
  createBundleTree,
  getInitialInterfaces,
  getOptimalNids,
  getBundles,
} = require('./lib/bundle');

const {
  NAME_W,
  WIDTH_W,
  DIR_W,
  costValue,
  createCost,
  zeroCost,
  duplicateCost,
  normalizeCost,
  addCost,
  subCost,
  mulCost,
  compareCost,
  isCostLess,
  eqCost,
  formatCost,
} = require('./lib/match-cost');

const {
  formatPorts,
  getUnassignedPorts,
  resolveJsonRefs,
  progressBar,
  setSilent,
} = require('./lib/duh-util');

const {
  getLowFcostBusDefs,
  getBusPairings,
  getInitialBusMatches,
  getBusMatches,
  dumpJsonBusCandidates,
} = require('./lib/infer');

const { bundlePorts, dumpJsonBundles } = require('./lib/bundler');
const { loadBusDefsFromDir, loadDefaultBusDefs } = require('./lib/loader');
const {
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
  mapPortsToBus,
} = require('./lib/optimize');

module.exports = {
  // BusDef
  createBusDef,
  busWordsFromName,
  formatBusDef,
  parsePort,
  busDefsFromSpec,
  loadBusDefsFromCatalog,

  // Bundle / Interface
  createInterface,
  mergeInterfaces,
  createBundle,
  createTreeNode,
  createBundleTree,
  getInitialInterfaces,
  getOptimalNids,
  getBundles,

  // Cost
  NAME_W,
  WIDTH_W,
  DIR_W,
  costValue,
  createCost,
  zeroCost,
  duplicateCost,
  normalizeCost,
  addCost,
  subCost,
  mulCost,
  compareCost,
  isCostLess,
  eqCost,
  formatCost,

  // DUH Util
  formatPorts,
  getUnassignedPorts,
  resolveJsonRefs,
  progressBar,
  setSilent,

  // Optimize
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
  mapPortsToBus,

  // Inference & Bundling
  getLowFcostBusDefs,
  getBusPairings,
  getInitialBusMatches,
  getBusMatches,
  dumpJsonBusCandidates,
  bundlePorts,
  dumpJsonBundles,
  loadBusDefsFromDir,
  loadDefaultBusDefs,
};
