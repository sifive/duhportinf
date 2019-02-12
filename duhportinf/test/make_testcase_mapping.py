import os
from ..busdef import BusDef

bsdir = os.path.join(
    os.path.dirname(__file__),
    'test-bus-specs',
)
spec_path = os.path.join(bsdir, 'AXI4_rtl.json5')
bus_defs.extend(BusDef.bus_defs_from_spec(spec_path))                
all_bd_portnames = set([p[0] for bd in bus_defs for p in bd.all_ports])

input_mapping = set([
    (('front_port_axi4_0_aw_ready', 1, -1), ('AWREADY', 1, -1)),
    (('front_port_axi4_0_aw_valid', 1, 1), ('AWVALID', 1, 1)),
    (('front_port_axi4_0_aw_bits_id', 8, 1), ('AWID', None, 1)),
    (('front_port_axi4_0_aw_bits_addr', 40, 1), ('AWADDR', None, 1)),
    (('front_port_axi4_0_aw_bits_len', 8, 1), ('AWLEN', 8, 1)),
    (('front_port_axi4_0_aw_bits_size', 3, 1), ('AWSIZE', 3, 1)),
    (('front_port_axi4_0_aw_bits_burst', 2, 1), ('AWBURST', 2, 1)),
    (('front_port_axi4_0_aw_bits_lock', 1, 1), ('AWLOCK', 1, 1)),
    (('front_port_axi4_0_aw_bits_cache', 4, 1), ('AWCACHE', 4, 1)),
    (('front_port_axi4_0_aw_bits_prot', 3, 1), ('AWPROT', 3, 1)),
    (('front_port_axi4_0_aw_bits_qos', 4, 1), ('AWQOS', 4, 1)),
    (('front_port_axi4_0_w_ready', 1, -1), ('WREADY', 1, -1)),
    (('front_port_axi4_0_w_valid', 1, 1), ('WVALID', 1, 1)),
    (('front_port_axi4_0_w_bits_data', 64, 1), ('WDATA', None, 1)),
    (('front_port_axi4_0_w_bits_strb', 8, 1), ('WSTRB', None, 1)),
    (('front_port_axi4_0_w_bits_last', 1, 1), ('WLAST', 1, 1)),
    (('front_port_axi4_0_b_ready', 1, 1), ('BREADY', 1, 1)),
    (('front_port_axi4_0_b_valid', 1, -1), ('BVALID', 1, -1)),
    (('front_port_axi4_0_b_bits_id', 8, -1), ('BID', None, -1)),
    (('front_port_axi4_0_b_bits_resp', 2, -1), ('BRESP', 2, -1)),
    (('front_port_axi4_0_ar_ready', 1, -1), ('ARREADY', 1, -1)),
    (('front_port_axi4_0_ar_valid', 1, 1), ('ARVALID', 1, 1)),
    (('front_port_axi4_0_ar_bits_id', 8, 1), ('ARID', None, 1)),
    (('front_port_axi4_0_ar_bits_addr', 40, 1), ('ARADDR', None, 1)),
    (('front_port_axi4_0_ar_bits_len', 8, 1), ('ARLEN', 8, 1)),
    (('front_port_axi4_0_ar_bits_size', 3, 1), ('ARSIZE', 3, 1)),
    (('front_port_axi4_0_ar_bits_burst', 2, 1), ('ARBURST', 2, 1)),
    (('front_port_axi4_0_ar_bits_lock', 1, 1), ('ARLOCK', 1, 1)),
    (('front_port_axi4_0_ar_bits_cache', 4, 1), ('ARCACHE', 4, 1)),
    (('front_port_axi4_0_ar_bits_prot', 3, 1), ('ARPROT', 3, 1)),
    (('front_port_axi4_0_ar_bits_qos', 4, 1), ('ARQOS', 4, 1)),
    (('front_port_axi4_0_r_ready', 1, 1), ('RREADY', 1, 1)),
    (('front_port_axi4_0_r_valid', 1, -1), ('RVALID', 1, -1)),
    (('front_port_axi4_0_r_bits_id', 8, -1), ('RID', None, -1)),
    (('front_port_axi4_0_r_bits_data', 64, -1), ('RDATA', None, -1)),
    (('front_port_axi4_0_r_bits_resp', 2, -1), ('RRESP', 2, -1)),
    (('front_port_axi4_0_r_bits_last', 1, -1), ('RLAST', 1, -1)),
])

filt_mapping = filter(
    lambda x: x[1][0] in all_bd_portnames,
    input_mapping,
)
for x in filt_mapping.items():
    print('{},'.format(x))
