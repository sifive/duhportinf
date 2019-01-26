import numpy as np
import operator
import cvxopt
from collections import Counter
from cvxopt import matrix, solvers
from cvxopt.modeling import variable, dot, op
from cvxopt.modeling import sum as cvx_sum
import editdistance as ed
from . import util
from .busdef import BusDef

solvers.options['show_progress'] = False

def get_mapping_fcost(ports, bus_def):
    """
    coarse cost function to cheaply estimate how good a potential mapping
    will be
    """
    def sum_across(keys, cnts):
        return sum([cnts[k] for k in keys])

    # TODO can assign some cost to the closeness of the port name
    # alphabets (include name/library for bus def)
    
    # strip name and just match based off of width+direction
    phy_port_cnts = Counter(map(lambda x: tuple(x[1:]), ports))
    bus_req_port_cnts = Counter(map(lambda x: tuple(x[1:]), bus_def.req_ports))
    bus_opt_port_cnts = Counter(map(lambda x: tuple(x[1:]), bus_def.opt_ports))

    ds = [
        phy_port_cnts,
        bus_req_port_cnts,
        bus_opt_port_cnts,
    ]
    allkeys = set()
    for d in ds:
        allkeys |= set(d.keys())

    for k in allkeys:
        ppc = phy_port_cnts[k]
        brc = bus_req_port_cnts[k]
        boc = bus_opt_port_cnts[k]

        # first match required ports
        num_matched = min(ppc, brc)
        ppc -= num_matched
        brc -= num_matched

        # then match optional ports
        num_matched = min(ppc, boc)
        ppc -= num_matched
        boc -= num_matched

        # update counts with unmatched info
        phy_port_cnts[k]     = ppc
        bus_req_port_cnts[k] = brc
        bus_opt_port_cnts[k] = boc

    in_keys  = list(filter(lambda x:x[-1] == np.sign( 1), allkeys))
    out_keys = list(filter(lambda x:x[-1] == np.sign(-1), allkeys))

    # try coarser matches requiring just direction to match
    cost = MatchCost.zero()
    for (d, keys) in [('in', in_keys), ('out', out_keys)]:
        ppc = sum_across(keys, phy_port_cnts)
        brc = sum_across(keys, bus_req_port_cnts)
        boc = sum_across(keys, bus_opt_port_cnts)

        # first match required ports
        num_dir_matched = min(ppc, brc)
        ppc -= num_dir_matched
        brc -= num_dir_matched
        
        cost += MatchCost(0,1,0)*num_dir_matched
        # add harsh penalty for unmatched bus ports
        cost += 4*MatchCost(0,1,1)*brc

        # then match optional ports (no cost for unmatched optional bus
        # ports)
        num_dir_matched = min(ppc, boc)
        ppc -= num_dir_matched
        boc -= num_dir_matched

        # the rest of the unmatched ports
        cost += MatchCost(0,1,0)*num_dir_matched
        cost += MatchCost(0,1,1)*ppc

    return cost

def map_ports_to_bus(ports, bus_def):
    """
    optimally map ports to bus definition {req, opt} ports by formulating
    as a convex LP and solving
    """
    # get cost functions from closure, which takes into account specifics of
    # bus_def
    match_cost, mapping_cost = get_cost_funcs(ports, bus_def)

    ports1 = list(ports)
    ports2 = list(bus_def.req_ports)
    ports2.extend(bus_def.opt_ports)

    m, n  = len(ports1), len(ports2)
    C = np.zeros((m, n))
    for i, p1 in enumerate(ports1):
        for j, p2 in enumerate(ports2):
            C[i,j] = match_cost(p1, p2).value

    # swap phy ports with bus def so that the columns are always the ones
    # underdetermined
    swap = False
    if m > n:
        swap = True
        m, n = n, m
        ports1, ports2 = ports2, ports1
        C = C.T
    
    c = matrix(C.reshape(m*n))
    x = variable(m*n)
    constraints = [
        x >= 0,
        x <= 1,
    ]
    for i in range(m):
        #print('setting constraint', i*n, i*n+n)
        constraints.append(
            cvx_sum(x[i*n:i*n+n]) == 1
        )
        
    # add constraints so max number of assignments to each port in ports2
    # is 1 as well
    for j in range(n):
        #print(list(range(j, m*n, n)))
        constraints.append(
            cvx_sum([x[jj] for jj in range(j, m*n, n)]) <= 1
        )

    # NOTE mus use external solver (such as glpk), the default one is
    # _very_ slow
    op(
        dot(c, x),
        constraints,
    ).solve(solver='glpk')
    X = np.array(x.value).reshape(m,n) > 0.01
    
    mapping = {ports1[i] : ports2[j] for i, j in np.argwhere(X)}
    if swap:
        mapping = {v:k for k, v in mapping.items()}
    cost = mapping_cost(mapping, ports, bus_def)
    return cost, mapping, match_cost

#--------------------------------------------------------------------------
# helpers for computing cost function
#--------------------------------------------------------------------------
def get_cost_funcs(ports, bus_def):
    """
    determine cost functions in a closure with access to bus_def
    """

    def match_cost_func(phy_port, bus_port):
        
        def name_dist(w1, w2):
            return ed.eval(w1, w2)
            #return ed.eval(w1, w2) / max(len(w1), len(w2))
    
        # FIXME for now hardcode in functions that are used to get words from name
        # for both ports and buses
        p_words = util.words_from_name(phy_port[0].lower())
        b_words = bus_def.words_from_name(bus_port[0].lower())
        cost_n = 0
        for b_word in b_words:
            cost_n += min(map(lambda w: name_dist(b_word, w), p_words))
        
        return MatchCost(
            # name attr mismatch
            cost_n,
            # width mismatch
            (phy_port[1] != bus_port[1]),
            # direction mismatch
            (phy_port[2] != bus_port[2]),
        )
    
    # NOTE this function closure actually includes the match_cost_func defined
    # above
    def mapping_cost_func(mapping, ports, bus_def):
        umap_ports = set(ports) - set(mapping.keys())
        umap_busports = set(bus_def.req_ports) - set(mapping.values())
        cost = MatchCost.zero()
        cost += sum([match_cost_func(p1, p2) for p1, p2 in mapping.items()])
        # penalize only width+direction for unmapped ports
        cost += MatchCost(0,1,1)*len(umap_ports)
        cost += MatchCost(0,1,1)*len(umap_busports)
        return cost

    return match_cost_func, mapping_cost_func


def MAKE_BINARY(opfn):
    def op_func(self, other):
        if type(other) != MatchCost:
            return MatchCost(
                opfn(self.nc, other),
                opfn(self.wc, other),
                opfn(self.dc, other),
             )
        else:
            #assert type(other) == MatchCost, \
            #    "unexpected operator type {} with MatchCost".format(type(other))
            return MatchCost(
                opfn(self.nc, other.nc),
                opfn(self.wc, other.wc),
                opfn(self.dc, other.dc),
            )
    return op_func

MAKE_RBINARY = lambda opfn : lambda self, other : MatchCost(
    opfn(other, self.nc),
    opfn(other, self.wc),
    opfn(other, self.dc),
)
MAKE_COMPARATOR = lambda opfn : lambda self, other : opfn(self.value, other.value)

class MatchCost(object):    
    __add__  = MAKE_BINARY(operator.add)
    __sub__  = MAKE_BINARY(operator.sub)
    __mul__  = MAKE_BINARY(operator.mul)
    __iadd__  = MAKE_BINARY(operator.add)
    __isub__  = MAKE_BINARY(operator.sub)
    __imul__  = MAKE_BINARY(operator.mul)
    __radd__ = MAKE_RBINARY(operator.add)
    __rsub__ = MAKE_RBINARY(operator.sub)
    __rmul__ = MAKE_RBINARY(operator.mul)
    __lt__ = MAKE_COMPARATOR(operator.__lt__)
    __le__ = MAKE_COMPARATOR(operator.__le__)
    __gt__ = MAKE_COMPARATOR(operator.__gt__)
    __ge__ = MAKE_COMPARATOR(operator.__ge__)

    def __eq__(self, other):
        return (
            self.nc == other.nc and
            self.wc == other.wc and
            self.dc == other.dc
        )
    def __ne__(self, other):
        return (
            self.nc != other.nc or
            self.wc != other.wc or
            self.dc != other.dc
        )

    # cost weights # uniform for now
    NAME_W = 1
    WIDTH_W = 1
    DIR_W = 1

    def __neg__(self, other):
        return MatchCost(
            -self.nc,
            -self.wc,
            -self.dc,
        )

    @classmethod
    def zero(cls):
        return cls(0,0,0)

    @property
    def value(self):
        return (
            self.NAME_W*self.nc + 
            self.WIDTH_W*self.wc + 
            self.DIR_W*self.dc
        )

    def __init__(self, nc, wc, dc):
        self.nc = nc
        self.wc = wc
        self.dc = dc

    def __str__(self):
        return '{}(n:{};w:{};d:{})'.format(
		    self.value,
            self.nc,
            self.wc,
            self.dc,
        )

