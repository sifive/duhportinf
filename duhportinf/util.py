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
        print('\r', ' '*len(s), '\r', '  - done')

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

def dump_json_bus_candidates(output, pg_bus_mappings):

    def json_format(p):
        return (p[0], None if p[1] == None else int(p[1]), int(p[2]))
    
    portmap_objs = []
    portgroup_objs = []
    for i, (port_group, bus_mappings) in enumerate(sorted(
        pg_bus_mappings,
        key=lambda x: len(x[0]),
        reverse=True,
        #key=lambda x: x[1][0][0],
    )):
        bus_mapping_objs = []
        for j, bus_mapping in enumerate(bus_mappings):
            (
                cost,
                fcost,
                mapping,
                sideband_ports,
                match_cost_func,
                bus_def,
            ) = bus_mapping
            portmap_name = 'portmap_{}_{}_{}'.format(i,j, bus_def.abstract_type.name)
            o = NoIndent({
                'port_group_num': i,
                'interfaceMode': bus_def.driver_type,
                'busType': bus_def.abstract_type,
                'abstractionTypes': [{
                    'viewRef': 'RTLview',
                    'portMapRef': portmap_name,
                }], 
            })
            # for all ports in mapping, just include port names and exclude width+direction
            bm = dict(mapping)
            sbm = dict(mapping)
            for pp in sideband_ports:
                del bm[pp]
            for pp in set(mapping.keys()) - sideband_ports:
                del sbm[pp]
                
            mapped_sideband_ports = list(sorted(
                sbm.items(),
                key=lambda x: match_cost_func(x[0], x[1]),
            ))
            mapped_ports = list(sorted(
                bm.items(),
                key=lambda x: match_cost_func(x[0], x[1]),
            ))
            req_mapped_names = [NoIndent((bp[0], pp[0])) for pp, bp in mapped_ports if bp in bus_def.req_ports]
            opt_mapped_names = [NoIndent((bp[0], pp[0])) for pp, bp in mapped_ports if bp in bus_def.opt_ports]
            sideband_names =   [NoIndent((bp[0], pp[0])) for pp, bp in mapped_sideband_ports]
            # propose all unmapped names as user signals as well, but without a logical mapping
            umap_ports = list(set(port_group) - set(mapping.keys()))
            sideband_names.extend([NoIndent((None, pp[0])) for pp in umap_ports])
            pm_o = {
                'req_mapped': req_mapped_names,
                'opt_mapped': opt_mapped_names,
                'user_sideband': sideband_names,
                'unmapped': [],
            }
            bus_mapping_objs.append(o)
            portmap_objs.append((portmap_name, pm_o))
        
        pgo = {
            'port_group_num': i,
            'ports': [NoIndent(json_format(p)) for p in sorted(port_group)],
            'busInterfaces': bus_mapping_objs,
        }
        portgroup_objs.append(pgo)
        
    o = [
        ('port_groups' , portgroup_objs),
        ('port_maps' , portmap_objs),
    ]
    s = json.dumps(o, indent=4, cls=PrettyPrintEncoder)
    if hasattr(output, 'write'):
        _ = output.write(s)
    else:
        with open(output, 'w') as fout:
            fout.write(s)
    return

