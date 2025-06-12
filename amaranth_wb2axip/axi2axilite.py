#

from amaranth import Instance, ClockSignal, ResetSignal, Module
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from .axibus import AXI4, AXI4Lite
from .utils import add_verilog_files


class AXI2AXILite(wiring.Component):
    DEPENDENCIES = ['axi2axilsub.v', 'axi2axilite.v', 'skidbuffer.v',
                    'axi_addr.v', 'sfifo.v']

    def __init__(self, data_width, addr_width, id_width, domain='sync', *,
                 ldata_width=None, writes=True, reads=True, lowpower=False, lgfifo=4):
        self.data_width = data_width
        self.ldata_width = data_width if ldata_width is None else ldata_width
        assert self.ldata_width <= self.data_width
        self.addr_width = addr_width
        self.id_width = id_width
        self.domain = domain
        self.writes = writes
        self.reads = reads
        self.lowpower = lowpower
        self.lgfifo = lgfifo
        super().__init__({
            'axilite': Out(AXI4Lite(self.ldata_width, addr_width)),
            'axi': In(AXI4(data_width, addr_width, id_width)),
        })

    def elaborate(self, platform):
        m = Module()
        if self.ldata_width == self.data_width:
            m.submodules.axi2axil_i = Instance(
                'axi2axilite',
                p_C_AXI_ID_WIDTH=self.id_width,
                p_C_AXI_DATA_WIDTH=self.data_width,
                p_C_AXI_ADDR_WIDTH=self.addr_width,
                p_OPT_WRITES=self.writes,
                p_OPT_READS=self.reads,
                p_OPT_LOWPOWER=self.lowpower,
                p_LGFIFO=self.lgfifo,
                i_S_AXI_ACLK=ClockSignal(self.domain),
                i_S_AXI_ARESETN=~ResetSignal(self.domain),
                **self.axi.get_ports_for_instance(prefix='S_AXI_'),
                **self.axilite.get_ports_for_instance(prefix='M_AXI_'),
            )
        else:
            m.submodules.axi2axilsub_i = Instance(
                'axi2axilsub',
                p_C_AXI_ID_WIDTH=self.id_width,
                p_C_S_AXI_DATA_WIDTH=self.data_width,
                p_C_M_AXI_DATA_WIDTH=self.ldata_width,
                p_C_AXI_ADDR_WIDTH=self.addr_width,
                p_OPT_WRITES=self.writes,
                p_OPT_READS=self.reads,
                p_OPT_LOWPOWER=self.lowpower,
                p_LGFIFO=self.lgfifo,
                i_S_AXI_ACLK=ClockSignal(self.domain),
                i_S_AXI_ARESETN=~ResetSignal(self.domain),
                **self.axi.get_ports_for_instance(prefix='S_AXI_'),
                **self.axilite.get_ports_for_instance(prefix='M_AXI_'),
            )
        add_verilog_files(platform, self.DEPENDENCIES)
        return m


if __name__ == '__main__':
    from amaranth.cli import main
    core = AXI2AXILite(32, 8, 5)
    main(core, None, ports=core.axi.all_ports + core.axilite.all_ports)
