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

    def __init__(self, buffered=False):
        self._buffered = buffered
        super().__init__()

    def elaborate(self, plat):
        m = TModule()

        m.submodules.buff = buff = ReadyBuffer(ready=self.i_ready, valid=self.i_valid,
                                               data=self.i_data, buffered=self._buffered)

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

def test_synth_ready_buffer2():
    buff = TransactronContextComponent(ReadyBufferWrapper(True))
    synth(buff, ports=[buff.i_valid, buff.i_ready, buff.i_data,
                       buff.o_valid, buff.o_ready, buff.o_data])


class ReadyBufferModel:
    def __init__(self, buffered=False):
        self.i_ready = True
        self._i_valid = False
        self.o_ready = False
        self.o_valid = False
        self.i_data = 0
        self.buffer = []
        self.buffered = buffered

    @property
    def i_valid(self):
        return self._i_valid

    @i_valid.setter
    def i_valid(self, i_valid):
        if not self.buffered:
            self.o_valid = bool(self.buffer) or i_valid
        self._i_valid = bool(i_valid)

    @property
    def i_transfer(self):
        return self.i_valid and self.i_ready

    @property
    def o_transfer(self):
        return self.o_valid and self.o_ready

    @property
    def o_data(self):
        if self.buffered:
            return self.buffer[0] if self.buffer else 0
        return self.buffer[0] if self.buffer else self.i_data

    def tick(self):
        i_transfer = self.i_transfer
        o_transfer = self.o_transfer

        if i_transfer:
            self.buffer.append(self.i_data)
        if o_transfer:
            self.buffer.pop(0)

        if self.buffered:
            self.o_valid = bool(self.buffer)
            self.i_ready = len(self.buffer) <= 1
        else:
            self.o_valid = bool(self.buffer) or self._i_valid
            self.i_ready = not self.buffer


class TestReadyBuffer(TestCaseWithSimulator):
    def test_init(self):
        ready = Signal(1)
        valid = Signal(1)
        data = Signal(32)

        buff = ReadyBuffer(ready=ready, valid=valid, data=data)
        circ = SimpleTestCircuit(buff)

        async def init(sim):
            assert sim.get(ready) == 1

        with self.run_simulation(circ) as sim:
            sim.add_testbench(init)

    def test_init2(self):
        ready = Signal(1)
        valid = Signal(1)
        data = Signal(32)

        buff = ReadyBuffer(ready=ready, valid=valid, data=data, buffered=True)
        circ = SimpleTestCircuit(buff)

        async def init(sim):
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

    def test_full_throughput2(self):
        buff = ReadyBufferWrapper(True)
        circ = SimpleTestCircuit(buff)

        cycles = 256

        async def full(sim):
            sim.set(buff.i_valid, 0)
            assert sim.get(buff.o_valid) == 0
            sim.set(buff.i_valid, 1)
            assert sim.get(buff.o_valid) == 0
            sim.set(buff.o_ready, 1)

            for _ in range(cycles):
                v = random.randint(0, 0xffff_ffff)
                sim.set(buff.i_data, v)
                await sim.tick()
                assert sim.get(buff.o_data) == v
                assert sim.get(buff.o_valid) == 1

        with self.run_simulation(circ) as sim:
            sim.add_testbench(full)

    def log_state(self, name, sim, buff, model):
        def log_line(sig, real, expected):
            real = sim.get(real)
            if real == expected:
                print(f"  {sig}: {real}")
            else:
                print(f"  {sig}: {real}(expect {int(expected)})")
        print(f"{name}:")
        log_line("i_v", buff.i_valid, model.i_valid)
        log_line("i_r", buff.i_ready, model.i_ready)
        log_line("i_d", buff.i_data, model.i_data)
        log_line("o_v", buff.o_valid, model.o_valid)
        log_line("o_r", buff.o_ready, model.o_ready)
        log_line("o_d", buff.o_data, model.o_data)

    async def check_buffer(self, sim, buff, model, cycles):
        sim.set(buff.i_valid, 0)
        model.i_valid = 0
        sim.set(buff.o_ready, 0)
        model.o_ready = 0
        sim.set(buff.i_data, 0)
        model.i_data = 0
        assert sim.get(buff.i_ready) == model.i_ready
        assert sim.get(buff.o_ready) == model.o_ready

        data_in = []
        data_out = []

        i_had_transfer = False
        o_had_transfer = False

        for _ in range(cycles):
            i_v0 = model.i_valid
            i_r0 = model.i_ready
            o_v0 = model.o_valid
            o_r0 = model.o_ready

            if (not i_v0) or i_had_transfer:
                i_v = random.randint(0, 1)
                sim.set(buff.i_valid, i_v)
                model.i_valid = i_v
                if i_v and (not i_v0 or i_had_transfer):
                    i_d = random.randint(0, 0xffff_ffff)
                    sim.set(buff.i_data, i_d)
                    model.i_data = i_d
            if (not o_r0) or o_had_transfer:
                o_r = random.randint(0, 1)
                sim.set(buff.o_ready, o_r)
                model.o_ready = o_r

            i_had_transfer = sim.get(buff.i_valid) and sim.get(buff.i_ready)
            o_had_transfer = sim.get(buff.o_valid) and sim.get(buff.o_ready)

            if i_had_transfer:
                data_in.append(sim.get(buff.i_data))
            if o_had_transfer:
                data_out.append(sim.get(buff.o_data))

            self.log_state("Pre tick", sim, buff, model)
            await sim.tick()
            model.tick()
            self.log_state("Post tick", sim, buff, model)

            assert sim.get(buff.i_valid) == model.i_valid
            assert sim.get(buff.i_ready) == model.i_ready
            assert sim.get(buff.o_valid) == model.o_valid
            assert sim.get(buff.o_ready) == model.o_ready
            if model.o_valid:
                assert sim.get(buff.o_data) == model.o_data

        assert len(data_in) >= len(data_out)
        return data_in, data_out

    def test_buffer(self):
        buff = ReadyBufferWrapper()
        model = ReadyBufferModel()
        circ = SimpleTestCircuit(buff)

        async def buffer(sim):
            data_in, data_out = await self.check_buffer(sim, buff, model, 256)
            if len(data_in) > len(data_out):
                assert len(data_in) == len(data_out) + 1
                data_in = data_in[:len(data_out)]
            assert data_in == data_out

        with self.run_simulation(circ) as sim:
            sim.add_testbench(buffer)

    def test_buffer2(self):
        buff = ReadyBufferWrapper(True)
        model = ReadyBufferModel(True)
        circ = SimpleTestCircuit(buff)

        async def buffer(sim):
            data_in, data_out = await self.check_buffer(sim, buff, model, 256)
            if len(data_in) > len(data_out):
                assert (len(data_in) == len(data_out) + 1 or
                        len(data_in) == len(data_out) + 2)
                data_in = data_in[:len(data_out)]
            assert data_in == data_out

        with self.run_simulation(circ) as sim:
            sim.add_testbench(buffer)
