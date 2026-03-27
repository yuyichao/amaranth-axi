#

from amaranth import *
from amaranth.utils import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from .axibus import AXI4Lite
from .axitools import axi_write_reg


class DemoAXI(wiring.Component):
    def __init__(self, data_width, addr_width, domain='sync', *,
                 read_sideeffect=True):
        self.data_width = data_width
        self.addr_width = addr_width
        self.read_sideeffect = read_sideeffect
        self.domain = domain
        super().__init__({
            'axilite': In(AXI4Lite(data_width, addr_width)),
        })

    def latch_signal(self, m, val, ready):
        cache = Signal(val.shape())
        with m.If(ready):
            m.d[self.domain] += cache.eq(val)
        return Mux(ready, val, cache)

    def elaborate(self, platform):
        m = Module()

        idx_len = 6
        addr_shift = ceil_log2(self.data_width // 8)
        def addr2idx(addr):
            return (addr >> addr_shift)[:idx_len]

        axil = self.axilite
        mem = Array([Signal(self.data_width) for _ in range(1 << idx_len)])

        awready = Signal(init=1)
        wready = Signal(init=1)
        arready = Signal(init=1)
        m.d.comb += [axil.AWREADY.eq(awready),
                     axil.WREADY.eq(wready),
                     axil.ARREADY.eq(arready),
                     axil.BRESP.eq(0),
                     axil.RRESP.eq(0)]

        # Read
        valid_read_request = axil.ARVALID | ~axil.ARREADY
        read_response_stall = axil.RVALID  & ~axil.RREADY
        rd_idx = addr2idx(self.latch_signal(m, axil.ARADDR, arready))

        m.d[self.domain] += axil.RVALID.eq(read_response_stall | valid_read_request)
        with m.If(~read_response_stall & ((not self.read_sideeffect) |
                                          valid_read_request)):
            m.d[self.domain] += axil.RDATA.eq(mem[rd_idx])
        m.d[self.domain] += arready.eq(~read_response_stall | ~valid_read_request)

        # Write
        valid_write_address = axil.AWVALID | ~awready
        valid_write_data = axil.WVALID  | ~wready
        write_response_stall = axil.BVALID  & ~axil.BREADY
        wr_idx = addr2idx(self.latch_signal(m, axil.AWADDR, awready))
        wr_data = self.latch_signal(m, axil.WDATA, wready)
        wr_strb = self.latch_signal(m, axil.WSTRB, wready)

        with m.If(write_response_stall):
            m.d[self.domain] += [awready.eq(~valid_write_address),
                                 wready.eq(~valid_write_data)]
        with m.Else():
            m.d[self.domain] += [awready.eq(valid_write_data | ~valid_write_address),
                                 wready.eq(valid_write_address | ~valid_write_data)]

        with m.If(~write_response_stall & valid_write_address & valid_write_data):
            axi_write_reg(m, mem[wr_idx], wr_data, wr_strb, domain=self.domain)

        with m.If(valid_write_address & valid_write_data):
            m.d[self.domain] += axil.BVALID.eq(1)
        with m.Elif(axil.BREADY):
            m.d[self.domain] += axil.BVALID.eq(0)

        return m

if __name__ == '__main__':
    from amaranth.cli import main
    core = DemoAXI(32, 8)
    main(core, None, ports=core.axilite.all_ports)
