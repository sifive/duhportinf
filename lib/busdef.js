'use strict';

const { wordsFromName } = require('./tokenize');

const busWordsFromName = (portName) => wordsFromName(portName).map(w => w.toLowerCase());

const createBusDef = (
  busType = {},
  abstractType = {},
  driverType = 'master',
  reqPorts = [],
  optPorts = [],
  userPortGroups = []
) => {
  const normalizedUserGroups = userPortGroups.map(([p, pp]) => [p.toLowerCase(), pp]);
  const req = [...reqPorts];
  const opt = [...optPorts];

  return Object.freeze({
    bus_type: busType,
    abstract_type: abstractType,
    driver_type: driverType,
    req_ports: req,
    opt_ports: opt,
    user_port_groups: normalizedUserGroups,
    all_ports: [...req, ...opt],
    num_req_ports: req.length,
    num_opt_ports: opt.length,
    isInitiator: driverType === 'master' || driverType === 'initiator',
    isTarget: driverType === 'slave' || driverType === 'target',
    wordsFromName: busWordsFromName
  });
};

const formatBusDef = (busDef) => (
  `bus_def{\n\tbus_type:${JSON.stringify(busDef.bus_type)},\n\tabstract_type:${JSON.stringify(busDef.abstract_type)},\n\tdriver_type:${busDef.driver_type},\n\tnum_req:${busDef.num_req_ports},\n\tnum_opt:${busDef.num_opt_ports},\n}`
);

const parsePort = (portname, portdef = {}) => {
  const isUser = Boolean(portdef.isUser);
  const userGroup = portdef.group ? String(portdef.group).toLowerCase() : '';

  const reqPortMap = {};
  const optPortMap = {};

  const wire = portdef.wire;
  if (!wire || typeof wire !== 'object') {
    return { isUser, userGroup, reqPortMap, optPortMap };
  }

  const roleKeys = ['onInitiator', 'onMaster', 'onTarget', 'onSlave'];

  for (const roleKey of roleKeys) {
    if (!(roleKey in wire)) continue;
    const subportdef = wire[roleKey];
    if (!subportdef || typeof subportdef !== 'object') continue;
    if (subportdef.presence === 'illegal') continue;

    let width = null;
    if (typeof subportdef.width === 'number' && Number.isInteger(subportdef.width)) {
      width = subportdef.width;
    }

    const direction = subportdef.direction === 'in' ? 1 : -1;
    const desc = [portname, width, direction];

    if (!subportdef.presence || subportdef.presence === 'required') {
      reqPortMap[roleKey] = desc;
    } else if (subportdef.presence === 'optional') {
      optPortMap[roleKey] = desc;
    }
  }

  return { isUser, userGroup, reqPortMap, optPortMap };
};

const validateUserGroups = (userGroups) => {
  if (userGroups.length <= 1) return;
  if (userGroups.some(g => g === '')) {
    throw new Error(`Cannot have empty user group when multiple specified: ${userGroups}`);
  }
  for (let i = 0; i < userGroups.length; i++) {
    for (let j = i + 1; j < userGroups.length; j++) {
      const p1 = userGroups[i];
      const p2 = userGroups[j];
      if (p1.startsWith(p2) || p2.startsWith(p1)) {
        throw new Error(`Ambiguous user_groups specified: ${userGroups}`);
      }
    }
  }
};

const busDefsFromSpec = (spec = {}) => {
  const ad = spec.abstractionDefinition;
  if (!ad || typeof ad !== 'object') {
    return [];
  }

  const busType = ad.busType || {};
  const abstractType = {
    vendor: ad.vendor,
    library: ad.library,
    name: ad.name,
    version: ad.version
  };

  const initiatorReqPorts = [];
  const initiatorOptPorts = [];
  const initiatorUserPortGroups = [];

  const targetReqPorts = [];
  const targetOptPorts = [];
  const targetUserPortGroups = [];

  const userGroups = [];
  let usesModernRoles = false;

  const ports = ad.ports || {};
  for (const [portname, portdef] of Object.entries(ports)) {
    const { isUser, userGroup, reqPortMap, optPortMap } = parsePort(portname, portdef);

    if (isUser && userGroup) {
      userGroups.push(userGroup);
    }

    // Initiator / Master
    const initReq = reqPortMap.onInitiator || reqPortMap.onMaster;
    const initOpt = optPortMap.onInitiator || optPortMap.onMaster;
    if ('onInitiator' in reqPortMap || 'onInitiator' in optPortMap) usesModernRoles = true;

    if (initReq) initiatorReqPorts.push(initReq);
    if (initOpt) {
      if (isUser) {
        initiatorUserPortGroups.push([userGroup, initOpt]);
      } else {
        initiatorOptPorts.push(initOpt);
      }
    }

    // Target / Slave
    const tgtReq = reqPortMap.onTarget || reqPortMap.onSlave;
    const tgtOpt = optPortMap.onTarget || optPortMap.onSlave;
    if ('onTarget' in reqPortMap || 'onTarget' in optPortMap) usesModernRoles = true;

    if (tgtReq) targetReqPorts.push(tgtReq);
    if (tgtOpt) {
      if (isUser) {
        targetUserPortGroups.push([userGroup, tgtOpt]);
      } else {
        targetOptPorts.push(tgtOpt);
      }
    }
  }

  validateUserGroups(userGroups);

  const initRoleName = usesModernRoles ? 'initiator' : 'master';
  const tgtRoleName = usesModernRoles ? 'target' : 'slave';

  const busDefs = [];
  if (initiatorReqPorts.length > 0) {
    busDefs.push(
      createBusDef(
        busType,
        abstractType,
        initRoleName,
        initiatorReqPorts,
        initiatorOptPorts,
        initiatorUserPortGroups
      )
    );
  }
  if (targetReqPorts.length > 0) {
    busDefs.push(
      createBusDef(
        busType,
        abstractType,
        tgtRoleName,
        targetReqPorts,
        targetOptPorts,
        targetUserPortGroups
      )
    );
  }

  return busDefs;
};

const loadBusDefsFromCatalog = (catalog) => {
  const busDefs = [];
  const walk = (obj) => {
    if (!obj || typeof obj !== 'object') return;
    if (obj.abstractionDefinition) {
      busDefs.push(...busDefsFromSpec(obj));
      return;
    }
    for (const val of Object.values(obj)) {
      walk(val);
    }
  };
  walk(catalog);
  return busDefs;
};

module.exports = {
  createBusDef,
  busWordsFromName,
  formatBusDef,
  parsePort,
  busDefsFromSpec,
  loadBusDefsFromCatalog
};
