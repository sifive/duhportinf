'use strict';

const NAME_W = 2;
const WIDTH_W = 1;
const DIR_W = 4;

const costValue = (c = {}) => (
  NAME_W * (c.nc || 0) + WIDTH_W * (c.wc || 0) + DIR_W * (c.dc || 0)
);

const createCost = (nc = 0, wc = 0, dc = 0) => {
  const c = { nc, wc, dc };
  // cache value for fast access without getters/OOP
  c.value = costValue(c);
  return Object.freeze(c);
};

const zeroCost = () => createCost(0, 0, 0);

const duplicateCost = (c = {}) => createCost(c.nc, c.wc, c.dc);

const normalizeCost = (c, n) => {
  const divisor = n > 0 ? n : 1;
  return createCost(c.nc / divisor, c.wc, c.dc);
};

const addCost = (c1, c2) => {
  if (typeof c2 === 'number') {
    return createCost(c1.nc + c2, c1.wc + c2, c1.dc + c2);
  }
  return createCost(c1.nc + c2.nc, c1.wc + c2.wc, c1.dc + c2.dc);
};

const subCost = (c1, c2) => {
  if (typeof c2 === 'number') {
    return createCost(c1.nc - c2, c1.wc - c2, c1.dc - c2);
  }
  return createCost(c1.nc - c2.nc, c1.wc - c2.wc, c1.dc - c2.dc);
};

const mulCost = (c, scalar) => createCost(c.nc * scalar, c.wc * scalar, c.dc * scalar);

const compareCost = (c1, c2) => {
  const v1 = typeof c1 === 'object' && c1 !== null ? c1.value : Number(c1);
  const v2 = typeof c2 === 'object' && c2 !== null ? c2.value : Number(c2);
  return v1 - v2;
};

const isCostLess = (c1, c2) => compareCost(c1, c2) < 0;

const eqCost = (c1, c2) => {
  if (!c1 || !c2) return c1 === c2;
  return c1.nc === c2.nc && c1.wc === c2.wc && c1.dc === c2.dc;
};

const formatCost = c => (
  `${c.value.toFixed(2)}(n:${c.nc.toFixed(2)};w:${c.wc};d:${c.dc})`
);

module.exports = {
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
  formatCost
};
