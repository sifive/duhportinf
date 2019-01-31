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
    # distance
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
    Yield all groupings of the input ports by traversing this tree in
    pre-order.
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
        
    def _get_group(self, node):
        return set(map(
            lambda nid: self.nid_port_map[nid],
            filter(
                lambda nid: nid in self.leaf_ids,
                node.pre_order(lambda n:n.id),
            ),
        ))

    def get_initial_port_groups(self):
        """

        yield port groups for non-leaf nodes of the hierarchical
        clustering tree using node distances to intelligently choose
        initial port groups to expose

        modified from ClusterNode.pre_order() src to yield at non-leaf
        nodes
        """
        # first obtain node ids correpsonding to initial port groups to
        # yield based off of distances in hierarchical clustering tree
        init_node_ids = self._get_init_node_ids()

        # Do a preorder traversal, caching the result. To avoid having to do
        # recursion, we'll store the previous index we've visited in a vector.
        node = self.root_node
        n = self.root_node.count
        
        curNode = [None] * (2 * n)
        lvisited = set()
        rvisited = set()
        curNode[0] = node
        k = 0
        while k >= 0:
            nd = curNode[k]
            ndid = nd.id
            if nd.is_leaf():
                #yield set([self.nid_port_map[nd.id]])
                k = k - 1
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
                    k = k - 1
                    if nd.id in init_node_ids:
                        yield nd.id, self._get_group(nd)
        
        return

    def _get_init_node_ids(self):
        """
        use relative distances in linkage tree to determine initial port
        groups to test.

        yield a particular node, and its port group, if for any port (leaf
        node) it is the maximum increase in distance.
        """
        init_nids = set()
        def tag_init_node_func(node):
            curr = node
            nid_costs = []

            while curr.parent is not None:
                cost = curr.parent.dist - curr.dist
                # exclude singletons, which have the largest distance from self
                if not curr.is_leaf():
                    nid_costs.append((cost, curr.id, curr))
                curr = curr.parent

            ## FIXME remove debug
            #dport = ('axi4_mst0_aclk', 1, 1)
            #init_group = set(self._get_group(nid_costs[0][-1]))
            #if dport in init_group and len(init_group) < 60:
            #    prev_group = set()
            #    for cost, nid, node in nid_costs:
            #        group = set(self._get_group(node))
            #        print('cost:{}, size:{}'.format(cost, len(group)))
            #        print('  - added', list(sorted(group - prev_group))[:10])
            #        prev_group = group
            #    _, opt_nid, opt_node = max(
            #        filter(
            #            lambda x: x[-1].get_count() < 200,
            #            nid_costs,
            #        ),
            #        key=lambda x: x[0],
            #    )
            #    print('opt size:', len(self._get_group(opt_node)))
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
                _, opt_nid, opt_node = max(
                    f_nid_costs,
                    key=lambda x: x[0],
                )
                init_nids.add(opt_nid)

        # use default pre order traversal, which only executes argument
        # func at the leaves
        self.root_node.pre_order(tag_init_node_func)
        
        return init_nids

    def get_optimal_groups(self, nid_cost_map):

        opt_nids = set()
        def tag_optimal_func(node):
            curr = node
            nid_costs = []

            while curr is not None:
                cost = None if curr.id not in nid_cost_map else \
                    nid_cost_map[curr.id]
                if cost is not None:
                    nid_costs.append((cost, curr.id, curr))
                # early exit
                if curr.optimal:
                    break
                curr = curr.parent

            ## must be at least one node assigned a cost on the path of
            ## every leaf
            #assert len(nid_costs) > 0
            if len(nid_costs) > 0:
                _, opt_nid, opt_node = min(nid_costs, key=lambda x: x[0])
                opt_nids.add(opt_nid)
                opt_node.optimal = True

        # use default pre order traversal, which only executes argument
        # func at the leaves
        self.root_node.pre_order(tag_optimal_func)
        
        return opt_nids
        
#--------------------------------------------------------------------------
# ClusterNode helpers
#--------------------------------------------------------------------------
def set_defaults(node):
    node.parent = None
    node.optimal = False

def add_parent(node, parent):
    node.parent = parent
    
def tag_parent(node):
    if not node.is_leaf():
        add_parent(node.get_left(), node)
        add_parent(node.get_right(), node)

def pre_order_n(self, func=(lambda x: x.id)):
        """
        modified from ClusterNode src to invoke func at non-leaf nodes as well
        """

        # Do a preorder traversal, caching the result. To avoid having to do
        # recursion, we'll store the previous index we've visited in a vector.
        n = self.count

        curNode = [None] * (2 * n)
        lvisited = set()
        rvisited = set()
        curNode[0] = self
        k = 0
        preorder = []
        while k >= 0:
            nd = curNode[k]
            ndid = nd.id
            if nd.is_leaf():
                preorder.append(func(nd))
                k = k - 1
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

