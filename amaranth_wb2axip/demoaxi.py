#

from amaranth import Instance, ClockSignal, ResetSignal, Module
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from .axibus import AXI4Lite
from .utils import add_verilog_files


class DemoAXI(wiring.Component):
    DEPENDENCIES = ['demoaxi.v']

    def __init__(self, data_width, addr_width, domain='sync', *,
                 read_sideeffect=True):
        self.data_width = data_width
        self.addr_width = addr_width
        self.read_sideeffect = read_sideeffect
        self.domain = domain
        super().__init__({
            'axilite': In(AXI4Lite(data_width, addr_width)),
        })

    def elaborate(self, platform):
        m = Module()
        m.submodules.demoaxi_i = Instance(
            'demoaxi',
            p_C_S_AXI_DATA_WIDTH=self.data_width,
            p_C_S_AXI_ADDR_WIDTH=self.addr_width,
            p_OPT_READ_SIDEEFFECTS=self.read_sideeffect,
            i_S_AXI_ACLK=ClockSignal(self.domain),
            i_S_AXI_ARESETN=~ResetSignal(self.domain),
            **self.axilite.get_ports_for_instance(prefix='S_AXI_'),
        )
        add_verilog_files(platform, self.DEPENDENCIES)
        return m


if __name__ == '__main__':
    from amaranth.cli import main
    core = DemoAXI(32, 8)
    main(core, None, ports=core.axilite.all_ports)
