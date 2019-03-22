import copy
import json
import collections
from collections import deque, defaultdict, Counter
from itertools import chain
from . import util

def is_range(keys):
    if not all([k.isdigit() for k in keys]):
        return False
    idx = [int(k) for k in keys]
    return util.is_range(idx)

class Interface(object):
    @property
    def size(self):
        # only count vector ports as width one
        return len(self.ports) + len(self.vectors)
    @classmethod
    def merge(cls, *inters):
        ports = util.flatten([inter.ports for inter in inters])
        vectors = util.flatten([inter.vectors for inter in inters])
        return cls(ports, vectors)
    @property
    def all_ports(self):
        return chain(self.ports, util.flatten(self.vectors))
    @property
    def prefix(self):
        assert self.ports is not None
        return util.common_prefix([p[0] for p in self.all_ports])

    def __init__(self, ports, vectors):
        assert ports is not None
        assert vectors is not None
        self.ports = ports
        self.vectors = vectors
        # <vector port name prefix>: <mapping port>
        self._vkey_mapport_map = {}
        # <vector port name prefix>: <vector>
        self._vkey_vector_map = {}
        for v in self.vectors:
            vkey = util.common_prefix([p[0] for p in v])
            assert len(vkey) > 0
            _, w, d = next(iter(v))
            self._vkey_mapport_map[vkey] = (vkey, w, d)
            self._vkey_vector_map[vkey] = v

    def get_ports_to_map(self):
        return set(chain(self.ports, self._vkey_mapport_map.values()))

    def is_vector(self, vkey):
        return vkey in self._vkey_mapport_map

    def get_vector(self, vkey):
        return self._vkey_vector_map[vkey]

class Bundle(object):
    def __init__(self, tree, name):
        self.tree = tree
        self.name = name

class BundleTreeNode(object):
    id_gen = util.get_id_gen()
        
    @property
    def id(self): return self._id
    @property
    def children_refs(self): return iter(self._children_refs.items())
    @property
    def ptrs(self): return self._children_refs.keys()
    @property
    def children(self): return self._children_refs.values()
    @property
    def parent(self): return self._parent
    @property
    def port(self): return self._port
    @property
    def passkey(self):
        assert len(self) == 1 
        return next(iter(self.ptrs))
    @property
    def passthru(self):
        assert len(self) == 1 
        return self.get_child(self.passkey)
    @property
    def is_leaf(self):
        # FIXME probably not fully implemented yet
        return len(self) == 0
    @property
    def is_vector(self): return self._is_vector
    @property
    def vports(self): return iter(self._vports)
    @property
    def interface(self): return self._interface

    def __init__(
        self,
        parent=None,
    ):
        self._id = next(self.id_gen)
        self._parent = parent
        self._children_refs = defaultdict(
            lambda: BundleTreeNode(parent=self),
        )
        # specific to this node
        self._port = None
        self._is_vector = False
        self._vports = []

        # compiled from the ports specified in this node and all
        # descendent nodes, after the bundle tree is created
        self._interface = None

    def set_interface(self):
        # all children of non-vector nodes should have their interface set
        assert (
            (self.is_leaf or self.is_vector) or
            all([(n.interface is not None) for n in self.children])
        )
        cinter = None
        if self.is_vector:
            cinter = Interface([], [list(self.vports)])
        elif self.port:
            cinter = Interface([self.port], [])
        self._interface = Interface.merge(*[n.interface for n in self.children])
        if cinter:
            self._interface = Interface.merge(self._interface, cinter)
        return self._interface
        
    def __len__(self):
        return len(self._children_refs)

    def _is_singleton_path(self):
        if self.is_leaf:
            return True
        elif len(self) > 1:
            return False
        else:
            return self.passthru._is_singleton_path()
    
    def is_passthru(self):
        return len(self) == 1 and not self.port and not self.is_vector

    def get_contained_ports(self):
        ports = set()
        if self.port:
            ports.add(self.port)
        for child in self.children:
            ports |= child.get_contained_ports()
        return ports

    def set_parent(self, parent):
        assert parent is None
        self._parent = parent

    def tag_as_vector(self, vports):
        self._is_vector = True
        self._vports = vports
        # drop digit ptrs corresponding to vector
        # FIXME this is a little hacky
        dptrs = [ptr for ptr in self.ptrs if ptr.isdigit()]
        for ptr in dptrs:
            del self._children_refs[ptr]

    def add_port(self, port):
        self._port = port

    def add_child(self, ptr, child):
        self._children_refs[ptr] = child

    def __getitem__(self, ptr):
        return self._children_refs[ptr]
        
    def get_child(self, ptr):
        return self._children_refs[ptr]

    def drop_child(self, ptr):
        n = self._children_refs[ptr]
        del self._children_refs[ptr]
        return n

    def update(self, ss):
        """
        recursively update with specified subtree `ss`
        """
        # FIXME this is a little tenuous
        if ss.port:
            assert self.port == None
            self._port = ss.port
        for ptr, ss_child in ss.children_refs:
            child = self.get_child(ptr)
            child.update(ss_child)

    def as_dict(self, name_only=False):
        def fmt_vector(v):
            return [p[0] for p in v] if name_only else list(v)
        def fmt_port(p):
            return p[0] if name_only else p

        if self.is_leaf and self.is_vector:
            return fmt_vector(self.vports)
        elif self.is_leaf:
            return fmt_port(self.port)
        else:
            assert not (self.port and self.is_vector), \
                "node cannot both have a port and be a vector"
            d = {}
            for ptr, child in self.children_refs:
                d[ptr] = child.as_dict(name_only)
            if self.port:
                d['_'] = fmt_port(self.port)
            if self.is_vector:
                d['_'] = fmt_vector(self.vports)
            return d

class BundleTree(object):
    
    @property
    def tree(self): return self._root_node.as_dict()
    @property
    def name(self): return self._name
    @property
    def size(self): return len(self._ports)
    @property
    def ports(self): return iter(self._ports)
    
    def __init__(self, ports):
        self._ports = list(ports)
        self._root_node = BundleTreeNode()
        root = self._root_node
        for port in self._ports:
            root.update(self._subtree_from_port(port))
        self._format_vectors()
        self._flatten_passthru_paths()

        # if the first level is a trunk (single key), designate as name,
        # and pass thru the trunk to assign a new root
        if (
            len(root) == 1 and 
            self.size > 1 and 
            not root.passthru.is_vector
        ):
            root_ptr = next(iter(root.ptrs))
            self._name = root_ptr.strip('_')
            nroot = root.get_child(root_ptr)
            self._root_node = nroot
        # otherwise simply assign the name 'root' to this bundle tree
        else:
            self._name = 'root'

        # do a post-order traversal that sets up the interfaces of each node
        # using the interface of the children
        pre_order_n(self._root_node, lambda n: n.set_interface())
    
    def get_initial_interfaces(
        self,
        min_size=4,
        max_size=None,
    ):
        """
        return interfaces for all bundle tree nodes that meet min and max
        size filter
        """
        # if the root is large (>= 100 ports), then only expose only
        # leaves at root node (the "rest" of the ungrouped ports) 
        root_leaves = list(filter(lambda n: n.is_leaf, self._root_node.children))
        abbr_root_interface = Interface.merge(*[n.interface for n in root_leaves])
        rootnid = self._root_node.id

        for nid, interface in pre_order_n(
            self._root_node, 
            lambda n: (n.id, n.interface),
        ):
            if nid == rootnid and interface.size >= 100:
                yield nid, abbr_root_interface
            elif (
                (interface.size >= min_size) and
                (max_size is None or interface.size <= max_size)
            ):
                yield nid, interface

    def get_optimal_nids(self, nid_cost_map, min_num_leaves=4):
        """
        return nids that are optimal for at least `min_num_leaves`
        according to costs specified `nid_cost_map` 
        """
        ninfo = pre_order_n(self._root_node, lambda n: (n, n.is_leaf))
        leaf_nodes = [n for n, is_leaf in ninfo if is_leaf]

        opt_node_counts = Counter()
        for leaf in leaf_nodes:
            curr = leaf
            costs = []
            # compare against all parent interfaces *except* root
            while curr.parent is not None:
                cost = None if curr.id not in nid_cost_map else \
                    nid_cost_map[curr.id]
                if cost is not None:
                    costs.append((cost, curr))
                curr = curr.parent
            if len(costs) > 0:
                min_cost = min([cost for cost, _ in costs])
                opt_nodes = [n for cost, n in costs if cost == min_cost]
                for opt_node in opt_nodes:
                    opt_node_counts[opt_node] += 1

        # yield root nid as optimal if there is nothing else
        if len(opt_node_counts) == 0:
            return set([self._root_node.id])

        opt_nids = set()
        for t in reversed(range(min_num_leaves)):
            opt_nids = [n.id for n in opt_node_counts if opt_node_counts[n] > t]
            if len(opt_nids) > 0:
                break
        return opt_nids
        
    def get_bundles(self):
        """
        return bundles for all non-leaf children of the root and a single
        bundle for the remaining leaf children of the root (ungrouped
        ports).
        """
        bundles = [
            Bundle(n.as_dict(name_only=True), ptr)
            for ptr, n in self._root_node.children_refs
                if not n.is_leaf
        ]

        # remove non-leaf children pointers of root from root bundle,
        # these are yielded as separate bundles
        root_tree = self._root_node.as_dict(name_only=True)
        filt_ptrs = [
            ptr
            for ptr, n in self._root_node.children_refs 
                if not n.is_leaf
        ]
        for ptr in filt_ptrs:
            del root_tree[ptr]
        if len(root_tree) > 0:
            bundles.append(Bundle(root_tree, 'root'))

        return bundles

    def _subtree_from_port(self, port):
        """
        convert name of port to subtree to be inserted
        """
        name, _, _ = port
        words = util.words_from_name(name)
        nodes = [BundleTreeNode() for i in range(len(words)+1)]
        # leaf should map to port
        nodes[-1].add_port(port)
        # set parent pointers
        for ptr, parent, child in zip(words, nodes, nodes[1:]):
            parent.add_child(ptr, child)
        return nodes[0]
    
    def _format_vectors(self):
        """
        format vectors of the tree in place
        """
        def get_vec_info(n):
            dptrs = [ptr for ptr in n.ptrs if ptr.isdigit()]
            if (
                len(dptrs) < 2 or
                not is_range(dptrs) or
                not all([n[ptr]._is_singleton_path() for ptr in dptrs])
            ):
                return False, []
            # ports must have matching width
            ptr_ports = sorted([
                (int(ptr), next(iter(n[ptr].get_contained_ports())))
                for ptr in dptrs
            ])
            vports = [p for _, p in ptr_ports]
            is_vector = (
                len(set([p[1] for p in vports])) == 1 and
                len(set([p[2] for p in vports])) == 1
            )
            return is_vector, vports

        stack = deque([(None, None, self._root_node)])
        while len(stack) > 0:
            parent, pkey, curr = stack.popleft()
            is_vector, vports = get_vec_info(curr)
            if is_vector:
                curr.tag_as_vector(vports)
            # FIXME a bit hacky, but tag_as_vector actually modifies ptrs
            # to remove the ones assigned to a vector, so this will only
            # add children from non-vector ptrs
            for ptr, child in curr.children_refs:
                if not child.is_leaf:
                    stack.appendleft((curr, ptr, child))

    def _flatten_passthru_paths(self):
        """
        flatten hierarchy of passthru paths in the tree
        """
        stack = deque([(None, None, self._root_node)])
        while len(stack) > 0:
            parent, pkey, curr = stack.popleft()
            # pass thru, modify parent pointer with newkey and add children
            if parent is not None and curr.is_passthru():
                ckey = curr.passkey
                child = curr.passthru
                new_key = '{}_{}'.format(pkey, ckey)
                # remove intermediate curr
                parent.drop_child(pkey)
                parent.add_child(new_key, child)
                # place this node back on the stack if not a leaf
                if not child.is_leaf:
                    stack.appendleft((parent, new_key, child))
            else:
                for ptr, child in curr.children_refs:
                    if not child.is_leaf:
                        stack.appendleft((curr, ptr, child))

def pre_order_n(
    node,
    func=(lambda x: x.id),
    visit_leaf=True,
    term_func=(lambda x: False),
):
    stack = [node]
    def push(n): stack.append(n)
    def pop(): return stack.pop()
    def peek(): return stack[-1] 
    visited = set()
    preorder = []
    while len(stack) > 0:
        curr = peek()
        if curr.is_leaf:
            pop()
            if visit_leaf:
                preorder.append(func(curr))
        elif curr.id in visited:
            preorder.append(func(curr))
            pop()
        elif (
            term_func is None or
            not term_func(curr)
        ):
            for ptr, child in curr.children_refs:
                push(child)
        visited.add(curr.id)

    return preorder

