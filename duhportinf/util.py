from itertools import chain
from _ctypes import PyObj_FromPtr
import json
import re

def words_from_name(name):
    # convert camelcase to '_'
    name = re.sub('(.)([A-Z][a-z]+)(.)', r'\1_\2\3', name)
    # always return lower case so case insensitive
    name = re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()
    ## insert '_' in between names and numbers
    #name = re.sub('([a-zA-Z])([0-9])', r'\1_\2', name).lower()
    words = name.split('_')
    return words

def flatten(l): 
    return [e for ll in l for e in ll]

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
    return fraction of tokens in n1 present in the tokens of n2
    """
    n1t = set(get_tokens(n1))
    n2t = set(get_tokens(n2))
    return len(n1t - n2t)

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

def dump_json_bus_candidates(output, pg_bus_mappings, debug=False):

    def json_format(p):
        return (p[0], None if p[1] == None else int(p[1]), int(p[2]))
    
    portgroup_objs = []
    busint_objs = []
    busint_obj_map = {}
    busint_refs = []
    for i, (port_group, bus_mappings) in enumerate(sorted(
        pg_bus_mappings,
        key=lambda x: len(x[0]),
        reverse=True,
        #key=lambda x: x[1][0][0],
    )):
        for j, bus_mapping in enumerate(bus_mappings):
            bm = bus_mapping
            busint_name = 'busint-portgroup_{}-{}-{}-{}'.format(
                i,
                j,
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
            portmap_o.update({bp[0]:pp[0] for pp, bp in mapped_sideband_ports})
            if len(sbm_umap) > 0:
                portmap_o['__UMAP__'] = [p[0] for p in sbm_umap]

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
                'name': busint_name,
                'interfaceMode': bm.bus_def.driver_type,
                'busType': bm.bus_def.abstract_type,
                'abstractionTypes': [{
                    'viewRef': 'RTLview',
                    'portMaps': portmap_o if not debug else debug_port_map_o,
                }], 
            }
            busint_objs.append(o)
            busint_obj_map[busint_name] = o
            busint_refs.append(
                NoIndent({'$ref': '#/busDefinitions/{}'.format(busint_name)})
            )
        
        pgo = ('portgroup_{}'.format(i), [NoIndent(json_format(p)) for p in sorted(port_group)])
        portgroup_objs.append(pgo)
        
    o = {
        'busDefinitions' : busint_obj_map,
        'busInterfaces' : busint_refs,
    }
    if debug:
        o = [
            ('portGroups', portgroup_objs),
            ('busInterfaces', busint_refs),
            ('busDefinitions', busint_objs),
        ]
    s = json.dumps(o, indent=4, cls=PrettyPrintEncoder)

    if hasattr(output, 'write'):
        _ = output.write(s)
    else:
        with open(output, 'w') as fout:
            fout.write(s)
    return

