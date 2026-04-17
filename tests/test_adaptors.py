#

from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from transactron import TModule, Transaction, Method, def_method, TransactronContextComponent
from transactron.testing import TestCaseWithSimulator, SimpleTestCircuit

from amaranth_axi.adaptors import InAdaptor, OutAdaptor

from .utils import synth

import pytest
import random


class InAdaptorWrapper(wiring.Component):
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

        m.submodules.adaptor = adaptor = InAdaptor(32, buffered=self._buffered)

        m.d.comb += [self.i_ready.eq(adaptor.READY),
                     adaptor.VALID.eq(self.i_valid),
                     adaptor.DATA.eq(self.i_data)]

        with Transaction().body(m):
            status = adaptor.peek(m)
            m.d.top_comb += [self.o_valid.eq(status.VALID),
                             self.o_data.eq(status.DATA)]

        with Transaction().body(m, ready=self.o_ready):
            adaptor.input(m)

        return m


class OutAdaptorWrapper(wiring.Component):
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

        m.submodules.adaptor = adaptor = OutAdaptor(32, buffered=self._buffered)

        m.d.comb += [self.o_valid.eq(adaptor.VALID),
                     adaptor.READY.eq(self.o_ready),
                     self.o_data.eq(adaptor.DATA)]

        with Transaction().body(m):
            m.d.top_comb += self.i_ready.eq(adaptor.peek(m).READY)

        with Transaction().body(m, ready=self.i_valid):
            adaptor.output(m, self.i_data)

        return m

def test_synth_in_adaptor():
    buff = TransactronContextComponent(InAdaptorWrapper())
    synth(buff, ports=[buff.i_valid, buff.i_ready, buff.i_data,
                       buff.o_valid, buff.o_ready, buff.o_data])

def test_synth_in_adaptor2():
    buff = TransactronContextComponent(InAdaptorWrapper(True))
    synth(buff, ports=[buff.i_valid, buff.i_ready, buff.i_data,
                       buff.o_valid, buff.o_ready, buff.o_data])

def test_synth_out_adaptor():
    buff = TransactronContextComponent(OutAdaptorWrapper())
    synth(buff, ports=[buff.i_valid, buff.i_ready, buff.i_data,
                       buff.o_valid, buff.o_ready, buff.o_data])

def test_synth_out_adaptor2():
    buff = TransactronContextComponent(OutAdaptorWrapper(True))
    synth(buff, ports=[buff.i_valid, buff.i_ready, buff.i_data,
                       buff.o_valid, buff.o_ready, buff.o_data])


class InAdaptorModel:
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


class OutAdaptorModel:
    def __init__(self, buffered=False):
        self.i_ready = True
        self.i_valid = False
        self._o_ready = False
        self.o_valid = False
        self.i_data = 0
        self.buffer = []
        self.buffered = buffered

    @property
    def o_ready(self):
        return self._o_ready

    @o_ready.setter
    def o_ready(self, o_ready):
        if not self.buffered:
            self.i_ready = (not self.buffer) or o_ready
        self._o_ready = bool(o_ready)

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
            self.o_valid = bool(self.buffer)
            self.i_ready = (not self.buffer) or self._o_ready


class TestAdaptor(TestCaseWithSimulator):
    def test_init_in(self):
        adaptor = InAdaptor(32)
        circ = SimpleTestCircuit(adaptor)

        async def init(sim):
            assert sim.get(adaptor.READY) == 1

        with self.run_simulation(circ) as sim:
            sim.add_testbench(init)

    def test_init_in_buff(self):
        adaptor = InAdaptor(32, buffered=True)
        circ = SimpleTestCircuit(adaptor)

        async def init(sim):
            assert sim.get(adaptor.READY) == 1

        with self.run_simulation(circ) as sim:
            sim.add_testbench(init)

    def test_init_out(self):
        adaptor = OutAdaptor(32)
        circ = SimpleTestCircuit(adaptor)

        async def init(sim):
            assert sim.get(adaptor.VALID) == 0

        with self.run_simulation(circ) as sim:
            sim.add_testbench(init)

    def test_init_out_buff(self):
        adaptor = OutAdaptor(32, buffered=True)
        circ = SimpleTestCircuit(adaptor)

        async def init(sim):
            assert sim.get(adaptor.VALID) == 0

        with self.run_simulation(circ) as sim:
            sim.add_testbench(init)

    @pytest.mark.parametrize("AdaptorWrapper", [InAdaptorWrapper, OutAdaptorWrapper])
    def test_full_throughput(self, AdaptorWrapper):
        buff = AdaptorWrapper()
        circ = SimpleTestCircuit(buff)

        cycles = 256

        async def full(sim):
            sim.set(buff.i_valid, 0)
            assert sim.get(buff.o_valid) == 0
            sim.set(buff.i_valid, 1)
            if AdaptorWrapper is InAdaptorWrapper:
                assert sim.get(buff.o_valid) == 1
            else:
                assert sim.get(buff.o_valid) == 0

            assert sim.get(buff.i_ready) == 1
            sim.set(buff.o_ready, 1)

            for _ in range(cycles):
                v = random.randint(0, 0xffff_ffff)
                sim.set(buff.i_data, v)
                await sim.tick()
                assert sim.get(buff.o_data) == v
                assert sim.get(buff.o_valid) == 1
                sim.set(buff.i_valid, 0)
                if AdaptorWrapper is InAdaptorWrapper:
                    assert sim.get(buff.o_valid) == 0
                else:
                    assert sim.get(buff.o_valid) == 1
                sim.set(buff.i_valid, 1)
                assert sim.get(buff.o_valid) == 1

                sim.set(buff.o_ready, 0)
                if AdaptorWrapper is OutAdaptorWrapper:
                    assert sim.get(buff.i_ready) == 0
                else:
                    assert sim.get(buff.i_ready) == 1
                sim.set(buff.o_ready, 1)
                assert sim.get(buff.i_ready) == 1

        with self.run_simulation(circ) as sim:
            sim.add_testbench(full)

    @pytest.mark.parametrize("AdaptorWrapper", [InAdaptorWrapper, OutAdaptorWrapper])
    def test_full_throughput2(self, AdaptorWrapper):
        buff = AdaptorWrapper(True)
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

    async def check_adaptor(self, sim, buff, model, cycles):
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

    @pytest.mark.parametrize("AdaptorWrapper,AdaptorModel", [(InAdaptorWrapper, InAdaptorModel),
                                                             (OutAdaptorWrapper, OutAdaptorModel)])
    def test_adaptor(self, AdaptorWrapper, AdaptorModel):
        buff = AdaptorWrapper()
        model = AdaptorModel()
        circ = SimpleTestCircuit(buff)

        async def f(sim):
            data_in, data_out = await self.check_adaptor(sim, buff, model, 256)
            if len(data_in) > len(data_out):
                assert len(data_in) == len(data_out) + 1
                data_in = data_in[:len(data_out)]
            assert data_in == data_out

        with self.run_simulation(circ) as sim:
            sim.add_testbench(f)

    # The behavior are the same for the buffered version
    @pytest.mark.parametrize("AdaptorWrapper", [InAdaptorWrapper, OutAdaptorWrapper])
    @pytest.mark.parametrize("AdaptorModel", [InAdaptorModel, OutAdaptorModel])
    def test_adaptor2(self, AdaptorWrapper, AdaptorModel):
        buff = AdaptorWrapper(True)
        model = AdaptorModel(True)
        circ = SimpleTestCircuit(buff)

        async def f(sim):
            data_in, data_out = await self.check_adaptor(sim, buff, model, 256)
            if len(data_in) > len(data_out):
                assert (len(data_in) == len(data_out) + 1 or
                        len(data_in) == len(data_out) + 2)
                data_in = data_in[:len(data_out)]
            assert data_in == data_out

        with self.run_simulation(circ) as sim:
            sim.add_testbench(f)
