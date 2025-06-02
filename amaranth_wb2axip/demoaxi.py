#

from amaranth import Instance, ClockSignal, ResetSignal, Module
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from .axibus import AXI4, AXI4Lite
from .utils import add_verilog_file


class DemoAXI(wiring.Component):
    DEPENDENCIES = ['demoaxi.v']

    def __init__(self, data_w, addr_w, domain='sync'):
        self.data_w = data_w
        self.addr_w = addr_w
        self.domain = domain
        super().__init__({
            'axilite': In(AXI4Lite(data_w, addr_w)),
        })

    def elaborate(self, platform):
        m = Module()
        m.submodules.demoaxi_i = Instance(
            'demoaxi',
            p_C_S_AXI_DATA_WIDTH=self.data_w,
            p_C_S_AXI_ADDR_WIDTH=self.addr_w,
            i_S_AXI_ACLK=ClockSignal(self.domain),
            i_S_AXI_ARESETN=~ResetSignal(self.domain),
            **self.axilite.get_ports_for_instance(prefix='S_AXI_'),
        )

        if platform is not None:
            for d in self.DEPENDENCIES:
                add_verilog_file(platform, d)
        return m


if __name__ == '__main__':
    from amaranth.cli import main
    core = DemoAXI(32, 8)
    main(core, None, ports=core.axilite.all_ports)
