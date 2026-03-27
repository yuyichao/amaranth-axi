#

from amaranth import *

def axi_write_reg(m, reg, data, strb, *, domain='sync'):
    width = len(data)
    for i in range(width//8):
        with m.If(strb[i]):
            m.d[domain] += reg[i * 8:i * 8 + 8].eq(data[i * 8:i * 8 + 8])
