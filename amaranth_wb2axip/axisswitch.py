#

from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from .axibus import AXI4Lite, AXI4Stream
from .utils import add_verilog_files


class AXISSwitch(wiring.Component):
    DEPENDENCIES = ['axisswitch.v', 'skidbuffer.v']

    def __init__(self, data_width, addr_width, domain='sync', *, lowpower=False):
        self.data_width = data_width
        self.addr_width = addr_width
        self.lowpower = lowpower
        self.domain = domain
        self.master_sig = AXI4Stream(data_width)
        self.slave_sig = self.master_sig.flip()
        self.masters = []
        super().__init__({
            'axilite': In(AXI4Lite(32, addr_width)),
            'axis': Out(self.master_sig),
        })

    def add_master(self, master):
        assert self.master_sig.is_compliant(master)
        self.masters.append(master)

    def elaborate(self, platform):
        m = Module()
        ports = [self.slave_sig.get_port_for_instance(wiring.flipped(master),
                                                      prefix='S_AXIS_')
                 for master in self.masters]
        slave_ports = {k: Cat([s[k] for s in ports]) for k in ports[0].keys()}
        m.submodules.axisswitch_i = Instance(
            'axisswitch',
            p_C_AXIS_DATA_WIDTH=self.data_width,
            p_C_AXI_ADDR_WIDTH=self.addr_width,
            p_OPT_LOWPOWER=self.lowpower,
            p_NUM_STREAMS=len(self.masters),
            i_S_AXI_ACLK=ClockSignal(self.domain),
            i_S_AXI_ARESETN=~ResetSignal(self.domain),
            **self.axilite.get_ports_for_instance(prefix='S_AXI_'),
            **self.axis.get_ports_for_instance(prefix='M_AXIS_'),
            **slave_ports,
        )
        add_verilog_files(platform, self.DEPENDENCIES)
        return m


if __name__ == '__main__':
    from amaranth.cli import main
    core = AXISSwitch(32, 8)
    master1 = core.master_sig.create()
    master2 = core.master_sig.create()
    core.add_master(master1)
    core.add_master(master2)
    ports = [signal for path, _, signal in core.axilite.signature.flatten(core.axilite)]
    ports += [signal for path, _, signal in core.axis.signature.flatten(core.axis)]
    ports += [signal for path, _, signal in core.master_sig.flatten(master1)]
    ports += [signal for path, _, signal in core.master_sig.flatten(master2)]
    main(core, None, ports=ports)
