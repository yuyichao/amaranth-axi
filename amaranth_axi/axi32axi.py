#

from amaranth import Instance, ClockSignal, ResetSignal, Module
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from .axibus import AXI3, AXI4
from .utils import add_verilog_files

_reorder_methods = dict(none=0, shift_register=1, perid_fifos=2)

class AXI32AXI(wiring.Component):
    DEPENDENCIES = ['axi32axi.v', 'skidbuffer.v', 'axi3reorder.v', 'sfifo.v']

    def __init__(self, data_width, addr_width, id_width, domain='sync', *,
                 reorder_method='none', transform_axcache=True,
                 lowpower=False, lowlatency=False, lgawfifo=3, lgwfifo=3):
        self.data_width = data_width
        self.addr_width = addr_width
        self.id_width = id_width
        self.domain = domain
        self.reorder_method = _reorder_methods[reorder_method]
        self.lowpower = lowpower
        self.lowlatency = lowlatency
        self.transform_axcache = transform_axcache
        self.lgawfifo = lgawfifo
        self.lgwfifo = lgwfifo
        super().__init__({
            'axi3': In(AXI3(data_width, addr_width, id_width)),
            'axi': Out(AXI4(data_width, addr_width, id_width)),
        })

    def elaborate(self, platform):
        m = Module()
        m.submodules.axi32axi_i = Instance(
            'axi32axi',
            p_C_AXI_ID_WIDTH=self.id_width,
            p_C_AXI_DATA_WIDTH=self.data_width,
            p_C_AXI_ADDR_WIDTH=self.addr_width,
            p_OPT_REORDER_METHOD=self.reorder_method,
            p_OPT_TRANSFORM_AXCACHE=self.transform_axcache,
            p_OPT_LOWPOWER=self.lowpower,
            p_OPT_LOW_LATENCY=self.lowlatency,
            p_WID_LGAWFIFO=self.lgawfifo,
            p_WID_LGWFIFO=self.lgwfifo,
            i_S_AXI_ACLK=ClockSignal(self.domain),
            i_S_AXI_ARESETN=~ResetSignal(self.domain),
            **self.axi3.get_ports_for_instance(prefix='S_AXI_'),
            **self.axi.get_ports_for_instance(prefix='M_AXI_'),
        )
        add_verilog_files(platform, self.DEPENDENCIES)
        return m


if __name__ == '__main__':
    from amaranth.cli import main
    core = AXI32AXI(32, 8, 5)
    main(core, None, ports=core.axi3.all_ports + core.axi.all_ports)
