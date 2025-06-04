#

from math import ceil, log2

from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from .axibus import AXI4
from .utils import add_verilog_file

def length_to_mask(length, width):
    return (~int('1' * ceil(log2(length)), 2)) &  int('1' * width, 2)

class AXIXBar(Elaboratable):
    DEPENDENCIES = ['axixbar.v', 'addrdecode.v', 'skidbuffer.v']

    def __init__(self, data_width, addr_width, id_width, domain='sync'):
        self.domain = domain
        self.data_width = data_width
        self.addr_width = addr_width
        self.id_width = id_width
        self.master_sig = AXI4(data_width, addr_width, id_width)
        self.slave_sig = self.master_sig.flip()
        self.slaves = []
        self.masters = []

    def add_slave(self, slave, addr, length):
        assert self.slave_sig.is_compliant(slave)
        self.slaves.append((slave, addr, length))

    def add_master(self, master):
        assert self.master_sig.is_compliant(master)
        self.masters.append(master)

    def get_instance_ports(self):
        ports = [self.master_sig.get_port_for_instance(wiring.flipped(slave),
                                                       prefix='M_AXI_')
                 for slave, a, l in self.slaves]
        slave_ports = {k: Cat([s[k] for s in ports]) for k in ports[0].keys()}

        ports = [self.slave_sig.get_port_for_instance(wiring.flipped(master),
                                                      prefix='S_AXI_')
                 for master in self.masters]
        master_ports = {k: Cat([s[k] for s in ports]) for k in ports[0].keys()}
        return {**slave_ports, **master_ports}

    def cat_addresses(self, addresses):
        fmt = '{{:0{}b}}'.format(self.addr_width)
        return int(''.join([fmt.format(a) for a in addresses[::-1]]), 2)

    def elaborate(self, platform):
        m = Module()

        ns = len(self.slaves)
        nm = len(self.masters)

        addresses = [a for s, a, l in self.slaves]
        masks = [length_to_mask(l, self.addr_width) for s, a, l in self.slaves]

        m.submodules.axilxbar_i = Instance(
            'axixbar',
            p_C_AXI_DATA_WIDTH = self.data_width,
            p_C_AXI_ADDR_WIDTH = self.addr_width,
            p_C_AXI_ID_WIDTH = self.id_width,
            p_NM = nm,
            p_NS = ns,
            p_SLAVE_ADDR = Const(self.cat_addresses(addresses), ns * self.addr_width),
            p_SLAVE_MASK = Const(self.cat_addresses(masks), ns * self.addr_width),
            p_OPT_LOWPOWER = 1,
            p_OPT_LINGER = 4,
            p_LGMAXBURST = 5,
            i_S_AXI_ACLK = ClockSignal(self.domain),
            i_S_AXI_ARESETN = ~ResetSignal(self.domain),
            **self.get_instance_ports(),
        )

        if platform is not None:
            for d in self.DEPENDENCIES:
                add_verilog_file(platform, d)

        return m

if __name__ == '__main__':
    from amaranth.cli import main

    xbar = AXIXBar(32, 16, 3)
    slave1 = xbar.slave_sig.create()
    slave2 = xbar.slave_sig.create()
    master1 = xbar.master_sig.create()
    master2 = xbar.master_sig.create()
    xbar.add_slave(slave1, 0x8000, 0x1000)
    xbar.add_slave(slave2, 0x9000, 0x1000)
    xbar.add_master(master1)
    xbar.add_master(master2)

    ports = [signal for path, _, signal in xbar.slave_sig.flatten(slave1)]
    ports += [signal for path, _, signal in xbar.slave_sig.flatten(slave2)]
    ports += [signal for path, _, signal in xbar.master_sig.flatten(master1)]
    ports += [signal for path, _, signal in xbar.master_sig.flatten(master2)]
    main(xbar, None, ports=(slave1.all_ports + slave2.all_ports +
                            master1.all_ports + master2.all_ports))
