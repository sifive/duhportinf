import numpy as np
import operator
import cvxopt
from collections import Counter, defaultdict
from cvxopt import matrix, solvers
from cvxopt.modeling import variable, dot, op
from cvxopt.modeling import sum as cvx_sum
from . import util

solvers.options['show_progress'] = False
solvers.options['glpk'] = dict(msg_lev='GLP_MSG_OFF')

def _get_port_words(interface, bus_def):
    dup_words = get_dup_words(interface.ports)
    # get tokens for all port names (less duplicate words appearing in all
    # signals) and bus def logical names and return jaccard distance as a
    # measure of compatibility
    p_words = set(util.flatten(
        [util.words_from_name(p[0]) for p in interface.ports]
    ))
    p_words -= dup_words
    b_words = set(util.flatten([
        bus_def.words_from_name(p[0])
        for pp in [bus_def.req_ports, bus_def.opt_ports] for p in pp
    ]))
    return p_words, b_words

def _get_name_fcost1(interface, bus_def):
    p_words, b_words = _get_port_words(interface, bus_def)
    return util.get_jaccard_dist(p_words, b_words)

def _get_name_fcost2(interface, bus_def):
    p_words, b_words = _get_port_words(interface, bus_def)
    return util.get_frac_missing_tokens(b_words, p_words)

def get_mapping_fcost_global(interface, bus_def):
    """
    coarse cost function to cheaply estimate global (full set of ports)
    interface match to bus_def
    """
    cost = _get_mapping_fcost_base(interface, bus_def, penalize_umap=True) 
    name_cost = _get_name_fcost1(interface, bus_def)
    cost.nc = name_cost*interface.size
    return cost

def get_mapping_fcost_local(interface, bus_def):
    """
    coarse cost function to cheaply estimate local (subset of ports)
    interface match to bus_def
    """
    cost = _get_mapping_fcost_base(interface, bus_def, penalize_umap=False) 
    name_cost = _get_name_fcost2(interface, bus_def)
    cost.nc = name_cost
    return cost

def _get_mapping_fcost_base(interface, bus_def, penalize_umap=True):

    def sum_across(keys, cnts):
        return sum([cnts[k] for k in keys])

    # collapse vectors
    ports = interface.get_ports_to_map()
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
        cost += MatchCost(0,1,1)*brc

        # then match optional ports (no cost for unmatched optional bus
        # ports)
        num_dir_matched = min(ppc, boc)
        ppc -= num_dir_matched
        boc -= num_dir_matched

        # the rest of the unmatched ports
        cost += MatchCost(0,1,0)*num_dir_matched
        # only penalize if specified
        if penalize_umap:
            cost += MatchCost(0,1,1)*ppc

    return cost

def map_ports_to_bus(interface, bus_def, penalize_umap=True):
    """
    optimally map interface ports to bus definition {req, opt} ports by
    formulating as a convex LP and solving
    """
    # get cost functions from closure, which takes into account specifics of
    # bus_def
    match_cost_func, mapping_cost_func = get_cost_funcs(interface, bus_def)

    ports = interface.get_ports_to_map()
    ports1 = list(ports)
    ports2 = list(bus_def.req_ports)
    ports2.extend(bus_def.opt_ports)

    m, n  = len(ports1), len(ports2)
    C = np.zeros((m, n))
    for i, p1 in enumerate(ports1):
        for j, p2 in enumerate(ports2):
            C[i,j] = match_cost_func(p1, p2).value

    # swap phy ports with bus def so that the columns are always the ones
    # underdetermined
    swap = False
    if m > n:
        swap = True
        m, n = n, m
        ports1, ports2 = ports2, ports1
        C = C.T

    def is_satisfiable(X):
        # test assignment satisfies row/col constraints of assignment
        # problem
        return (
            np.all(np.sum(X,axis=1) == 1) and
            np.all(np.sum(X,axis=0) <= 1) and
            np.all(np.sum(X,axis=0) >= 0)
        )

    X = _get_greedy_assignment(C)
    if not is_satisfiable(X):
        X = _get_convex_opt_assignment(C)
        #assert is_satisfiable(X)
    
    mapping = {ports1[i] : ports2[j] for i, j in np.argwhere(X)}
    if swap:
        mapping = {v:k for k, v in mapping.items()}
    sideband_ports = get_sideband_ports(
        mapping, 
        ports,
        bus_def,
        match_cost_func,
    )
    # create a separate 'best guess' mapping for sideband ports
    # all ports without a primary mapping mapped to None
    sideband_mapping = {
        k : v for k,v in mapping.items() if k in sideband_ports
    }
    sideband_mapping.update({
        k : None for k in sideband_ports if k not in mapping
    })
    # remove sideband ports from primary mapping
    for p in sideband_ports:
        if p in mapping:
            del mapping[p]
    # assign sideband signals to user groups if they are specified
    user_group_mapping, unmapped_ports = get_user_group_assignment(
        interface,
        sideband_ports,
        bus_def,
    )

    bus_mapping = BusMapping(
        mapping = mapping,
        sideband_mapping = sideband_mapping,
        user_group_mapping = user_group_mapping,
        unmapped_ports = unmapped_ports,
        match_cost_func = match_cost_func,
        bus_def = bus_def,
    )
    cost = mapping_cost_func(bus_mapping, penalize_umap)
    assert set(ports).issubset(set(bus_mapping.get_ports())), \
        "bus mapping port designation broken"
    # normalize cost to the number of physical ports matched
    cost = MatchCost.normalize(cost, len(ports))
    bus_mapping.cost = cost
    return bus_mapping
    
def _get_greedy_assignment(C):
    # greedily select the lowest cost col port for each row port
    rsel = np.argmin(C, axis=1)
    X = np.zeros(C.shape, dtype=bool)
    rmask = (np.arange(len(rsel)), rsel)
    X[rmask] = True
    return X

def _get_convex_opt_assignment(C):
    m,n = C.shape
    c = matrix(C.reshape(m*n))
    x = variable(m*n)
    constraints = [
        x >= 0,
        x <= 1,
    ]
    # row constraints
    for i in range(m):
        #print('setting constraint', i*n, i*n+n)
        constraints.append(
            cvx_sum(x[i*n:i*n+n]) == 1
        )
    # col constraints
    # add constraints so max number of assignments to each port in ports2
    # is 1 as well
    for j in range(n):
        #print(list(range(j, m*n, n)))
        constraints.append(
            cvx_sum([x[jj] for jj in range(j, m*n, n)]) <= 1
        )

    # NOTE must use external solver (such as glpk), the default one is
    # _very_ slow
    op(
        dot(c, x),
        constraints,
    ).solve(solver='glpk')
    X = np.array(x.value).reshape(m,n) > 0.01
    return X

#--------------------------------------------------------------------------
# helpers for computing cost function
#--------------------------------------------------------------------------
def get_dup_words(ports):
    """
    get port words that appear in *all* ports
    """
    ports = set(ports)
    all_port_words = util.flatten([
        list(set(util.words_from_name(p[0])))
        for p in ports
    ])
    dup_words = set()
    for w, cnt in Counter(all_port_words).most_common():
        if cnt == len(ports):
            dup_words.add(w)
    return dup_words

def get_cost_funcs(interface, bus_def):
    """
    determine cost functions in a closure with access to bus_def
    """ 
    dup_words = get_dup_words(interface.ports)
    def match_cost_func(phy_port, bus_port):

        p_words = set(util.words_from_name(phy_port[0])) - dup_words
        b_words = bus_def.words_from_name(bus_port[0])
        cost_n = util.get_jaccard_dist(p_words, b_words)
        
        return MatchCost(
            # name attr mismatch
            cost_n,
            # width mismatch (either being None does *not* count as a match)
            (phy_port[1] != bus_port[1]) and (None not in [phy_port[1], bus_port[1]]),
            # direction mismatch
            (phy_port[2] != bus_port[2]),
        )
    
    # NOTE this function closure actually includes the match_cost_func defined
    # above
    def mapping_cost_func(bm, penalize_umap):
        cost = MatchCost.zero()
        # add penalties for all mapped signals
        cost += sum([match_cost_func(p1, p2) for p1, p2 in bm.mapping.items()])
        # penalize sideband candidates as unmapped
        if penalize_umap:
            cost += MatchCost(0,1,1)*len(bm.sbm)
        # penalize only width+direction for unmapped bus ports
        umap_busports = set(bm.bus_def.req_ports) - set(bm.mapping.values())
        cost += MatchCost(0,1,1)*len(umap_busports)
        return cost

    return match_cost_func, mapping_cost_func

def get_sideband_ports(mapping, ports, bus_def, match_cost_func):
    """
    tag ports that are either not mapped or whose name match score is poor
    as compared to the rest of the mapped ports.  these are most likely
    user defined signals.
    """
    # designate phy ports as sideband based on the number of tokens from
    # the bus_def port that are missing from the tokens in the mapped phy
    # port
    num_missing_tokens = [
        util.get_num_missing_tokens(bp[0], pp[0]) 
        for pp, bp in mapping.items()
    ]
    # label mappings as sideband if they are missing more than 1 token
    # than the median mapping
    cutoff = np.median(num_missing_tokens) + 1
    sideband_mapping = dict(filter(
        lambda x: (
            util.get_num_missing_tokens(x[1][0], x[0][0]) > cutoff
        ),
        mapping.items(),
    ))
    sideband_ports = set(sideband_mapping.keys())
    # include unmapped ports as sideband as well
    umap_ports = set(ports) - set(mapping.keys())
    sideband_ports |= umap_ports
    
    return sideband_ports

def get_user_group_assignment(interface, ports, bus_def):
    """
    assign ports to the appropriate most appropriate user group of the
    busdef
    """
    # strip shared prefix between ports for determing user group
    # assignment
    sprefix = interface.prefix
    bd_user_port_groups = bus_def.user_port_groups
    if len(bd_user_port_groups) == 0:
        return {}, ports

    def get_user_group_port(port):
        # return the port of the user group with the prefix match nearest
        # to the root of the given port name
        for w in util.words_from_name(port[0][len(sprefix):]):
            for prefix, uport in bd_user_port_groups:
                # prefix *and* direction must match to be assigned to a group
                if w.startswith(prefix) and port[2] == uport[2]:
                    return uport
        return None

    user_group_mapping = defaultdict(list)
    for port in ports:
        uport = get_user_group_port(port)
        user_group_mapping[uport].append(port)

    # all ports not assigned to a valid user group are considered unmapped
    umap_ports = user_group_mapping[None]
    del user_group_mapping[None]

    return user_group_mapping, umap_ports

# FIXME should probably have proper accessors to prevent errors in
# mutating state
class BusMapping(object):

    @property
    def m(self): return self.mapping
    @property
    def sbm(self): return self.sideband_mapping
    @property
    def mc_func(self): return self.match_cost_func
    @property
    def umap(self): return self.unmapped_ports

    @classmethod
    def duplicate(cls, bm):
        return cls(
            cost             = MatchCost.duplicate(bm.cost),
            mapping          = dict(bm.mapping),
            sideband_mapping = dict(bm.sideband_mapping),
            user_group_mapping = dict(bm.user_group_mapping),
            unmapped_ports = set(bm.unmapped_ports),
            match_cost_func  = bm.match_cost_func,
            bus_def          = bm.bus_def,
            fcost            = MatchCost.duplicate(bm.fcost),
        )

    def __init__(self, **kwargs):
        self.cost               = None
        self.mapping            = None
        self.sideband_mapping   = None
        self.user_group_mapping = None
        self.unmapped_ports     = None
        self.match_cost_func    = None
        #self.mapping_cost_func = None
        self.bus_def            = None
        self.fcost              = None
        for k, v in kwargs.items():
            assert hasattr(self, k), \
                'invalid kwargs {} for BusMapping'.format(k)
            setattr(self, k, v)
        assert None not in [
            self.mapping,
            self.sideband_mapping,
            self.match_cost_func,
            self.bus_def,
        ]

    def get_ports(self):
        return set(self.m.keys()) | set(self.sbm.keys())

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
    # cost weights
    NAME_W = 2
    WIDTH_W = 1
    # heavily penalize directionality mismatch
    #DIR_W = 1
    DIR_W = 4

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
    def __neg__(self, other):
        return MatchCost(
            -self.nc,
            -self.wc,
            -self.dc,
        )

    @classmethod
    def duplicate(cls, mc):
        return cls(mc.nc, mc.wc, mc.dc)
    @classmethod
    def zero(cls):
        return cls(0,0,0)
    @classmethod
    def normalize(cls, cost, n):
        """
        Normalize the name mismatch cost to the number of wires this cost
        was computed.  Want to compare the *average* name mismatch rate of
        a wire, not cumulative.  The width+direction costs should be
        cumulative by contrast
        """
        return cls(
            cost.nc/n,
            cost.wc,
            cost.dc,
        )

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
        return '{:2.2f}(n:{:2.2f};w:{};d:{})'.format(
            self.value,
            self.nc,
            self.wc,
            self.dc,
        )

