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
    Build a tree off an input hierarchical clustering linkage matrix Z.
    Yield all groupings of the input ports by traversing this tree in
    pre-order.
    """

    def __init__(self, ports, Z):
        self.root_node, self.node_list = to_tree(Z, rd=True)

        leaves = list(filter(lambda n: n.is_leaf(), self.node_list))
        self.port_node_map = dict(zip(
            ports,
            sorted(leaves, key=lambda n: n.id),
        ))
        self.id_port_map = {v.id:k for k,v in self.port_node_map.items()}
        self.leaf_ids = set(map(lambda n: n.id, leaves))
        
    #def get_group_leaves(self, node):
    #    return list(filter(
    #        lambda n: n.id in self.leaf_ids,
    #        pre_order_n(node, lambda n: n),
    #    ))
    
    def _get_group(self, node):
        return set(map(
            lambda nid: self.id_port_map[nid],
            filter(
                lambda nid: nid in self.leaf_ids,
                node.pre_order(lambda n:n.id),
            ),
        ))

    def get_port_groups(self):
        """
        modified from ClusterNode src to invoke func at non-leaf nodes as well
        """
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
                #yield set([self.id_port_map[nd.id]])
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
                    yield self._get_group(nd)
        
        return

