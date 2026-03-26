#

from amaranth import Instance, ClockSignal, ResetSignal, Module
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from .axibus import AXI4Lite
from .utils import add_verilog_files


class AXILUpSz(wiring.Component):
    DEPENDENCIES = ['axilupsz.v', 'skidbuffer.v', 'sfifo.v']

    def __init__(self, sdata_width, mdata_width, addr_width, domain='sync', *,
                 lgfifo=5, lowpower=True):
        assert sdata_width <= mdata_width
        self.sdata_width = sdata_width
        self.mdata_width = mdata_width
        self.addr_width = addr_width
        self.domain = domain
        self.lgfifo = lgfifo
        self.lowpower = lowpower
        super().__init__({
            'maxilite': Out(AXI4Lite(self.mdata_width, addr_width)),
            'saxilite': In(AXI4Lite(self.sdata_width, addr_width)),
        })

    def elaborate(self, platform):
        m = Module()
        m.submodules.axilupsz_i = Instance(
            'axilupsz',
            p_C_S_AXIL_DATA_WIDTH=self.sdata_width,
            p_C_M_AXIL_DATA_WIDTH=self.mdata_width,
            p_C_AXIL_ADDR_WIDTH=self.addr_width,
            p_LGFIFO=self.lgfifo,
            p_OPT_LOWPOWER=self.lowpower,
            i_S_AXI_ACLK=ClockSignal(self.domain),
            i_S_AXI_ARESETN=~ResetSignal(self.domain),
            **self.maxilite.get_ports_for_instance(prefix='M_AXIL_'),
            **self.saxilite.get_ports_for_instance(prefix='S_AXIL_'),
        )
        add_verilog_files(platform, self.DEPENDENCIES)
        return m


if __name__ == '__main__':
    from amaranth.cli import main
    core = AXILUpSz(32, 64, 8)
    main(core, None, ports=core.maxilite.all_ports + core.saxilite.all_ports)
