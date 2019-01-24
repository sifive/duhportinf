import numpy as np
from collections import defaultdict
from itertools import tee, chain
from . import util

def pairwise(iterable):
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)

class GroupVectorizer(object):
    @property
    def size(self): return self._size
    def __init__(self, words):
        self._idx_word_map = dict(enumerate(words))
        self._word_idx_map = dict(
            [(v, k) for (k, v) in enumerate(words)],
        )
        self._size = len(words)
        
    def get_vec(self, words):
        v = np.zeros(self.size, dtype=bool)
        for w in words:
            assert w in self._word_idx_map
            v[self._word_idx_map[w]] = True
        return v
    
    def get_attrs(self):
        return np.array(list(map(
            lambda x: x[1],
            sorted(self._idx_word_map.items()),
        )))
    
class Vectorizer(object):
    @property
    def size(self): return sum([gv.size for _, gv in self.group_vectorizers.items()])
    @property
    def max_words(self): return self._max_words
                               
    def __init__(self, wire_names):
        group_words = defaultdict(set)
        #words = set()
        
        # determine number of word groups based on wire_names
        idx = np.argmax(list(map(
            lambda x: len(list(util.words_from_name(x, pad=True))),
            wire_names,
        )))
        mwire = wire_names[idx]
        self._max_words = len(list(util.words_from_name(mwire, pad=True)))
        
        for wire_name in wire_names:
            for i, (w1, w2) in self.__iter_groups__(wire_name):
                for w in w1, w2:
                    group_words[i].add(w)
                    #if w != None:
                    #    words.add(w)
        self.group_vectorizers = dict([(i, GroupVectorizer(words)) for (i, words) in group_words.items()])
        
    def __words_from_name__(self, wire_name):
        base_words = list(util.words_from_name(wire_name, pad=True))
        slop = self._max_words - len(base_words)
        # can pad with the wire_name itself so wires with smaller 
        # number of words are not biased to cluster with each other
        #pad = None
        pad = wire_name
        return chain(base_words, [pad]*slop)
    
    def __iter_groups__(self, wire_name):
        return enumerate(pairwise(self.__words_from_name__(wire_name)))
        
    def get_vec(self, wire_name):
        vs = np.hstack(
            [self.group_vectorizers[i].get_vec(words)
                for i, words in self.__iter_groups__(wire_name)]
        )
        return np.hstack(vs)
    
    def get_attrs(self):
        return np.hstack([gv.get_attrs() for i, gv in sorted(self.group_vectorizers.items())])

