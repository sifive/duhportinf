import numpy as np
from scipy.cluster.hierarchy import linkage, to_tree
from ._vectorizer import Vectorizer
from . import util

def get_port_grouper(ports):
    wire_names = [p[0] for p in ports]
    vectorizer = Vectorizer(wire_names)
    vs = [vectorizer.get_vec(name) for name in wire_names]
    V = np.vstack(vs)
    Z = linkage(V, 'ward')
    pg = PortGrouper(ports, Z)
    #print(Z[:,:])
    return pg, Z, wire_names

class PortGrouper(object):
    """
    Build a tree off an input hierarchical clustering linkage matrix Z
    
    Yield all parent groupings of a given input wire
    """
    def __init__(self, ports, Z):
        self.root_node, self.node_list = to_tree(Z, rd=True)

        # default no parents
        for n in self.node_list:
            add_parent(n, None)
        # traverse tree and tag parents
        _ = pre_order_n(self.root_node, tag_parent)
    
        leaves = list(filter(lambda n: n.is_leaf(), self.node_list))
        self.wire_node_map = dict(zip(
            ports,
            sorted(leaves, key=lambda n: n.id),
        ))
        self.id_wire_map = {v.id:k for k,v in self.wire_node_map.items()}
        self.leaf_ids = set(map(lambda n: n.id, leaves))
        
    def get_group_leaves(self, node):
        return list(filter(
            lambda n: n.id in self.leaf_ids,
            pre_order_n(node, lambda n: n),
        ))
    
    def get_port_groups(self, wire):
        assert wire in self.wire_node_map
        curr = self.wire_node_map[wire]
        assert curr.parent is not None
        # traverse up until the root
        while curr is not None:
            group = self.get_group_leaves(curr)
            yield set(map(lambda n: self.id_wire_map[n.id], group))
            curr = curr.parent

#--------------------------------------------------------------------------
# ClusterNode helpers
#--------------------------------------------------------------------------
def pre_order_n(node, func=(lambda x: x.id)):
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
                k = k - 1
                preorder.append(func(nd))
    
    return preorder

def add_parent(node, parent):
    node.parent = parent
    
def tag_parent(node):
    if not node.is_leaf():
        add_parent(node.get_left(), node)
        add_parent(node.get_right(), node)

