#

from amaranth import *
from amaranth.utils import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from transactron import TModule, Transaction

from .axibus import AXI4Lite
from .axitools import axi_write_reg, AXILSlaveReadIFace, AXILSlaveWriteIFace


class DemoAXI(wiring.Component):
    def __init__(self, data_width, addr_width, domain='sync', *,
                 read_sideeffect=True, buffered=False):
        self.data_width = data_width
        self.addr_width = addr_width
        self.read_sideeffect = read_sideeffect
        self.buffered = buffered
        self.domain = domain
        super().__init__({
            'axilite': In(AXI4Lite(data_width, addr_width)),
        })

    def elaborate(self, platform):
        m = TModule()

        idx_len = 6
        addr_shift = ceil_log2(self.data_width // 8)
        def addr2idx(addr):
            return (addr >> addr_shift)[:idx_len]

        axil = self.axilite
        mem = Array([Signal(self.data_width) for _ in range(1 << idx_len)])

        m.submodules.r_iface = r_iface = AXILSlaveReadIFace(axil, domain=self.domain,
                                                            buffered=self.buffered)
        m.submodules.w_iface = w_iface = AXILSlaveWriteIFace(axil, domain=self.domain,
                                                             buffered=self.buffered)

        with Transaction().body(m):
            req = w_iface.get(m)
            idx = addr2idx(req.addr)
            data = req.data
            strb = req.strb
            axi_write_reg(m, mem[idx], data, strb, domain=self.domain)
            w_iface.done(m)

        with Transaction().body(m):
            req = r_iface.get(m)
            idx = addr2idx(req.addr)
            r_iface.done(m, mem[idx])

        return m

if __name__ == '__main__':
    from amaranth.cli import main
    from transactron import TransactronContextComponent
    core = TransactronContextComponent(DemoAXI(32, 8))
    main(core, None, ports=core.axilite.all_ports)
