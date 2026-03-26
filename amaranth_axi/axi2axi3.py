#

from amaranth import Instance, ClockSignal, ResetSignal, Module
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from .axibus import AXI3, AXI4
from .utils import add_verilog_files

class AXI2AXI3(wiring.Component):
    DEPENDENCIES = ['axi2axi3.v', 'skidbuffer.v', 'sfifo.v']

    def __init__(self, data_width, addr_width, id_width, domain='sync'):
        self.data_width = data_width
        self.addr_width = addr_width
        self.id_width = id_width
        self.domain = domain
        super().__init__({
            'axi3': Out(AXI3(data_width, addr_width, id_width)),
            'axi': In(AXI4(data_width, addr_width, id_width)),
        })

    def elaborate(self, platform):
        m = Module()
        m.submodules.axi2axi3_i = Instance(
            'axi2axi3',
            p_C_AXI_ID_WIDTH=self.id_width,
            p_C_AXI_DATA_WIDTH=self.data_width,
            p_C_AXI_ADDR_WIDTH=self.addr_width,
            i_S_AXI_ACLK=ClockSignal(self.domain),
            i_S_AXI_ARESETN=~ResetSignal(self.domain),
            **self.axi3.get_ports_for_instance(prefix='M_AXI_'),
            **self.axi.get_ports_for_instance(prefix='S_AXI_'),
        )
        add_verilog_files(platform, self.DEPENDENCIES)
        return m


if __name__ == '__main__':
    from amaranth.cli import main
    core = AXI2AXI3(32, 8, 5)
    main(core, None, ports=core.axi3.all_ports + core.axi.all_ports)
