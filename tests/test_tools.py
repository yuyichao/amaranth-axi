#

from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from transactron import TModule, Transaction, Method, def_method, TransactronContextComponent
from transactron.testing import TestCaseWithSimulator, SimpleTestCircuit

from amaranth_axi.axitools import axi_write_reg, ReadyBuffer

from .utils import synth

import random

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


class ReadyBufferWrapper(wiring.Component):
    i_valid: In(1)
    i_ready: Out(1)
    i_data: In(32)

    o_valid: Out(1)
    o_ready: In(1)
    o_data: Out(32)

    def elaborate(self, plat):
        m = TModule()

        m.submodules.buff = buff = ReadyBuffer(ready=self.i_ready, valid=self.i_valid,
                                               data=self.i_data)

        with Transaction().body(m):
            status = buff.peek(m)
            m.d.top_comb += [self.o_valid.eq(status.valid),
                             self.o_data.eq(status.data)]

        with Transaction().body(m, ready=self.o_ready):
            buff.get(m)

        return m

def test_synth_ready_buffer():
    buff = TransactronContextComponent(ReadyBufferWrapper())
    synth(buff, ports=[buff.i_valid, buff.i_ready, buff.i_data,
                       buff.o_valid, buff.o_ready, buff.o_data])

class TestReadyBuffer(TestCaseWithSimulator):
    def test_init(self):
        ready = Signal(1)
        valid = Signal(1)
        data = Signal(32)

        buff = ReadyBuffer(ready=ready, valid=valid, data=data)
        circ = SimpleTestCircuit(buff)

        async def init(sim):
            await sim.tick()
            assert sim.get(ready) == 1

        with self.run_simulation(circ) as sim:
            sim.add_testbench(init)

    def test_full_throughput(self):
        buff = ReadyBufferWrapper()
        circ = SimpleTestCircuit(buff)

        cycles = 256

        async def full(sim):
            sim.set(buff.i_valid, 0)
            assert sim.get(buff.o_valid) == 0
            sim.set(buff.i_valid, 1)
            assert sim.get(buff.o_valid) == 1
            sim.set(buff.o_ready, 1)

            for _ in range(cycles):
                v = random.randint(0, 0xffff_ffff)
                sim.set(buff.i_data, v)
                await sim.tick()
                assert sim.get(buff.o_data) == v
                assert sim.get(buff.o_valid) == 1
                sim.set(buff.i_valid, 0)
                assert sim.get(buff.o_valid) == 0
                sim.set(buff.i_valid, 1)
                assert sim.get(buff.o_valid) == 1

        with self.run_simulation(circ) as sim:
            sim.add_testbench(full)

    def test_buffer(self):
        buff = ReadyBufferWrapper()
        circ = SimpleTestCircuit(buff)

        cycles = 256

        async def buffer(sim):
            sim.set(buff.i_valid, 0)
            sim.set(buff.o_ready, 0)
            sim.set(buff.i_data, 0)
            assert sim.get(buff.i_ready) == 1
            assert sim.get(buff.o_ready) == 0

            i_v0 = 0
            i_r0 = 1
            i_d = 0
            o_v0 = 0
            o_r0 = 0
            o_d = 0

            data_in = []
            data_out = []

            for _ in range(cycles):
                i_v = i_v0
                if (not i_v0) or i_r0:
                    i_v = random.randint(0, 1)
                    sim.set(buff.i_valid, i_v)
                    if i_v and (not i_v0 or i_r0):
                        i_d = random.randint(0, 0xffff_ffff)
                        sim.set(buff.i_data, i_d)
                o_r = o_r0
                if (not o_r0) or o_v0:
                    o_r = random.randint(0, 1)
                    sim.set(buff.o_ready, o_r)

                in_transfer = i_v and sim.get(buff.i_ready)
                out_transfer = o_r and sim.get(buff.i_valid)

                if in_transfer:
                    data_in.append(i_d)
                if out_transfer:
                    data_out.append(sim.get(buff.o_data))

                await sim.tick()

                i_r = int(o_r or (i_r0 and not i_v))
                o_v = int(i_v or (o_v0 and not o_r0))
                assert sim.get(buff.i_valid) == i_v
                assert sim.get(buff.i_ready) == i_r
                assert sim.get(buff.o_valid) == o_v
                assert sim.get(buff.o_ready) == o_r

                if i_r0:
                    o_d = i_d
                if o_v:
                    assert sim.get(buff.o_data) == o_d

                i_v0 = i_v
                i_r0 = i_r
                o_v0 = o_v
                o_r0 = o_r

            assert len(data_in) >= len(data_out)
            if len(data_in) > len(data_out):
                assert len(data_in) == len(data_out) + 1
                data_in = data_in[:-1]
            assert data_in == data_out

        with self.run_simulation(circ) as sim:
            sim.add_testbench(buffer)
