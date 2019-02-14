from abc import ABC
import numpy as np
from scipy.cluster.hierarchy import linkage, to_tree
from scipy.spatial.distance import pdist
from ._vectorizer import Vectorizer
from . import util

def get_port_grouper(ports):
    wire_names = [p[0] for p in ports]
    vectorizer = Vectorizer(wire_names)
    vs = [vectorizer.get_vec(name) for name in wire_names]
    V = np.vstack(vs)

    # preferentially weight port name prefix matches using mahalanobis
    # distance.  specify matrix S so that mismatches in the prefix word
    # groups will be more heavily penalized
    S = np.diag(np.hstack([
        np.ones(group_size) * scale**4
        for scale, group_size in zip(
            range(vectorizer.num_groups, 0,-1),
            vectorizer.group_sizes,
        )
    ]))
    Y = pdist(
        V,
        'mahalanobis',
        VI=S,
    )
    Z = linkage(
        Y,
        method='single',
    )
    pg = PortGrouper(ports, Z)

    return pg, Z, wire_names

class PortGrouper(object):
    """
    Build a tree off an input hierarchical clustering linkage matrix Z.
    Use the tree to yield port groups.
    """

    def __init__(self, ports, Z):
        self.root_node, self.node_list = to_tree(Z, rd=True)

        # set node attribute defaults
        for n in self.node_list:
            set_defaults(n)
        # traverse tree and tag parents
        _ = pre_order_n(self.root_node, tag_parent)
    
        leaves = list(filter(lambda n: n.is_leaf(), self.node_list))
        self.port_node_map = dict(zip(
            ports,
            sorted(leaves, key=lambda n: n.id),
        ))
        self.nid_port_map = {v.id:k for k,v in self.port_node_map.items()}
        self.leaf_ids = set(map(lambda n: n.id, leaves))
        # label vectors
        self._label_vectors()
        
    def _get_group(self, node):
        return set(map(
            lambda nid: self.nid_port_map[nid],
            filter(
                lambda nid: nid in self.leaf_ids,
                node.pre_order(lambda n:n.id),
            ),
        ))

    def get_initial_port_groups(self):
        init_nodes = self._get_init_nodes()
        for node in init_nodes:
            yield node.id, self._get_group(node)
        return

    def _get_init_nodes(self):
        """
        Use relative distances in linkage tree to determine initial port
        groups to test.

        Yield a particular node, and its port group, if for any port (leaf
        node) it is the maximum increase in distance.
        """
        init_nodes = []
        seen_ids = set()
        def tag_init_node_func(node):
            curr = node
            nid_costs = []

            while curr.parent is not None:
                cost = curr.parent.dist - curr.dist
                # exclude singletons, which have the largest distance from self
                if not curr.is_leaf():
                    nid_costs.append((cost, curr.id, curr))
                curr = curr.parent

            # FIXME remove debug
            #dport = ('axi0_AWLEN', 8, 1)
            #dport = ('axi4_mst0_aclk', 1, 1)
            #dport = ('nvdla_core2dbb_aw_awready', 1, 1)
            #dport = ('pl_rxpolarity', None, -1)
            #init_group = set(self._get_group(nid_costs[0][-1]))
            #if dport in init_group and len(init_group) < 60:
            #    prev_group = set()
            #    for cost, nid, node in nid_costs:
            #        group = set(self._get_group(node))
            #        print('cost:{}, size:{}'.format(cost, len(group)))
            #        print('  - added', list(sorted(group - prev_group))[:10])
            #        prev_group = group
            #    f_nid_costs = list(filter(
            #        lambda x: x[-1].get_count() < 200,
            #        nid_costs,
            #    ))
            #    if len(f_nid_costs) > 0:
            #        opt_nid_costs = sorted(
            #            f_nid_costs,
            #            key=lambda x: x[0],
            #            reverse=True,
            #        )[:2]
            #        for opt in opt_nid_costs:
            #            print('opt size:', opt[-1].get_count())
            #        die
            #    die

            # FIXME for now trim nodes in which the size of the port group
            # is very large.  this is not really robust, but ports added
            # closer to the tree root can actually have *very* large costs
            # and dominate the costs of the nodes that we are actually
            # trying to capture
            f_nid_costs = list(filter(
                lambda x: x[-1].get_count() < 200,
                nid_costs,
            ))
            if len(f_nid_costs) > 0:
                opt_nid_costs = sorted(
                    f_nid_costs,
                    key=lambda x: x[0],
                    reverse=True,
                )[:2]
                for _, _, opt_node in opt_nid_costs:
                    if opt_node.id not in seen_ids:
                        init_nodes.append(opt_node)
                    seen_ids.add(opt_node.id)

        # use default pre order traversal, which only executes argument
        # func at the leaves
        self.root_node.pre_order(tag_init_node_func)
        
        return init_nodes

    def get_optimal_groups(self, nid_cost_map):

        def reset_optimal_func(node):
            node.optimal = 0

        def count_optimal_func(node):
            curr = node
            nid_costs = []

            while curr is not None:
                cost = None if curr.id not in nid_cost_map else \
                    nid_cost_map[curr.id]
                if cost is not None:
                    nid_costs.append((cost, curr.id, curr))
                curr = curr.parent

            ## must be at least one node assigned a cost on the path of
            ## every leaf
            #assert len(nid_costs) > 0
            if len(nid_costs) > 0:
                _, opt_nid, opt_node = min(nid_costs, key=lambda x: x[0])
                opt_node.optimal += 1


        opt_nids = set()
        def tag_optimal_func(node):
            if node.optimal > 3:
                opt_nids.add(node.id)

        # reset optimal counts
        self.root_node.pre_order(reset_optimal_func)

        # use default pre order traversal, which only executes argument
        # func at the leaves
        self.root_node.pre_order(count_optimal_func)

        # use helper  pre order traversal to tag non-leaf nodes that have
        # a high optimal count
        pre_order_n(self.root_node, tag_optimal_func)
        
        return opt_nids
        
    def get_vectors(self):
        vector_port_groups = []
        for node, is_vector in (
            pre_order_n(self.root_node, lambda n: (n, n.is_vector))
        ):
            if is_vector:
                vector_port_groups.append(self._get_group(node))
        return [
            VectorBundle(port_group) 
            for port_group in vector_port_groups
        ]

    def _label_vectors(self):

        # tag all nodes that make up a vector
        def tag_is_vector_func(node):
            ports = self._get_group(node)
            bundle = get_bundle_designation(ports)
            if type(bundle) == VectorBundle:
                node.is_vector = True

        # untag nodes in which the parent is also a vector and the node
        # belongs to a wider vector
        def tag_is_root_vector_func(node):
            if node.parent and node.parent.is_vector:
                node.is_vector = False
        
        pre_order_n(self.root_node, tag_is_vector_func, visit_leaf=False)
        pre_order_n(self.root_node, tag_is_root_vector_func, visit_leaf=False)
        return

#--------------------------------------------------------------------------
# port group designations
#--------------------------------------------------------------------------
def get_bundle_designation(ports):
    names  = [p[0] for p in ports]
    widths = [p[1] for p in ports]
    dirs   = [p[2] for p in ports]
    same_dir = (len(set(dirs)) == 1)
    same_width = (len(set(widths)) == 1)
    vindex_idx = VectorBundle.get_vector_index(ports)
    if same_dir and same_width and vindex_idx != -1:
        return VectorBundle(ports)
    elif same_dir:
        return DirectedBundle(ports)
    else:
        return UndirectedBundle(ports)

class Bundle(ABC):

    @property
    def size(self): return len(self._ports)
    @property
    def ports(self): return iter(self._ports)

    @property
    def prefix(self):
        "Given a list of names, returns the longest common leading component"
        port_names = [p[0] for p in self.ports]
        n1 = min(port_names)
        n2 = max(port_names)
        for i, c in enumerate(n1):
            if c != n2[i]:
                return n1[:i] 
        return n1

    def __init__(self, ports):
        assert len(ports) > 1
        self._ports = ports

class VectorBundle(Bundle):

    @classmethod
    def get_vector_index(cls, ports):
        name_words = [util.words_from_name(p[0]) for p in ports]
        diff_idxs = [
            (i, word_group)
            for i, word_group in enumerate(zip(*name_words))
                if len(set(word_group)) > 1
        ]
        if len(diff_idxs) != 1:
            return -1
        # check all words in group are digits and form a range
        idx, word_group = diff_idxs[0]
        all_digits = all([w.isdigit() for w in word_group])
        if not all_digits:
            return -1
        indexes = [int(w) for w in word_group]
        return idx if util.is_range(indexes) else -1

    @property
    def range(self):
        return range(self._min, self._max+1)

    def __init__(self, ports):
        super(self.__class__, self).__init__(ports)

        vindex = self.__class__.get_vector_index(self.ports)

        name_words = [util.words_from_name(p[0]) for p in self.ports]
        index_words = list(zip(*name_words))[vindex]
        assert all([w.isdigit() for w in index_words])
        indexes = [int(w) for w in index_words]
        assert util.is_range(indexes)
        self._min = min(indexes)
        self._max = max(indexes)

class DirectedBundle(Bundle):
    def __init__(self, ports):
        super(self.__class__, self).__init__(ports)
        dirs = [p[2] for p in self.ports]
        same_dir = (len(set(dirs)) == 1)
        assert same_dir

class UndirectedBundle(Bundle):
    def __init__(self, ports):
        super(self.__class__, self).__init__(ports)

#--------------------------------------------------------------------------
# ClusterNode helpers
#--------------------------------------------------------------------------
def set_defaults(node):
    node.parent = None
    node.optimal = 0
    node.is_vector = False

def add_parent(node, parent):
    node.parent = parent
    
def tag_parent(node):
    if not node.is_leaf():
        add_parent(node.get_left(), node)
        add_parent(node.get_right(), node)

def pre_order_n(node, func=(lambda x: x.id), visit_leaf=True):
    """
    modified from ClusterNode src to invoke func at non-leaf nodes as well
    """
    
    # Do a preorder traversal, caching the result. To avoid having to do
    # recursion, we'll store the previous index we've visited in a vector.
    n = node.count
    
    curNode = [None] * (2 * n)
    lvisited = set()
    rvisited = set()
    curNode[0] = node
    k = 0
    preorder = []
    while k >= 0:
        nd = curNode[k]
        ndid = nd.id
        if nd.is_leaf():
            k = k - 1
            if visit_leaf:
                preorder.append(func(nd))
        else:
            if ndid not in lvisited:
                curNode[k + 1] = nd.left
                lvisited.add(ndid)
                k = k + 1
            elif ndid not in rvisited:
                curNode[k + 1] = nd.right
                rvisited.add(ndid)
                k = k + 1
            # If we've visited the left and right of this non-leaf
            # node already, go up in the tree.
            else:
                preorder.append(func(nd))
                k = k - 1
    
    return preorder

