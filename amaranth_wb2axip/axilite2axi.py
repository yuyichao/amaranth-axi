#

from amaranth import Instance, ClockSignal, ResetSignal, Module
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from .axibus import AXI4, AXI4Lite
from .utils import add_verilog_files


class AXILite2AXI(wiring.Component):
    DEPENDENCIES = ['axilite2axi.v']

    def __init__(self, data_width, addr_width, id_width, domain='sync', *,
                 write_id=0, read_id=0):
        self.data_width = data_width
        self.addr_width = addr_width
        self.id_width = id_width
        self.domain = domain
        self.write_id = write_id
        self.read_id = read_id
        super().__init__({
            'axilite': In(AXI4Lite(self.data_width, addr_width)),
            'axi': Out(AXI4(data_width, addr_width, id_width)),
        })

    def elaborate(self, platform):
        m = Module()
        m.submodules.axil2axi_i = Instance(
            'axilite2axi',
            p_C_AXI_ID_WIDTH=self.id_width,
            p_C_AXI_DATA_WIDTH=self.data_width,
            p_C_AXI_ADDR_WIDTH=self.addr_width,
            p_C_AXI_WRITE_D=self.write_id,
            p_C_AXI_READ_D=self.read_id,
            i_ACLK=ClockSignal(self.domain),
            i_ARESETN=~ResetSignal(self.domain),
            **self.axi.get_ports_for_instance(prefix='S_AXI_'),
            **self.axilite.get_ports_for_instance(prefix='M_AXI_'),
        )
        add_verilog_files(platform, self.DEPENDENCIES)
        return m


if __name__ == '__main__':
    from amaranth.cli import main
    core = AXILite2AXI(32, 8, 5)
    main(core, None, ports=core.axi.all_ports + core.axilite.all_ports)
