import numpy as np
import cvxopt
from cvxopt import matrix, solvers
from cvxopt.modeling import variable, dot, op
from cvxopt.modeling import sum as cvx_sum
import editdistance as ed
from . import util
from .busdef import BusDef

solvers.options['show_progress'] = False

#bus_words_from_name = None

def map_port_sets(ports1, ports2):
    ports1 = list(ports1)
    ports2 = list(ports2)
    m, n  = len(ports1), len(ports2)
    swap = False
    if m > n:
        swap = True
        m, n = n, m
        ports1, ports2 = ports2, ports1
    C = np.zeros((m, n))
    for i, p1 in enumerate(ports1):
        for j, p2 in enumerate(ports2):
            C[i,j] = match_cost(p1, p2)
    
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
    cost = _get_mapping_cost(mapping, ports1, ports2)
    if swap:
        return cost, {v:k for k, v in mapping.items()}
    else:
        return cost, mapping

def _get_mapping_cost(mapping, ports1, ports2):
    umap1 = set(ports1) - set(mapping.keys())
    umap2 = set(ports2) - set(mapping.values())
    cost = 0
    cost += sum([match_cost(p1, p2) for p1, p2 in mapping.items()])
    nil_port = ('', None, None)
    cost += sum([match_cost(nil_port, p) for p in umap1])
    cost += sum([match_cost(nil_port, p) for p in umap2])
    return cost
    

def match_cost(phy_port, bus_port):
    
    def name_dist(w1, w2):
        #return ed.eval(w1, w2)
        return ed.eval(w1, w2) / max(len(w1), len(w2))

    # FIXME for now hardcode in functions that are used to get words from name
    # for both ports and buses
    p_words = util.words_from_name(phy_port[0].lower())
    b_words = util.words_from_name(bus_port[0].lower())
    cost_n = 0
    for b_word in b_words:
        cost_n += min(map(lambda w: name_dist(b_word, w), p_words))
    
    return (
        # name attr mismatch
        cost_n + 
        # width mismatch
        1*(phy_port[1] != bus_port[1]) +
        # direction mismatch
        1*(phy_port[2] != bus_port[2])
    )

