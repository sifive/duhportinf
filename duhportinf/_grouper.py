import numpy as np
from scipy.cluster.hierarchy import linkage, to_tree
from scipy.spatial.distance import pdist
from itertools import chain
from ._vectorizer import Vectorizer
from . import util
from ._interface import (
    Interface,
    VectorBundle,
    DirectedBundle,
    get_bundle_designation,
)

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
        self.nid_node_map = dict(pre_order_n(
            self.root_node,
            lambda n: (n.id, n),
        ))
        # label vectors
        (
            self.vector_root_ids,
            self.vector_leaf_ids,
            self.vector_nid_ports_map,
        ) = self._label_vector_nodes()
        # get interfaces for all non-leaf nodes
        self.nid_interface_map = self._get_interfaces()
        
    def _get_group(self, node):
        """
        obtain all ports that are children of this node
        """
        return set(map(
            lambda nid: self.nid_port_map[nid],
            (self.leaf_ids & set(node.pre_order(lambda n:n.id))),
        ))

    def get_initial_interfaces(self):
        init_nodes = self._get_init_nodes()
        for node in init_nodes:
            yield node.id, self.nid_interface_map[node.id]
        return

    def _get_init_nodes(self):
        """
        Use relative distances in linkage tree to determine initial port
        groups to test.

        Yield a particular node, if for any port (leaf node) it is the
        maximum increase in tree distance.
        """
        init_nodes = []
        seen_ids = set()
        def tag_init_node_func(node):
            curr = node
            nid_costs = []

            is_vector = []
            while curr.parent is not None:
                cost = self._get_linkage_tree_dist(curr)
                # exclude singletons, which have the largest distance from self
                if not curr.is_leaf():
                    nid_costs.append((cost, curr.id, curr))
                    is_vector.append(curr.is_vector)
                curr = curr.parent

            vindexes = [i for i, is_v in enumerate(is_vector) if is_v]
            # a node should only be part of a vector once! 
            assert len(vindexes) <= 1
            # never return children of a vector
            vidx = next(iter(vindexes), 0)
            nid_costs = nid_costs[vidx:]

            ## FIXME remove debug
            #dport = ("axi1_RPARITY_EN", 1, -1)
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
        # special case if root node is a vector.  in this case, it is the only
        # initial node to return
        if self.root_node.is_vector:
            return [self.root_node]

        # tag based on linkage tree distance
        # NOTE use default pre order traversal, which only executes argument
        # func at the leaves
        self.root_node.pre_order(tag_init_node_func)

        return init_nodes

    def _get_linkage_tree_dist(self, node):
        """
        Determine the delta in linkage tree distance between the current
        node and its parent
        """
        if node.parent is None:
            return None
        else:
            cost = node.parent.dist - node.dist
            return cost
        
    def _label_vector_nodes(self):

        # tag all nodes that make up a vector
        def tag_is_vector_func(node):
            ports = self._get_group(node)
            bundle = get_bundle_designation(ports)
            if type(bundle) == VectorBundle:
                node.is_vector = True

        # untag nodes in which the parent is also a vector and the node
        # belongs to a wider vector
        vector_root_ids = set()
        vector_leaf_ids = set()
        vector_nid_ports_map = {}
        def tag_lca_is_vector_func(node):
            if node.parent and node.parent.is_vector:
                node.is_vector = False
            elif node.is_vector:
                vector_root_ids.add(node.id)
                for nid in node.pre_order(lambda n: n.id):
                    vector_leaf_ids.add(nid)
                vector_nid_ports_map[node.id] = self._get_group(node)
        
        pre_order_n(self.root_node, tag_is_vector_func, visit_leaf=False)
        pre_order_n(self.root_node, tag_lca_is_vector_func, visit_leaf=False)
        return (
            vector_root_ids,
            vector_leaf_ids,
            vector_nid_ports_map,
        )

    def _get_interfaces(self):
        nid_interface_map = {}
        # hierarchically merge interface instances, recognizing nodes
        # already tagged as vectors
        def add_interface_func(node):
            # single port interface for leaves
            if node.is_leaf():
                nid_interface_map[node.id] = Interface(
                    [DirectedBundle([self.nid_port_map[node.id]])]
                )
                return

            lnid = node.left.id
            rnid = node.right.id
            linter = nid_interface_map[lnid]
            rinter = nid_interface_map[rnid]
            lvbundles = linter.vector_bundles
            rvbundles = rinter.vector_bundles
            bundles = []
            ports = self._get_group(node)
            if node.is_vector:
                # if this node is itself a vector, then by construction
                # the child nodes can *not* be a vector
                assert len(lvbundles) == 0 and len(rvbundles) == 0
                assert node.id in self.vector_root_ids
                vports = self.vector_nid_ports_map[node.id]
                bundles.append(VectorBundle(vports))
            else:
                bundles.extend(list(chain(lvbundles, rvbundles)))
                lnvbundles = linter.nonvector_bundles
                rnvbundles = rinter.nonvector_bundles
                # each interface for now can only have a single
                # nonvector bundle
                assert len(lnvbundles) <= 1 and len(rnvbundles) <= 1
                rest_ports = util.flatten(
                    [b.ports for b in chain(lnvbundles, rnvbundles)]
                )
                if len(rest_ports) > 0:
                    # FIXME kind of hacky for children nodes of a vector,
                    # which should *not* themselves be designated as a
                    # vector
                    rest_bundle = get_bundle_designation(rest_ports)
                    if type(rest_bundle) == VectorBundle:
                        rest_bundle = DirectedBundle(rest_ports)
                    bundles.append(rest_bundle)

            interface = Interface(bundles)
            # this interface should contain the full number of ports for
            # this node
            assert interface.size == len(list(node.pre_order(lambda n: n.id)))
            nid_interface_map[node.id] = interface 

        pre_order_n(self.root_node, add_interface_func)

        return nid_interface_map

    def get_optimal_nids(self, nid_cost_map, min_num_leafs=4):
        """
        determine the set of nodes that are low cost with respect to the
        specified <node>: cost map.  nodes are selected if they are the
        lowest specified cost nodes on the path between leaf and root node
        for at least min_num_leafs.

        select the set of no
        """

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

        def get_tag_func(threshold):
            opt_nids = set()
            def tag_optimal_func(node):
                if node.optimal > threshold:
                    opt_nids.add(node.id)
            return tag_optimal_func, opt_nids

        # reset optimal counts
        pre_order_n(self.root_node, reset_optimal_func)

        # use default pre order traversal, which only executes argument
        # func at the leaves
        self.root_node.pre_order(count_optimal_func)

        # use helper pre order traversal to tag non-leaf nodes that have
        # a high optimal count
        # NOTE try obtaining nodes that are optimal for a minimum number
        # of leaf nodes, reduce this threshold iteratively if none are
        # found
        opt_nids = None
        for threshold in reversed(range(min_num_leafs)):
            tag_optimal_func, opt_nids = get_tag_func(threshold)
            pre_order_n(self.root_node, tag_optimal_func)
            if len(opt_nids) > 0:
                break
        # cannot return 0 nodes as optimal
        assert len(opt_nids) > 0

        return opt_nids

#--------------------------------------------------------------------------
# ClusterNode helpers
#--------------------------------------------------------------------------
def set_defaults(node):
    node.parent = None
    node.is_vector = False

def add_parent(node, parent):
    node.parent = parent
    
def tag_parent(node):
    if not node.is_leaf():
        add_parent(node.get_left(), node)
        add_parent(node.get_right(), node)

def pre_order_n(
    node,
    func=(lambda x: x.id),
    visit_leaf=True,
):
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

