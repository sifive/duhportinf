from itertools import chain
from _ctypes import PyObj_FromPtr
import json
from jsonref import JsonRef
import json5
import re
import numpy as np
import logging

silent = False

def format_ports(in_ports):
    """
    convert input component.json5 port shorthand to
    (port_name, width, dir)
    """
    fmt_ports = []
    for name, pw in in_ports.items():
        try:
            w, d = np.abs(pw), np.sign(pw)
        except Exception as e:
            #print('Warning', (name, pw), 'not correctly parsed')
            w, d = None, np.sign(-1) if pw[0] == '-' else np.sign(1)
        fmt_ports.append((name, w, d))
    return fmt_ports

def _get_bundle_ports(tree):
    strees = [v for v in tree.values() if type(v) == dict]
    fvals  = [v for v in tree.values() if type(v) != dict]
    for stree in strees:
        fvals.extend(_get_bundle_ports(stree))
    return fvals

def get_unassigned_ports(component_json):

    with open(component_json) as fin:
        block = json5.load(fin)
        block = JsonRef.replace_refs(block)
    try:
        block['component']['model']['ports']
    except:
        logging.error('obj["component"]["model"]["ports"] not accessible in {}'.format(component_json))

    try:
        block['component']['busInterfaces']
    except:
        logging.error('obj["component"]["busInterfaces"] not accessible in {}'.format(component_json))

    all_ports = format_ports(block['component']['model']['ports'])
    bus_interfaces = block['component']['busInterfaces']

    def get_portnames(interface):
        atkey = 'abstractionTypes'
        pmkey = 'portMaps'
        vkey = 'viewRef'
        if interface['busType'] == 'bundle':
            pns_ = flatten([
            _get_bundle_ports(at[pmkey]) for at in interface[atkey] 
                    if at[vkey] == 'RTLview'
            ])
        else:
            pns_ = flatten([
                at[pmkey].values() for at in interface[atkey] 
                    if at[vkey] == 'RTLview'
            ])
        nv_pns = [p for p in pns_ if type(p) == str]
        # flatten vectors
        v_pns = flatten([p for p in pns_ if type(p) != str])
        return set(chain(v_pns, nv_pns))

    portname_sets = [
        set(get_portnames(interface)) for interface in bus_interfaces
    ]
    seen = set()
    dups = set()
    for pns in portname_sets:
        dups |= (pns & seen)
        seen |= pns
    if len(dups) > 0:
        logging.error('ports illegally belong to multiple bus interfaces:')
        for port in list(sorted(dups))[:10]:
            logging.error('  - {}'.format(port))
        if len(dups) > 10:
            logging.error('  ...')

    assn_portnames = set(seen)
    unassn_ports = [p for p in all_ports if p[0] not in assn_portnames]
    return unassn_ports

def words_from_name(name):
    # convert camelcase to '_'
    name = re.sub('(.)([A-Z][a-z]+)(.)', r'\1_\2\3', name)
    # always return lower case so case insensitive
    name = re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()
    ## insert '_' in between names and numbers
    name = re.sub('([a-zA-Z])([0-9]+)', r'\1_\2', name).lower()
    words = name.split('_')
    return words

def flatten(l): 
    return [e for ll in l for e in ll]

def is_range(digits):
    assert all([type(d) == int for d in digits])
    return tuple(sorted(digits)) == tuple(range(min(digits), max(digits)+1))

def sorted_equal(i1, i2):
    return tuple(sorted(i1)) == tuple(sorted(i2))

def equal_ranges(ranges):
    r0 = ranges[0]
    return all([sorted_equal(r0, r) for r in ranges[1:]])

def common_prefix(words):
    "Given a list of names, returns the longest common leading component"
    n1 = min(words)
    n2 = max(words)
    for i, c in enumerate(n1):
        if c != n2[i]:
            return n1[:i] 
    return n1

def get_tokens(n):
    """all pairs and triples within a string or iterable of strings"""
    if type(n) in [list, set, tuple]:
        return flatten([_get_tokens(nn) for nn in n])
    else:
        return _get_tokens(n)

def _get_tokens(n):
    n = n.replace('_', '').lower()
    tokens = [c for c in n]
    tokens.extend([''.join(cs) for cs in zip(n, n[1:])])
    tokens.extend([''.join(cs) for cs in zip(n, n[1:], n[2:])])
    return tokens

def get_jaccard_dist(n1, n2):
    """
    jaccard distance of all tokens within n1 and n2 (strings or list,set)
    """
    n1t = set(get_tokens(n1))
    n2t = set(get_tokens(n2))
    jaccard_index = len(n1t & n2t) / len(n1t | n2t)
    return 1 - jaccard_index

def get_num_missing_tokens(n1, n2):
    """"
    return number of tokens in n1 that are not present in the tokens of n2
    """
    n1t = set(get_tokens(n1))
    n2t = set(get_tokens(n2))
    return len(n1t - n2t)

def get_frac_missing_tokens(n1, n2):
    """"
    return fraction of tokens in n1 that are not present in the tokens of n2
    """
    n1t = set(get_tokens(n1))
    n2t = set(get_tokens(n2))
    return len(n1t - n2t) / len(n1t)

def get_id_gen():
    i = 0
    while True:
        yield i
        i += 1

def progress_bar(
    iteration,
    total,
    prefix = 'Progress:',
    suffix = 'Complete',
    decimals = 1,
    length = 100,
    fill = 'x',
 ): 
    """
    referenced from: https://stackoverflow.com/questions/3173320/

    Call in a loop to create terminal progress bar
    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
    """
    # hacky fix so not messing with stdout during test when logging is off
    if silent:
        return
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filledLength = int(length * iteration // total)
    bar = fill * filledLength + '-' * (length - filledLength)
    s = '\r%s |%s| %s%% %s' % (prefix, bar, percent, suffix)
    print(s, end = '\r')
    # erase bar and print complete
    if iteration == total: 
        print('\r', ' '*len(s), '\r', end='')

#--------------------------------------------------------------------------
# json handling
#--------------------------------------------------------------------------
class NoIndent(object):
    """ Value wrapper. """
    def __init__(self, value):
        self.value = value

class PrettyPrintEncoder(json.JSONEncoder):
    """
    special json encoder that selectively skips certain objects for
    indenting that are marked with a NoIndent() class wrapper

    referenced from:
    https://stackoverflow.com/questions/13249415/
    """
    FORMAT_SPEC = '@@{}@@'
    regex = re.compile(FORMAT_SPEC.format(r'(\d+)'))

    def __init__(self, **kwargs):
        # Save copy of any keyword argument values needed for use here.
        self.__sort_keys = kwargs.get('sort_keys', None)
        super(self.__class__, self).__init__(**kwargs)

    def default(self, obj):
        return (self.FORMAT_SPEC.format(id(obj)) if isinstance(obj, NoIndent)
                else super(self.__class__, self).default(obj))

    def encode(self, obj):
        format_spec = self.FORMAT_SPEC  # Local var to expedite access.
        json_repr = super(self.__class__, self).encode(obj)  # Default JSON.

        # Replace any marked-up object ids in the JSON repr with the
        # value returned from the json.dumps() of the corresponding
        # wrapped Python object.
        for match in self.regex.finditer(json_repr):
            # see https://stackoverflow.com/a/15012814/355230
            id = int(match.group(1))
            no_indent = PyObj_FromPtr(id)
            json_obj_repr = json.dumps(no_indent.value, sort_keys=self.__sort_keys)

            # Replace the matched id string with json formatted representation
            # of the corresponding Python object.
            json_repr = json_repr.replace(
                            '"{}"'.format(format_spec.format(id)), json_obj_repr)

        return json_repr

def dump_json_bus_candidates(
    output,
    component_json5,
    i_bus_mappings,
    debug=False,
):

    def expand_if_vector(interface, port):
        if interface.is_vector(port):
            return [p[0] for p in interface.get_vector(port)]
        else:
            return port
    def json_format(p):
        return (p[0], None if p[1] == None else int(p[1]), int(p[2]))
    def ref_from_name(name):
        return {'$ref': '#/definitions/busDefinitions/{}'.format(name)}
    def get_cost_obj(interface, bm):
        port_names = [p[0] for p in interface.ports]
        prefix = common_prefix(port_names)
        o = [
            ('num_ports', interface.size),
            ('prefix', prefix),
            ('num-direction-mismatch', int(bm.cost.dc)),
            ('num-width-mismatch', int(bm.cost.wc)),
        ]
        return o

    def get_cnt_base():
        with open(component_json5) as fin:
            block_obj = json5.load(fin)
        try:
            return block_obj['definitions']['pg_cnt']
        except:
            return 0
    
    portgroup_objs = []
    busint_objs = []
    busint_obj_map = {}
    busint_refs = []
    busint_alt_refs = []
    pg_cnt_base = get_cnt_base()

    for i, (interface, bus_mappings) in enumerate(sorted(
        i_bus_mappings,
        key=lambda x: x[0].size,
        reverse=True,
    )):
        pg_busints = []
        for j, bus_mapping in enumerate(bus_mappings):
            bm = bus_mapping
            busint_name = 'busint-portgroup_{}-mapping_{}-prefix_{}-{}-{}'.format(
                pg_cnt_base+i,
                j,
                interface.prefix.strip('_'),
                bm.bus_def.driver_type,
                bm.bus_def.abstract_type.name,
            )
            # for all ports in mapping, just include port names and exclude width+direction
            sbm_map  = {k:v for k,v in bm.sideband_mapping.items() if v != None}
            sbm_umap = [k for k,v in bm.sideband_mapping.items() if v == None]
                
            mapped_sideband_ports = list(sorted(
                sbm_map.items(),
                key=lambda x: bm.match_cost_func(x[0], x[1]),
            ))
            mapped_ports = list(sorted(
                bm.m.items(),
                key=lambda x: bm.match_cost_func(x[0], x[1]),
            ))

            # format portmap object
            portmap_o = {}
            portmap_o.update({bp[0]:pp[0] for pp, bp in mapped_ports})
            # expand vectors in output
            portmap_o = {
                bpn : expand_if_vector(interface, ppn) for bpn, ppn in portmap_o.items()
            }
            # add user group ports
            for uport, ports in sorted(bm.user_group_mapping.items()):
                pp = [expand_if_vector(interface, p[0]) for p in ports]
                portmap_o.update({uport[0]:pp})
            # any ports that aren't map to normal busdef {req,opt} port or
            # a busdef specified user group are unmapped
            if len(bm.unmapped_ports) > 0:
                portmap_o['__UMAP__'] = [
                    expand_if_vector(interface, p[0]) for p in bm.unmapped_ports
                ]
            # FIXME remove old
            # provide best guess mapping for sideband signals
            #portmap_o.update({bp[0]:pp[0] for pp, bp in mapped_sideband_ports})
            #if len(sbm_umap) > 0:
            #    portmap_o['__UMAP__'] = [p[0] for p in sbm_umap]

            # format debug portmap object that tags req, opt, sideband signals
            req_mapped_names = [NoIndent((bp[0], pp[0])) for pp, bp in mapped_ports if bp in bm.bus_def.req_ports]
            opt_mapped_names = [NoIndent((bp[0], pp[0])) for pp, bp in mapped_ports if bp in bm.bus_def.opt_ports]
            sideband_names =   [NoIndent((bp[0], pp[0])) for pp, bp in mapped_sideband_ports]
            sideband_names.extend([NoIndent((None, pp[0])) for pp in sbm_umap])
            debug_portmap_o = [
                ('req_mapped', req_mapped_names),
                ('opt_mapped', opt_mapped_names),
                ('user_sideband', sideband_names),
                ('unmapped', []),
            ]
            o = {
                'name': interface.prefix.strip('_'),
                'interfaceMode': bm.bus_def.driver_type,
                'busType': bm.bus_def.bus_type,
                'abstractionTypes': [{
                    'viewRef': 'RTLview',
                    'portMaps': portmap_o if not debug else debug_portmap_o,
                }], 
            }
            pg_busints.append((busint_name, o))

        assert len(pg_busints) > 0
        busint_objs.extend([o for name, o in pg_busints])
        busint_refs.append(ref_from_name(pg_busints[0][0]))
        busint_alt_refs.extend(
            [ref_from_name(name) for name, o in pg_busints[1:]]
        )
        busint_obj_map.update({name:o for name, o in pg_busints})

        pgo = (
            'portgroup_{}'.format(i), 
            # show cost of best bus mapping
            [NoIndent(e) for e in get_cost_obj(interface, bus_mappings[0])],
            #[NoIndent(json_format(p)) for p in sorted(interface.ports)],
        )
        portgroup_objs.append(pgo)
        
    # update input block object with mapped bus interfaces and alternates
    with open(component_json5) as fin:
        block_obj = json5.load(fin)
    dkey = 'definitions'
    if dkey not in block_obj:
        block_obj[dkey] = {}
    
    # bump counter for the case portinf is run again
    block_obj[dkey]['pg_cnt'] = pg_cnt_base + len(i_bus_mappings)

    bdkey = 'busDefinitions'
    if bdkey not in block_obj[dkey]:
        block_obj[dkey][bdkey] = {}
    block_obj[dkey][bdkey].update(busint_obj_map)

    bmkey = 'busMappedPortGroups'
    if bmkey not in block_obj[dkey]:
        block_obj[dkey][bmkey] = []
    block_obj[dkey][bmkey].extend(portgroup_objs)
    assert 'component' in block_obj, \
        'component key not defined in input block object'
    comp_obj = block_obj['component']

    bkey = 'busInterfaces' 
    refs = [] if bkey not in comp_obj else comp_obj[bkey]
    refs.extend(busint_refs)
    comp_obj[bkey] = [NoIndent(o) for o in refs]

    abkey = 'busInterfaceAlts' 
    refs = [] if abkey not in comp_obj else comp_obj[abkey] 
    refs.extend(busint_alt_refs)
    comp_obj[abkey] = [NoIndent(o) for o in refs]
    
    if debug:
        block_obj = [
            ('portGroups', portgroup_objs),
            ('busInterfaces', busint_refs),
            ('busDefinitions', busint_objs),
        ]
    s = json.dumps(block_obj, indent=4, cls=PrettyPrintEncoder)

    if hasattr(output, 'write'):
        _ = output.write(s)
    else:
        with open(output, 'w') as fout:
            fout.write(s)
    return

def dump_json_bundles(
    output,
    component_json5,
    bundles,
    debug=False,
):

    def ref_from_name(name):
        return {'$ref': '#/definitions/bundleDefinitions/{}'.format(name)}
    
    bundle_objs = []
    bundle_refs = []
    bundle_obj_map = {}
    bnames = set()
    for i, bundle in enumerate(bundles): 
        refname = 'bundle-{}'.format(bundle.name)
        o = {
            'name': bundle.name,
            'interfaceMode': None,
            'busType': 'bundle',
            'abstractionTypes': [{
                'viewRef': 'RTLview',
                'portMaps': bundle.tree,
            }], 
        }
        bundle_objs.append(o)
        bundle_refs.append(ref_from_name(refname))
        bundle_obj_map[refname] = o
        # bundle names must be unique
        assert bundle.name not in bnames
        bnames.add(bundle.name)

    # update input block object with mapped bus interfaces and alternates
    with open(component_json5) as fin:
        block_obj = json5.load(fin)
    assert 'definitions' in block_obj, \
        'component key not defined in input block object'
    block_obj['definitions']['bundleDefinitions'] = bundle_obj_map
    assert 'component' in block_obj, \
        'component key not defined in input block object'
    comp_obj = block_obj['component']
    bkey = 'busInterfaces' 
    if bkey not in comp_obj:
        comp_obj[bkey] = []
    refs = comp_obj[bkey]
    refs.extend(bundle_refs)
    comp_obj[bkey] = [NoIndent(r) for r in refs]
    abkey = 'busInterfaceAlts' 
    if abkey in comp_obj:
        comp_obj[abkey] = [NoIndent(o) for o in comp_obj[abkey]]

    s = json.dumps(block_obj, indent=4, cls=PrettyPrintEncoder)

    if hasattr(output, 'write'):
        _ = output.write(s)
    else:
        with open(output, 'w') as fout:
            fout.write(s)
    return

