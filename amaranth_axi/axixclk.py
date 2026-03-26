#

from amaranth import Instance, ClockSignal, ResetSignal, Module
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from .axibus import AXI4
from .utils import add_verilog_files


class AXIXClk(wiring.Component):
    DEPENDENCIES = ['axixclk.v', 'afifo.v', 'skidbuffer.v']

    def __init__(self, data_width, addr_width, id_width, sdomain, mdomain, *,
                 write_only=False, read_only=False, xclock_ffs=2, lgfifo=5):
        self.data_width = data_width
        self.addr_width = addr_width
        self.id_width = id_width
        self.sdomain = sdomain
        self.mdomain = mdomain
        self.write_only = write_only
        self.read_only = read_only
        self.xclock_ffs = xclock_ffs
        self.lgfifo = lgfifo
        super().__init__({
            'saxi': In(AXI4(data_width, addr_width, id_width)),
            'maxi': Out(AXI4(data_width, addr_width, id_width)),
        })

    def elaborate(self, platform):
        m = Module()
        m.submodules.axixclk_i = Instance(
            'axixclk',
            p_C_S_AXI_ID_WIDTH=self.id_width,
            p_C_S_AXI_DATA_WIDTH=self.data_width,
            p_C_S_AXI_ADDR_WIDTH=self.addr_width,
            p_OPT_WRITE_ONLY=self.write_only,
            p_OPT_READ_ONLY=self.read_only,
            p_XCLOCK_FFS=self.xclock_ffs,
            p_LGFIFO=self.lgfifo,
            i_S_AXI_ACLK=ClockSignal(self.sdomain),
            i_S_AXI_ARESETN=~ResetSignal(self.sdomain),
            i_M_AXI_ACLK=ClockSignal(self.mdomain),
            i_M_AXI_ARESETN=~ResetSignal(self.mdomain),
            **self.saxi.get_ports_for_instance(prefix='S_AXI_'),
            **self.maxi.get_ports_for_instance(prefix='M_AXI_'),
        )
        add_verilog_files(platform, self.DEPENDENCIES)
        return m


if __name__ == '__main__':
    from amaranth.cli import main
    core = AXIXClk(32, 8, 5, "sync1", "sync2")
    main(core, None, ports=core.saxi.all_ports + core.maxi.all_ports)
