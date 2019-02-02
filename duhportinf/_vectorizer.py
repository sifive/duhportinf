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
    @property
    def num_groups(self): return len(self.group_vectorizers)
    @property
    def group_sizes(self): 
        return [
            gv.size 
            for k, gv in sorted(
                self.group_vectorizers.items(),
                key=lambda x: x[0],
             )
        ]
                               
    def __init__(self, wire_names):
        group_words = defaultdict(set)
        
        # determine number of word groups based on wire_names
        idx = np.argmax(list(map(
            lambda x: len(list(util.words_from_name(x))),
            wire_names,
        )))
        mwire = wire_names[idx]
        self._max_words = len(list(util.words_from_name(mwire)))
        
        for wire_name in wire_names:
            for i, words in self.__iter_groups__(wire_name):
                group_words[i] |= set(words)
        self.group_vectorizers = dict([
            (i, GroupVectorizer(words)) 
            for (i, words) in group_words.items()
        ])
        
    def __words_from_name__(self, wire_name):
        base_words = list(util.words_from_name(wire_name))
        slop = self._max_words - len(base_words)
        # can pad with the wire_name itself so wires with smaller 
        # number of words are not biased to cluster with each other
        # NOTE this explodes the size of the resulting vectors (since
        # wire names with a small number of words will be passed through
        # to the dictionaries of later groups).  this will make
        # hierarchical clustering extremely slow if not using *euclidean*
        # metric, for which pairwise computation is fast.  currently using
        # mahalanobis metric to preferentially prefer prefix matches
        # NOTE mahalanobis weight matrix is strong enough such that the
        # bias in similarity between short wire names with different
        # paddings doesn't affect anything
        #pad = wire_name
        pad = None
        return list(chain(base_words, [pad]*slop))
    
    def __iter_groups__(self, wire_name):
        # NOTE previously created pairwise groups for *all* words in a wire_name, but
        # resulting bit vectors were large and increased time to perform
        # hierarchical clustering
        #return enumerate(pairwise(self.__words_from_name__(wire_name)))
        words = self.__words_from_name__(wire_name)
        gidx = 0
        fp = 2
        # yield the first word as a singleton since it should be the
        # most informative for grouping
        yield 0, [words[0]]
        # yield pairs of words for up to the first three words of the wire_name
        for i, word_pair in enumerate(pairwise(words)):
            if i == fp:
                break
            gidx = i + 1
            yield gidx, word_pair
        # then yield singleton words for the rest
        gidx += 1
        for word in words[fp+1:]:
            yield gidx, [word]
            gidx += 1
        return
        
    def get_vec(self, wire_name):
        vs = np.hstack(
            [self.group_vectorizers[i].get_vec(words)
                for i, words in self.__iter_groups__(wire_name)]
        )
        return np.hstack(vs)
    
    def get_attrs(self):
        return np.hstack([gv.get_attrs() for i, gv in sorted(self.group_vectorizers.items())])

