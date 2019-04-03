# DUH inference implementation overview

This describes how the inference package takes as input both a set of bus
definitions and a flat list of module ports, and uses these to infer the
set of bus interfaces specified in the module.  

Given a single bus definition, the optimal mapping (or assignment) of a
set of ports to this single bus definition can be found using linear
programming (see [assignment
problem](https://en.wikipedia.org/wiki/Assignment_problem)).  However,
solving a single linear program is an expensive operation in itself.
Naively enumerating all possible groupings of input ports, and solving as
many linear programs as there are input bus definitions for every group
within a grouping, is an infeasible approach to determining correct bus
interfaces.

This package uses a set of heuristics to greatly reduce the total number
of linear programs that needs to be solved.  A [prefix
tree](https://en.wikipedia.org/wiki/Radix_tree) is first used to propose
an intial set of port groups that takes into account the tendency of
designers to encode hierarchy into names of ports.  For
all possible pairings of these initial port groups with the set of input
bus definitions, a cheap cost function is computed to filter out the
pairings unlikely to yield high quality mappings.  The remaining much
smaller set of pairings of port groups and input bus definitions are then
scored by solving the corresponding linear programs.

The resulting scores are used to determine port groups with their lowest cost
bus definition and a short list of low cost alternative bus definitions.

## Components

### bus definition loader

Bus specifications reside in `duh-bus` files and can describe either
a master or slave definition or both. Loading of `duh-bus` files is described
in the class definition `BusDef` in `busdef.py`.

### port prefix tree

The process for building a  prefix tree from a set of input port names is
described in the class definition `BundleTree` in `_bundle.py`.  The
prefix tree is built as follows:

1) *Port name tokenization*: Each port name is first converted to a
sequence of tokens, which induces a prefix subtree.

2) *Prefix tree construction*: These prefix subtrees are combined to yield
a prefix tree over all input ports.

3) *Vector node tagging*: Prefix tree nodes that contain ports as 
children that form a vector are tagged and reformatted.

4) *Passthrough node removal*: Passthrough nodes (with only a single
child) are flattened through to their parent node.

##### 1) Port name tokenization

All port names are first tokenized into words as described in
`words_from_name()` in `util.py`.  The following transformations are applied
in sequence to each name:
* camelCase converted to snake\_case
* all characters converted to lowercase
* '\_' characters are inserted around groups of consecutive numbers
* words are tokenized using the '\_' characters as delimiters.

The following ports:
```python
'int_foo_1'
'int_foo_2'
'int_foo_3'
'int_bar_1'
'int_bar_sub_1'
'int_bar_diff_baz'
'int_test'
```

would generate the following set of tokens:
```python
['int', 'foo', '1']
['int', 'foo', '2']
['int', 'foo', '3']
['int', 'bar', '1']
['int', 'bar', 'sub', '1']
['int', 'bar', 'diff', 'baz']
['int', 'test']
```

which would generate the following prefix subtrees:
```
  int  int  int  int  int  int  int
   |    |    |    |    |    |    | 
  foo  foo  foo  bar  bar  bar test*
   |    |    |    |    |    |
   1*   2*   3*   1*  sub  diff
                       |    |
                       1*  baz*
```

where `*` denotes nodes with corresponding ports attached.

##### 2) Prefix tree construction

The above subtrees are combined to produce the following prefix tree:
```
      int____________________
     /           \           \
    foo____      bar______  test*
   /   \   \    /   \     \
  1*   2*  3*  1*   sub  diff
                     |     |
                    1*   baz*
```

##### 3) Vector node tagging

Nodes corresponding to vectors of ports are tagged and reformatted.  The
ports `int_foo_1`, `int_foo_2`, and `int_foo_3` form a vector and the
above prefix tree would be restructured:
```
           int____________________
          /           \           \
       foo(v)         bar______  test*
          |          /   \     \
  ['1', '2', '3']*  1*   sub  diff
                          |     |
                         1*   baz*
```

##### 4) Passthrough node removal

Nodes that have only a single child are then flattened to remove
unnecessary hierarchy.  In the example, the node corresponding to "diff"
in `int_bar_diff_baz` and the node corresponding to "sub" in
`int_bar_sub_1` are both passthroughs.  Flattening of a node means that
its name is emended to include that of the child node, and the child node
is skipped over:
```
           int____________________
          /           \           \
       foo(v)         bar_______  test*
          |          /   \      \
  ['1', '2', '3']*  1*  sub_1*  diff_baz*
```


## Initial bus interface search

Each non-leaf node in a port prefix tree induces a group of ports with
names that share a common prefix. All of these nodes are first scored
against the entire input set of bus definitions using a fast and cheap to
compute cost function (fcost).

The use of fcost as a first-pass filter of port prefix tree nodes is
implemented in `main_portinf.py` in the function `_get_bus_pairings()`.  

#### The fcost approach

The fcost function is implemented in `_optimize.py` in the function
`_get_mapping_fcost_base()` and takes as input a single interface, which
describes a set of input ports (each with a name, width, and direction),
and a single bus interface, which describes a set of required and optional
ports (each with a name, width, and direction).  The output of fcost is a
`MatchCost` object (also described in `_optimize.py`) that captures the
sum total of {name, width, direction} mismatch penalties.  The scalar
value of these `MatchCost` objects, which is used in comparator operations, is a
linear combination of these penalties that uses pre-specified weights.

Fcost uses a greedy approach that assigns interface ports first to
required and then to optional bus definition ports that match {width,
direction} (without any regards to port or logical names).  These first
matches are considered perfect and incur zero `MatchCost`.

The remaining interface ports are then assigned first to required and then
to optional bus definitions ports that match {direction}, but mismatch
{width}.  Each such assignment incurs a single width `MatchCost` penalty.

Each of the remaining unassigned interface ports and *required* bus definition
ports incur a single width and direction `MatchCost` penalty.

Lastly, a pseudoalignment name score between the set of interface port
names and the set of bus definition logical names is computed as the
Jaccard distance of all 2-character and 3-character tokens present within
each set of names.  A lower Jaccard distance implies a higher amount of
shared tokens between the two name sets and that they are more compatible.

This fcost function is cheap to compute as there is no need to optimize
over all possible pairings of interface and bus definitions ports, and it
can be computed with a couple of scans that are linear in the total number of
interface ports.  For each interface, bus definitions are sorted in
increasing order of their global and local fcost scores (see below), and
only the lowest scoring ones are considered for further mapping.

#### Global versus local fcost scoring

Occasionally designers of modules will take advantage of the fact that
multiple bus interfaces do *not* collide in logical namespace and can be
specified using the same prefix.  Consider two separate interfaces that
share the same prefix:

```python
# APB-like interface
'int_PADDR',
'int_PSELx',
'int_PENABLE',
'int_PWRITE',
'int_PRDATA',
'int_PWDATA',
'int_PREADY',
# AHB-like interface
'int_HADDR',
'int_HBURST',
'int_HSIZE',
'int_HTRANS',
'int_HWDATA',
'int_HWRITE',
'int_HRDATA',
'int_HREADYOUT',
'int_HRESP',
'int_HREADY',
```

Although this set of ports specifies two separate bus interfaces, the
resulting prefix tree over the names will only ever yield them jointly
within the same group.  This joint group will have lower fcost scores
against (incorrect) wider interfaces such as AXI and higher fcost scores
against the correct narrower APB/AHB interfaces due to mismatches incurred
by superfluous ports within the group.   

To allow potentially correct narrower interfaces to pass the fcost filter,
a global and local fcost match score is computed for each interface and
bus definition pair. A global fcost match assigns `MatchCost` penalties
for all unmatched interface ports whereas a local fcost match does not. In
    a local fcost match, superfluous ports on the interface do not incur
    additional `MatchCost` penalties and the overall score is typically
    dominated by the pseudoalignment name score.  
    
In the above example, the APB and AHB bus definitions both have
logical names closer in pseudoalignment distance to the interface ports
than (incorrect) wider bus defintions, and will have decidedly lower
local fcost scores.

<a name="pruning-groups"></a>
#### Pruning of suboptimal interface groups

Each node within the prefix tree is assigned the lowest fcost score that
was computed between the corresponding interface and all input bus
definitions.  Interface groups that do not achieve the lowest fcost for at
least `min_num_leaves` (default=4) module ports are eliminated from
further consideration.  This pruning is described in `bundle.py` in the
method `BundleTree.get_optimal_nids()`.

This pruning process eliminates partial bus interface matches for prefix
tree nodes that are descendents of a correct interface node.  In these
cases, a single fully specified bus interface is clearly preferred over
multiple partial bus interfaces.

## Optimal bus interface scoring by solving linear programs

The remaining much smaller set of port group interfaces and their
corresponding candidate bus definitions are then fully (and optimally)
mapped by solving a series of linear programs.  Each optimal mapping has
an associated `MatchCost`, which is the sum total each `MatchCost`s
incurred by each {interface port, bus definition port} pair.

This optimal bus interface scoring is implemented in `main_portinf.py` in
the function `_get_initial_bus_matches()`.

#### Specifying the assignment linear program

The specification of the assignment linear program (and optimization
procedure) is described in `_optimize.py` in the function
`map_ports_to_bus()`.  This function first computes `MatchCost`s for every
pair of interface ports and bus definition ports to specify a total cost
matrix.  Pairs that mismatch in width or direction incur corresponding
`MatchCost` penalties, and the `MatchCost` name penalty is computed as a
pseudoalignment score between the interface and bus definition port names.

Rows in the cost matrix correspond to interface ports and columns
correspond to bus definition ports.  An adjacency matrix (with 0,1
entries) specifies the mapping of interface ports to bus definition ports.
An optimal mapping between interface and bus definition ports can be
specified as a particular adjacency matrix that achieves the lowest sum
total cost, subject to the constraint that each port is assigned only
once. This desired optimal adjacency matrix can be completely described as
a linear program.  A further explanation of the problem statement can be
found in a description of the [assignment
problem](https://en.wikipedia.org/wiki/Assignment_problem)). 

#### Optimization

The specification of the linear program and invocation of an interior
point solver are both done using [cvxopt](https://cvxopt.org/).  The
default python solver in cvxopt is quite slow, so the current
implementation relies on invoking the external [glpk
solver](https://www.gnu.org/software/glpk/) and this can be specified as
an argument to cvxopt's `solve()` function.

#### Tagging of sideband user ports

For a given interface and bus definition and the corresponding optimal
mapping, interface ports are then tagged as user "sideband" signals on the
basis of port name and logical name compatibility.  Each interface port
name and bus definition logical name is first broken up into its
2-character and 3-character tokens.  For each {interface port, bus
definition port} assignment pair, the number of bus bus definition logical
name tokens missing from the corresponding interface port name tokens is
computed.  If a particular interface port is missing *more than* the median
number of tokens across all assignment pairs, then the interface
port is tagged as a user sideband signal.

As an example, consider the following mapping:
```python
# <interface port> : <bus def port>
{
    'ahb_mst2_HADDR'  : 'HADDR',
    'ahb_mst2_HBURST' : 'HBURST',
    'ahb_mst2_HSIZE'  : 'HSIZE',
    'ahb_mst2_HTRANS' : 'HTRANS',
}
```

In this case, all the tokens in the bus definition logical names are
present in the corresponding interface port names and no ports are
tagged as user sideband signals.

However, consider the following mapping:
```python
# <interface port> : <bus def port>
{
    'pipe1_RATE'           : 'RATE',
    'pipe1_TXMARGIN'       : 'TXMARGIN',
    'pipe1_TXSWING'        : 'TXSWING',
    'pipe1_BLOCKALIGNCTRL' : 'BLKALNCTRL',
    'pipe1_ERRFUNC'        : 'RXSYNCHDR',
}
```

In this case, the first three interface ports contain all the
tokens from the corresponding bus definition logical names, so the median
number of missing tokens is zero.  The last two interface ports
`'pipe1_BLOCKALIGNCTRL'` and `'pipe1_ERRFUNC'` are missing multiple tokens
from the corresponding bus definition logical names and will both be
tagged as user sideband signals.

Tagging of user sideband signals is implemented in `_optimize.py` in the
function `get_sideband_ports()`.

#### Pruning of suboptimal interface groups

Interface port groups are pruned from the output using the same procedure
[previously described](#pruning-groups) under the first-pass fcost
computation using optimal mapping `MatchCost`s.

