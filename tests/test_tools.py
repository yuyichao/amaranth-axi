#

from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from transactron import TModule, Method, def_method
from transactron.testing import TestCaseWithSimulator, SimpleTestCircuit

from amaranth_axi.axitools import axi_write_reg

class AXIRegister(wiring.Component):
    def __init__(self):
        self.set = Method(i=[('data', 32), ('strb', 4)])
        super().__init__(dict(R=Out(32)))

    def elaborate(self, plat):
        m = TModule()

        @def_method(m, self.set)
        def _(data, strb):
            axi_write_reg(m, self.R, data, strb)

        return m

class TestAXIWriteReg(TestCaseWithSimulator):
    def test_write_reg(self):
        reg = AXIRegister()
        circ = SimpleTestCircuit(reg)

        async def setreg(sim):
            assert sim.get(reg.R) == 0

            await circ.set.call(sim, data=0xffff_ffff, strb=0b0001)
            await sim.tick()
            assert sim.get(reg.R) == 0x0000_00ff

            await circ.set.call(sim, data=0xffff_ffff, strb=0b0010)
            await sim.tick()
            assert sim.get(reg.R) == 0x0000_ffff

            await circ.set.call(sim, data=0xffff_ffff, strb=0b0100)
            await sim.tick()
            assert sim.get(reg.R) == 0x00ff_ffff

            await circ.set.call(sim, data=0xffff_ffff, strb=0b1000)
            await sim.tick()
            assert sim.get(reg.R) == 0xffff_ffff

            await circ.set.call(sim, data=0, strb=0b1000)
            await sim.tick()
            assert sim.get(reg.R) == 0x00ff_ffff

            await circ.set.call(sim, data=0, strb=0b0100)
            await sim.tick()
            assert sim.get(reg.R) == 0x0000_ffff

            await circ.set.call(sim, data=0, strb=0b0010)
            await sim.tick()
            assert sim.get(reg.R) == 0x0000_00ff

            await circ.set.call(sim, data=0, strb=0b0001)
            await sim.tick()
            assert sim.get(reg.R) == 0x0000_0000

        with self.run_simulation(circ) as sim:
            sim.add_testbench(setreg)
