from amaranth import Module
from amaranth_wb2axip import *
from .utils import synth


def test_synth_demo():
    demo = DemoAXI(32, 16)
    synth(demo, ports=demo.axilite.all_ports)


def test_synth_axi2axilite():
    axi2axil = AXI2AXILite(32, 16, 5)
    synth(axi2axil, ports=axi2axil.axilite.all_ports + axi2axil.axi.all_ports)


def test_synth_axilite2axi():
    axil2axi = AXILite2AXI(32, 16, 5)
    synth(axil2axi, ports=axil2axi.axilite.all_ports + axil2axi.axi.all_ports)


def test_synth_axi2axilsub():
    axi2axil = AXI2AXILite(64, 16, 5, ldata_width=32)
    synth(axi2axil, ports=axi2axil.axilite.all_ports + axi2axil.axi.all_ports)


def test_synth_axixclk():
    core = AXIXClk(32, 8, 5, "sync1", "sync2")
    synth(core, ports=core.saxi.all_ports + core.maxi.all_ports)


def test_synth_axilxbar():
    xbar = AXILiteXBar(32, 16)
    slaves = [xbar.slave_sig.create() for i in range(5)]
    masters = [xbar.master_sig.create() for i in range(2)]
    for i, s in enumerate(slaves):
        xbar.add_slave(s, 0x1000 * i, 0x1000)
    for m in masters:
        xbar.add_master(m)
    ports = [field for interface in slaves + masters for field in interface.all_ports]
    synth(xbar, ports)


def test_synth_axixbar():
    xbar = AXIXBar(32, 16, 3)
    slaves = [xbar.slave_sig.create() for i in range(5)]
    masters = [xbar.master_sig.create() for i in range(2)]
    for i, s in enumerate(slaves):
        xbar.add_slave(s, 0x1000 * i, 0x1000)
    for m in masters:
        xbar.add_master(m)
    ports = [field for interface in slaves + masters for field in interface.all_ports]
    synth(xbar, ports)


def test_synth_axisswitch():
    core = AXISSwitch(32, 8)
    masters = [core.master_sig.create() for i in range(4)]
    for m in masters:
        core.add_master(m)
    ports = [field for interface in masters + [core.axilite, core.axis]
             for field in interface.all_ports]
    synth(core, ports)


def test_synth_axilupsz():
    core = AXILUpSz(32, 64, 8)
    synth(core, ports=core.saxilite.all_ports + core.maxilite.all_ports)


def test_synth_axi32axi():
    core = AXI32AXI(32, 64, 8)
    synth(core, ports=core.axi3.all_ports + core.axi.all_ports)


def test_synth_axi2axi3():
    core = AXI2AXI3(32, 64, 8)
    synth(core, ports=core.axi3.all_ports + core.axi.all_ports)


def test_synth_realcase():
    m = Module()
    m.submodules.axi2axil = axi2axil = AXI2AXILite(32, 16, 5)
    m.submodules.xbar = xbar = AXILiteXBar(32, 16)
    slaves = [DemoAXI(32, 16) for _ in range(5)]
    for i, s in enumerate(slaves):
        m.submodules['slave_' + str(i)] = s
        xbar.add_slave(s.axilite, 0x1000 * i, 0x1000)
    xbar.add_master(axi2axil.axilite)
    synth(m, ports=axi2axil.axi.all_ports)
