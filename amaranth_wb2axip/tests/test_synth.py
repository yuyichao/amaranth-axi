from amaranth import Module
from amaranth_wb2axip.demoaxi import DemoAXI
from amaranth_wb2axip.axi2axilite import AXI2AXILite
from amaranth_wb2axip.axilxbar import AXILiteXBar
from amaranth_wb2axip.axibus import *
from .utils import synth


def test_synth_demo():
    demo = DemoAXI(32, 16)
    synth(demo, ports=demo.axilite.all_ports)


def test_synth_axi2axilite():
    axi2axil = AXI2AXILite(32, 16, 5)
    synth(axi2axil, ports=axi2axil.axilite.all_ports + axi2axil.axi.all_ports)


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
