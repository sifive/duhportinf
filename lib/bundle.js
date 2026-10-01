'use strict';

const { commonPrefix, isRange, wordsFromName } = require('./tokenize');

let nextNodeId = 0;

const resetNodeId = () => { nextNodeId = 0; };

const createInterface = (ports = [], vectors = []) => {
  const vkeyMapportMap = new Map();
  const vkeyVectorMap = new Map();
  for (const v of vectors) {
    const vkey = commonPrefix(v.map(p => p[0]));
    const [, w, d] = v[0];
    vkeyMapportMap.set(vkey, [vkey, w, d]);
    vkeyVectorMap.set(vkey, v);
  }

  const allPorts = [...ports];
  for (const v of vectors) {
    allPorts.push(...v);
  }

  return Object.freeze({
    ports: [...ports],
    vectors: [...vectors],
    size: ports.length + vectors.length,
    all_ports: allPorts,
    prefix: commonPrefix(allPorts.map(p => p[0])),
    get_ports_to_map: () => [...ports, ...vkeyMapportMap.values()],
    is_vector: (vkey) => vkeyMapportMap.has(vkey),
    get_vector: (vkey) => vkeyVectorMap.get(vkey)
  });
};

const mergeInterfaces = (...inters) => {
  const ports = [];
  const vectors = [];
  for (const inter of inters) {
    if (inter) {
      ports.push(...inter.ports);
      vectors.push(...inter.vectors);
    }
  }
  return createInterface(ports, vectors);
};

const createBundle = (tree, name) => Object.freeze({ tree, name });

const createTreeNode = (parent = null) => ({
  id: nextNodeId++,
  parent,
  children: new Map(),
  port: null,
  is_vector: false,
  vports: [],
  interface: null
});

const isLeafNode = (node) => node.children.size === 0;

const isPassthruNode = (node) => (
  node.children.size === 1 && !node.port && !node.is_vector
);

const getPassthruChild = (node) => {
  const firstChild = node.children.values().next().value;
  return firstChild;
};

const isSingletonPath = (node) => {
  if (isLeafNode(node)) return true;
  if (node.children.size > 1) return false;
  return isSingletonPath(getPassthruChild(node));
};

const getContainedPorts = (node) => {
  const ports = [];
  if (node.port) ports.push(node.port);
  for (const child of node.children.values()) {
    ports.push(...getContainedPorts(child));
  }
  return ports;
};

const tagNodeAsVector = (node, vports) => {
  node.is_vector = true;
  node.vports = vports;
  for (const ptr of Array.from(node.children.keys())) {
    if (/^\d+$/.test(ptr)) {
      node.children.delete(ptr);
    }
  }
};

const getChildNode = (node, ptr) => {
  if (!node.children.has(ptr)) {
    const child = createTreeNode(node);
    node.children.set(ptr, child);
  }
  return node.children.get(ptr);
};

const updateTreeNode = (target, source) => {
  if (source.port) {
    target.port = source.port;
  }
  for (const [ptr, srcChild] of source.children.entries()) {
    const tgtChild = getChildNode(target, ptr);
    updateTreeNode(tgtChild, srcChild);
  }
};

const setNodeInterface = (node) => {
  let cinter = null;
  if (node.is_vector) {
    cinter = createInterface([], [[...node.vports]]);
  } else if (node.port) {
    cinter = createInterface([node.port], []);
  }

  const childInters = Array.from(node.children.values()).map(n => n.interface);
  node.interface = mergeInterfaces(...childInters);
  if (cinter) {
    node.interface = mergeInterfaces(node.interface, cinter);
  }
  return node.interface;
};

const treeNodeAsDict = (node, nameOnly = false) => {
  const fmtVector = v => (nameOnly ? v.map(p => p[0]) : v.map(p => [...p]));
  const fmtPort = p => (nameOnly ? p[0] : [...p]);

  if (isLeafNode(node) && node.is_vector) {
    return fmtVector(node.vports);
  }
  if (isLeafNode(node)) {
    return fmtPort(node.port);
  }

  const d = {};
  for (const [ptr, child] of node.children.entries()) {
    d[ptr] = treeNodeAsDict(child, nameOnly);
  }
  if (node.port) {
    d._ = fmtPort(node.port);
  }
  if (node.is_vector) {
    d._ = fmtVector(node.vports);
  }
  return d;
};

const postOrderTraversal = (node, func = (n => n.id), visitLeaf = true) => {
  const stack = [node];
  const visited = new Set();
  const result = [];

  while (stack.length > 0) {
    const curr = stack[stack.length - 1];
    if (isLeafNode(curr)) {
      stack.pop();
      if (visitLeaf) {
        result.push(func(curr));
      }
    } else if (visited.has(curr.id)) {
      result.push(func(curr));
      stack.pop();
    } else {
      visited.add(curr.id);
      for (const child of curr.children.values()) {
        stack.push(child);
      }
    }
  }
  return result;
};

const subtreeFromPort = (port) => {
  const name = port[0];
  const words = wordsFromName(name);
  const nodes = [];
  for (let i = 0; i <= words.length; i++) {
    nodes.push(createTreeNode());
  }
  nodes[nodes.length - 1].port = port;
  for (let i = 0; i < words.length; i++) {
    nodes[i].children.set(words[i], nodes[i + 1]);
    nodes[i + 1].parent = nodes[i];
  }
  return nodes[0];
};

const formatVectors = (rootNode) => {
  const getVecInfo = (node) => {
    const dptrs = Array.from(node.children.keys()).filter(ptr => /^\d+$/.test(ptr));
    if (dptrs.length < 2) return [false, []];

    const digits = dptrs.map(Number);
    if (!isRange(digits)) return [false, []];

    for (const ptr of dptrs) {
      if (!isSingletonPath(node.children.get(ptr))) {
        return [false, []];
      }
    }

    const ptrPorts = dptrs.map(ptr => {
      const contained = getContainedPorts(node.children.get(ptr));
      return [parseInt(ptr, 10), contained[0]];
    });
    ptrPorts.sort((a, b) => a[0] - b[0]);
    const vports = ptrPorts.map(item => item[1]);

    const widthSet = new Set(vports.map(p => p[1]));
    const dirSet = new Set(vports.map(p => p[2]));
    const isVector = widthSet.size === 1 && dirSet.size === 1;
    return [isVector, vports];
  };

  const stack = [[null, null, rootNode]];
  while (stack.length > 0) {
    const [, , curr] = stack.shift();
    const [isVector, vports] = getVecInfo(curr);
    if (isVector) {
      tagNodeAsVector(curr, vports);
    }
    for (const [ptr, child] of curr.children.entries()) {
      if (!isLeafNode(child)) {
        stack.unshift([curr, ptr, child]);
      }
    }
  }
};

const flattenPassthruPaths = (rootNode) => {
  const stack = [[null, null, rootNode]];
  while (stack.length > 0) {
    const [parent, pkey, curr] = stack.shift();
    if (parent !== null && isPassthruNode(curr)) {
      const ckey = curr.children.keys().next().value;
      const child = curr.children.get(ckey);
      const newKey = `${pkey}_${ckey}`;
      parent.children.delete(pkey);
      parent.children.set(newKey, child);
      child.parent = parent;
      if (!isLeafNode(child)) {
        stack.unshift([parent, newKey, child]);
      }
    } else {
      for (const [ptr, child] of curr.children.entries()) {
        if (!isLeafNode(child)) {
          stack.unshift([curr, ptr, child]);
        }
      }
    }
  }
};

const getInitialInterfaces = (bundleTree, minSize = 4, maxSize = null) => {
  const rootLeaves = Array.from(bundleTree.rootNode.children.values()).filter(isLeafNode);
  const abbrRootInterface = mergeInterfaces(...rootLeaves.map(n => n.interface));
  const rootnid = bundleTree.rootNode.id;

  const list = [];
  postOrderTraversal(bundleTree.rootNode, (n) => {
    const nid = n.id;
    const inter = n.interface;
    if (nid === rootnid && inter.size >= 100) {
      list.push([nid, abbrRootInterface]);
    } else if (
      inter.size >= minSize &&
      (maxSize === null || inter.size <= maxSize)
    ) {
      list.push([nid, inter]);
    }
  });
  return list;
};

const getOptimalNids = (bundleTree, nidCostMap, minNumLeaves = 4) => {
  const ninfo = postOrderTraversal(bundleTree.rootNode, (n) => ({ node: n, isLeaf: isLeafNode(n) }));
  const leafNodes = ninfo.filter(item => item.isLeaf).map(item => item.node);

  const optNodeCounts = new Map();
  for (const leaf of leafNodes) {
    let curr = leaf;
    const costs = [];
    while (curr.parent !== null) {
      const cost = (curr.id in nidCostMap) ? nidCostMap[curr.id] : undefined;
      if (cost !== undefined && cost !== null) {
        costs.push({ cost, node: curr });
      }
      curr = curr.parent;
    }

    if (costs.length > 0) {
      let minVal = Infinity;
      for (const item of costs) {
        const val = typeof item.cost === 'object' && item.cost !== null ? item.cost.value : Number(item.cost);
        if (val < minVal) {
          minVal = val;
        }
      }
      const optNodes = costs.filter(item => {
        const val = typeof item.cost === 'object' && item.cost !== null ? item.cost.value : Number(item.cost);
        return val === minVal;
      }).map(item => item.node);

      for (const optNode of optNodes) {
        optNodeCounts.set(optNode, (optNodeCounts.get(optNode) || 0) + 1);
      }
    }
  }

  if (optNodeCounts.size === 0) {
    return new Set([bundleTree.rootNode.id]);
  }

  let optNids = new Set();
  for (let t = minNumLeaves - 1; t >= 0; t--) {
    const candidates = [];
    for (const [node, count] of optNodeCounts.entries()) {
      if (count > t) {
        candidates.push(node.id);
      }
    }
    if (candidates.length > 0) {
      optNids = new Set(candidates);
      break;
    }
  }
  return optNids;
};

const getBundles = (bundleTree) => {
  const bundles = [];
  for (const [ptr, n] of bundleTree.rootNode.children.entries()) {
    if (!isLeafNode(n)) {
      bundles.push(createBundle(treeNodeAsDict(n, true), ptr));
    }
  }

  const rootTree = treeNodeAsDict(bundleTree.rootNode, true);
  for (const [ptr, n] of bundleTree.rootNode.children.entries()) {
    if (!isLeafNode(n)) {
      delete rootTree[ptr];
    }
  }
  if (Object.keys(rootTree).length > 0) {
    bundles.push(createBundle(rootTree, 'root'));
  }
  return bundles;
};

const createBundleTree = (ports = []) => {
  const portList = Array.from(ports);
  let rootNode = createTreeNode();

  for (const port of portList) {
    updateTreeNode(rootNode, subtreeFromPort(port));
  }
  formatVectors(rootNode);
  flattenPassthruPaths(rootNode);

  let treeName = 'root';
  if (
    rootNode.children.size === 1 &&
    portList.length > 1
  ) {
    const firstKey = rootNode.children.keys().next().value;
    const firstChild = rootNode.children.get(firstKey);
    if (!firstChild.is_vector) {
      treeName = firstKey.replace(/^_+|_+$/g, '');
      firstChild.parent = null;
      rootNode = firstChild;
    }
  }

  // Set interfaces bottom-up
  postOrderTraversal(rootNode, setNodeInterface);

  const treeObj = {
    tree: treeNodeAsDict(rootNode),
    name: treeName,
    size: portList.length,
    ports: portList,
    rootNode
  };

  treeObj.get_initial_interfaces = (minSize = 4, maxSize = null) => (
    getInitialInterfaces(treeObj, minSize, maxSize)
  );
  treeObj.get_optimal_nids = (nidCostMap, minNumLeaves = 4) => (
    getOptimalNids(treeObj, nidCostMap, minNumLeaves)
  );
  treeObj.get_bundles = () => getBundles(treeObj);

  return Object.freeze(treeObj);
};

module.exports = {
  resetNodeId,
  createInterface,
  mergeInterfaces,
  createBundle,
  createTreeNode,
  isLeafNode,
  isPassthruNode,
  treeNodeAsDict,
  postOrderTraversal,
  createBundleTree,
  getInitialInterfaces,
  getOptimalNids,
  getBundles
};
