import numpy as np
import cvxopt
from collections import Counter
from cvxopt import matrix, solvers
from cvxopt.modeling import variable, dot, op
from cvxopt.modeling import sum as cvx_sum
import editdistance as ed
from . import util
from .busdef import BusDef

solvers.options['show_progress'] = False

# cost weights
# uniform for now
NAME_W = 1
WIDTH_W = 1
DIR_W = 1

def get_mapping_fcost(ports, bus_def):
    """
    coarse cost function to cheaply estimate how good a potential mapping
    will be
    """
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
    allkeys = []
    for d in ds:
        allkeys.extend(d.keys())

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

    in_keys  = filter(lambda x:x[-1] == np.sign( 1), allkeys)
    out_keys = filter(lambda x:x[-1] == np.sign(-1), allkeys)

    def sum_across(keys, cnts):
        return sum([cnts[k] for k in keys])

    # try coarser matches requiring just direction to match
    cost = 0
    for keys in [in_keys, out_keys]:
        ppc = sum_across(keys, phy_port_cnts)
        brc = sum_across(keys, bus_req_port_cnts)
        boc = sum_across(keys, bus_opt_port_cnts)

        # first match required ports
        num_dir_matched = min(ppc, brc)
        ppc -= num_dir_matched
        brc -= num_dir_matched
        
        cost += (WIDTH_W)*num_dir_matched
        cost += (WIDTH_W+DIR_W)*brc

        # then match optional ports (no cost for unmatched optional bus
        # ports)
        num_dir_matched = min(ppc, boc)
        ppc -= num_dir_matched
        boc -= num_dir_matched

        # the rest of the unmatched ports
        cost += (WIDTH_W)*num_dir_matched
        cost += (WIDTH_W+DIR_W)*ppc
    return cost

def map_ports_to_bus(ports, bus_def):
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
            C[i,j] = match_cost(p1, p2)
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
        
    # add constraints so max number of assignments 
    # to each port in ports2 is 1 as well
    for j in range(n):
        #print(list(range(j, m*n, n)))
        constraints.append(
            cvx_sum([x[jj] for jj in range(j, m*n, n)]) <= 1
        )
    op(
        dot(c, x),
        constraints,
    ).solve()
    X = np.array(x.value).reshape(m,n) > 0.01
    
    mapping = {ports1[i] : ports2[j] for i, j in np.argwhere(X)}
    if swap:
        mapping = {v:k for k, v in mapping.items()}
    cost = mapping_cost(mapping, ports, bus_def)
    return cost, mapping, match_cost

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
        
        return (
            # name attr mismatch
            NAME_W*cost_n + 
            # width mismatch
            WIDTH_W*(phy_port[1] != bus_port[1]) +
            # direction mismatch
            DIR_W*(phy_port[2] != bus_port[2])
        )
    
    def mapping_cost_func(mapping, ports, busdef):
        umap_ports = set(ports) - set(mapping.keys())
        umap_busports = set(busdef.req_ports) - set(mapping.values())
        cost = 0
        cost += sum([match_cost(p1, p2) for p1, p2 in mapping.items()])
        nil_port = ('', None, None)
        cost += sum([match_cost(nil_port, p) for p in umap_ports])
        cost += sum([match_cost(nil_port, p) for p in umap_busports])
        return cost

    return match_cost_func, mapping_cost_func
