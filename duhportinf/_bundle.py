import copy
import json
import collections
from collections import deque
from . import util

def update(d, u):
    for k, v in u.items():
        if isinstance(v, collections.Mapping):
            # special case when string is already inserted
            if k in d and isinstance(d[k], str):
                d[k] = {'_':d[k]}
            d[k] = update(d.get(k, {}), v)
        else:
            d[k] = v
    return d

class Bundle(object):
    
    @property
    def tree(self):
        return copy.deepcopy(self._tree)
    @property
    def name(self):
        return self._name
    @property
    def size(self):
        return len(self._port_names)
    @property
    def port_names(self):
        return iter(self._port_names)
    
    def __init__(self, names):
        self._port_names = list(names)
        self._tree = {}
        for name in self._port_names:
            update(self._tree, self._subtree_from_name(name))
        self._format_vectors()
        self._flatten_passthru_paths()
        # if the first level is a trunk (single key), designate as name,
        # otherwise root
        if len(self._tree) == 1 and self.size > 1:
            self._name = next(iter(self._tree.keys())).strip('_')
            branches = next(iter(self._tree.values()))
            self._tree = branches
        else:
            self._name = 'root'
    
    def _flatten_passthru_paths(self):
        """
        flatten hierarchy of passthru paths in the tree
        """
        stack = deque([(None, None, self._tree)])
        while len(stack) > 0:
            parent, pkey, curr = stack.popleft()
            # pass thru, modify parent pointer with newkey and add children
            if parent is not None and len(curr) == 1:
                ckey = next(iter(curr))
                child = next(iter(curr.values()))
                new_key = '{}_{}'.format(pkey, ckey)
                # remove intermediate curr
                del parent[pkey]
                parent[new_key] = child
                # place this node back on the stack if not a leaf
                if not self._is_leaf(child):
                    stack.appendleft((parent, new_key, child))
            else:
                for k, child in curr.items():
                    if not self._is_leaf(child):
                        stack.appendleft((curr, k, child))
        
    def _subtree_from_name(self, name):
        """
        convert name to subtree to be inserted
        """
        words = util.words_from_name(name)
        # leaf should map to port name
        tree_dict = {words[-1] : name}
        for w in reversed(words[:-1]):
            tree_dict = {w: tree_dict}
        return tree_dict
    
    def _format_vectors(self):
        """
        format vectors of the tree in place
        """
        stack = deque([(None, None, self._tree)])
        while len(stack) > 0:
            parent, pkey, curr = stack.popleft()
            if self._is_vector(curr):
                vector = [p for i, p in 
                    sorted([(idx, self._deref_singleton_path(stree)) for idx, stree in curr.items()])
                ]
                parent[pkey] = vector
            else:
                for k, child in curr.items():
                    if not self._is_leaf(child):
                        stack.appendleft((curr, k, child))

    def _is_vector(self, stree):
        return (
            not self._is_leaf(stree) and
            len(stree) > 1 and
            all([self._is_singleton_path(ss) for ss in stree.values()]) and
            self._is_range(stree.keys())
        )
       
    def _is_range(self, keys):
        if not all([k.isdigit() for k in keys]):
            return False
        idx = [int(k) for k in keys]
        return util.is_range(idx)
    
    def _is_leaf(self, stree):
        # vector or string
        return type(stree) in [list, str]
    
    def _deref_singleton_path(self, stree):
        if self._is_leaf(stree):
            return stree
        else:
            assert len(stree) == 1
            sstree = next(iter(stree.values()))
            return self._deref_singleton_path(sstree)
        
    def _is_singleton_path(self, stree):
        if self._is_leaf(stree):
            return True
        elif len(stree) > 1:
            return False
        else:
            sstree = next(iter(stree.values()))
            return self._is_singleton_path(sstree)
        
