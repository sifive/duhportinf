from itertools import chain
from collections import defaultdict
from abc import ABC
from . import util

class Interface(object):

    @classmethod
    def get_undirected(cls, ports):
        return cls([UndirectedBundle(ports)])

    @property
    def size(self): return len(self._ports)
    @property
    def ports(self): return iter(self._ports)
    @property
    def bundles(self):
        return chain(self.nonvector_bundles, self.vector_bundles)
    @property
    def vector_bundles(self):
        return list(self._vector_bundles)
    @property
    def nonvector_bundles(self):
        return list(self._nonvector_bundles)
    @property
    def mapping_width(self):
        """
        the number of attributes that would be mapped to a particular bus
        interface description
        """
        return (
            sum([b.size for b in self.nonvector_bundles]) +
            len(list(self.vector_bundles))
        )
    @property
    def prefix(self):
        prefixes = [b.prefix for b in self.bundles]
        return util.common_prefix(prefixes)

    def __init__(self, bundles):
        self._ports = util.flatten([b.ports for b in bundles])
        self._vector_bundles = list(filter(
            lambda b: type(b) == VectorBundle,
            bundles,
        ))
        self._nonvector_bundles = list(filter(
            lambda b: type(b) != VectorBundle,
            bundles,
        ))
        self._prefix_vbundle_map = {
            b.prefix:b for b in self._vector_bundles
        }
        assert (
            sum([b.size for b in self.vector_bundles]) +
            sum([b.size for b in self.nonvector_bundles])
        ) == len(self._ports)

    def is_vector(self, port):
        return port in self._prefix_vbundle_map

    def get_vector(self, port):
        assert self.is_vector(port), \
            "non-vector port {} illegally passed to get_vector()".format(port)
        return [p[0] for p in self._prefix_vbundle_map[port].ports]

    def get_ports_to_map(self):
        ports_to_map = []
        ports_to_map.extend(
            util.flatten([b.ports for b in self.nonvector_bundles])
        )
        ports_to_map.extend(
            [(b.prefix, b.width, b.dir) for b in self.vector_bundles]
        )
        return set(ports_to_map)

#--------------------------------------------------------------------------
# port group bundle designations
#--------------------------------------------------------------------------
def get_bundle_designation(ports):
    ports = list(ports)
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
        port_names = [p[0] for p in self.ports]
        return util.common_prefix(port_names)

    def __init__(self, ports):
        self._ports = ports

class UndirectedBundle(Bundle):
    def __init__(self, ports):
        super(self.__class__, self).__init__(ports)

class DirectedBundle(Bundle):
    def __init__(self, ports):
        super(self.__class__, self).__init__(ports)
        dirs = [p[2] for p in self.ports]
        same_dir = (len(set(dirs)) == 1)
        assert same_dir

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
    def range(self): return range(self._min, self._max+1)
    @property
    def width(self): return self._width
    @property
    def direction(self): return self._direction
    @property
    def dir(self): return self._direction

    def __init__(self, ports):
        super(self.__class__, self).__init__(ports)

        vindex = self.__class__.get_vector_index(self.ports)

        _, self._width, self._direction = next(self.ports)
        name_words = [util.words_from_name(p[0]) for p in self.ports]
        index_words = list(zip(*name_words))[vindex]
        assert all([w.isdigit() for w in index_words])
        indexes = [int(w) for w in index_words]
        assert util.is_range(indexes)
        self._min = min(indexes)
        self._max = max(indexes)
        # sort ports by index
        self._ports = [p for idx, p in sorted(zip(indexes, self._ports))]

