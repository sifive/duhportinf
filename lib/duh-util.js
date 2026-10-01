'use strict';

/**
 * Convert component ports shorthand or array to:
 * Array of [port_name, width (number|null), direction (+1|-1)]
 * @param {object|Array} inPorts
 * @returns {Array<[string, number|null, number]>}
 */
function formatPorts(inPorts) {
  const fmtPorts = [];
  if (!inPorts) return fmtPorts;

  if (Array.isArray(inPorts)) {
    for (const port of inPorts) {
      if (!port || typeof port !== 'object') continue;
      const name = port.name;
      const wire = port.wire !== undefined ? port.wire : port;
      fmtPorts.push(parsePortWire(name, wire));
    }
    return fmtPorts;
  }

  if (typeof inPorts === 'object') {
    for (const [name, pw] of Object.entries(inPorts)) {
      fmtPorts.push(parsePortWire(name, pw));
    }
  }
  return fmtPorts;
}

function parsePortWire(name, pw) {
  let width = null;
  let direction = 1;

  if (typeof pw === 'number') {
    if (pw < 0) {
      width = -pw;
      direction = -1;
    } else {
      width = pw;
      direction = 1;
    }
  } else if (typeof pw === 'string') {
    if (pw.startsWith('-')) {
      width = null;
      direction = -1;
    } else {
      width = null;
      direction = 1;
    }
  } else if (pw && typeof pw === 'object') {
    const wire = pw.wire !== undefined ? pw.wire : pw;
    if (typeof wire.width === 'number' && Number.isInteger(wire.width)) {
      width = Math.abs(wire.width);
    } else {
      width = null;
    }
    direction = (wire.direction === 'out') ? -1 : 1;
  }
  return [name, width, direction];
}

/**
 * Synchronous local JSON Pointer resolver with cycle detection.
 * Resolves local refs such as "#/definitions/ports".
 * @param {any} root
 * @returns {any}
 */
function resolveJsonRefs(root) {
  const resolving = new Set();

  function resolvePointer(ptr) {
    if (!ptr.startsWith('#/')) {
      return null;
    }
    const parts = ptr.slice(2).split('/').map(segment => segment.replace(/~1/g, '/').replace(/~0/g, '~'));
    let curr = root;
    for (const part of parts) {
      if (curr && typeof curr === 'object' && part in curr) {
        curr = curr[part];
      } else {
        return null;
      }
    }
    return curr;
  }

  function walk(node) {
    if (!node || typeof node !== 'object') {
      return node;
    }

    if (node.$ref && typeof node.$ref === 'string') {
      const ref = node.$ref;
      if (ref.startsWith('#/')) {
        if (resolving.has(ref)) {
          return node; // cycle guard
        }
        resolving.add(ref);
        const target = resolvePointer(ref);
        const resolved = target ? walk(target) : node;
        resolving.delete(ref);
        return resolved;
      }
      return node;
    }

    if (Array.isArray(node)) {
      return node.map(item => walk(item));
    }

    const copy = {};
    for (const [k, v] of Object.entries(node)) {
      copy[k] = walk(v);
    }
    return copy;
  }

  return walk(root);
}

function getBundlePorts(tree) {
  const ports = [];
  if (!tree || typeof tree !== 'object') return ports;
  for (const v of Object.values(tree)) {
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      ports.push(...getBundlePorts(v));
    } else if (Array.isArray(v)) {
      ports.push(...v);
    } else if (typeof v === 'string') {
      ports.push(v);
    }
  }
  return ports;
}

/**
 * Extract unassigned ports from a DUH component object.
 * @param {object} componentDoc
 * @returns {Array<[string, number|null, number]>}
 */
function getUnassignedPorts(componentDoc) {
  const resolved = resolveJsonRefs(componentDoc);
  const component = resolved.component || resolved;

  const rawPorts = component.model?.ports || component.ports || {};
  const allPorts = formatPorts(rawPorts);

  const busInterfaces = component.busInterfaces || [];

  function getPortnames(iface) {
    const atkey = 'abstractionTypes';
    const pmkey = 'portMaps';
    const vkey = 'viewRef';

    const pns = [];
    const absTypes = iface[atkey] || [];

    for (const at of absTypes) {
      if (at[vkey] === 'RTLview' && at[pmkey]) {
        if (iface.busType === 'bundle') {
          pns.push(...getBundlePorts(at[pmkey]));
        } else {
          for (const val of Object.values(at[pmkey])) {
            if (Array.isArray(val)) {
              pns.push(...val);
            } else if (typeof val === 'string') {
              pns.push(val);
            }
          }
        }
      }
    }
    return new Set(pns);
  }

  const seen = new Set();
  const dups = new Set();

  for (const iface of busInterfaces) {
    const pns = getPortnames(iface);
    for (const p of pns) {
      if (seen.has(p)) {
        dups.add(p);
      }
      seen.add(p);
    }
  }

  if (dups.size > 0) {
    process.stderr.write('ports illegally belong to multiple bus interfaces:\n');
    const sortedDups = Array.from(dups).sort().slice(0, 10);
    for (const p of sortedDups) {
      process.stderr.write(`  - ${p}\n`);
    }
    if (dups.size > 10) {
      process.stderr.write('  ...\n');
    }
  }

  return allPorts.filter(p => !seen.has(p[0]));
}

let silent = false;

function setSilent(val) {
  silent = Boolean(val);
}

function progressBar(iteration, total, options = {}) {
  if (silent) return;
  const prefix = options.prefix || 'Progress:';
  const suffix = options.suffix || 'Complete';
  const decimals = options.decimals !== undefined ? options.decimals : 1;
  const length = options.length || 40;
  const fill = options.fill || 'x';

  const percent = (100 * (iteration / Math.max(1, total))).toFixed(decimals);
  const filledLength = Math.round((length * iteration) / Math.max(1, total));
  const bar = fill.repeat(filledLength) + '-'.repeat(Math.max(0, length - filledLength));
  const line = `\r${prefix} |${bar}| ${percent}% ${suffix}`;

  process.stderr.write(line);
  if (iteration >= total) {
    process.stderr.write(`\r${' '.repeat(line.length)}\r`);
  }
}

module.exports = {
  formatPorts,
  resolveJsonRefs,
  getUnassignedPorts,
  progressBar,
  setSilent
};
