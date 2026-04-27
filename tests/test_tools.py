#

from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from transactron import TModule, Transaction, Method, def_method, TransactronContextComponent
from transactron.testing import TestCaseWithSimulator, TestbenchIO as _TestbenchIO, SimpleTestCircuit
from transactron.lib.adapters import AdapterTrans

from amaranth_axi.axitools import axi_write_reg, AXILMasterWriteIFace, AXILMasterReadIFace
from amaranth_axi.demoaxi import DemoAXI

from .utils import synth

import pytest
from types import SimpleNamespace
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

class DemoAXIWrapper(Elaboratable):
    def __init__(self, in_buffered, out_buffered, align_address):
        self.demo = DemoAXI(32, 8, in_buffered=in_buffered, out_buffered=out_buffered,
                            align_address=align_address)
        self.reader = AXILMasterReadIFace(
            self.demo.axilite,
            in_buffered=in_buffered, out_buffered=out_buffered,
            align_address=align_address)
        self.writer = AXILMasterWriteIFace(
            self.demo.axilite,
            in_buffered=in_buffered, out_buffered=out_buffered,
            align_address=align_address)

        self.read_request = _TestbenchIO(AdapterTrans.create(self.reader.request))
        self.read_reply = _TestbenchIO(AdapterTrans.create(self.reader.reply))
        self.write_request = _TestbenchIO(AdapterTrans.create(self.writer._request))
        self.write_reply = _TestbenchIO(AdapterTrans.create(self.writer.reply))

    def elaborate(self, plat):
        m = TModule()

        m.submodules.demo = self.demo
        m.submodules.reader = self.reader
        m.submodules.writer = self.writer

        m.submodules.read_request = self.read_request
        m.submodules.read_reply = self.read_reply
        m.submodules.write_request = self.write_request
        m.submodules.write_reply = self.write_reply

        return m

def update_mem(mem, idx, data, strb):
    old_data = mem[idx]
    for i in range(4):
        bitmask = 1 << i
        bytemask = 0xff << (i * 8)
        if not (strb & bitmask):
            data = (data & ~bytemask) | (old_data & bytemask)
    mem[idx] = data

def gen_rand_write():
    idx = random.randint(0, 0x3f)
    addr = (idx << 2) + random.randint(0, 0x3)
    data = random.randint(0, 0xffff_ffff)
    strb = random.randint(0, 0xf)
    return idx, addr, data, strb

class TestAXILite(TestCaseWithSimulator):
    @pytest.mark.parametrize("in_buffered", [False, True])
    @pytest.mark.parametrize("out_buffered", [False, True])
    @pytest.mark.parametrize("align_address", [False, True])
    def test_full_throughput(self, in_buffered, out_buffered, align_address):
        demo = DemoAXIWrapper(in_buffered, out_buffered, align_address)

        mem = [0 for _ in range(2**6)]

        g = SimpleNamespace()
        g.written = False
        g.nwrite = 500

        async def producer(sim):
            for _ in range(g.nwrite):
                idx, addr, data, strb = gen_rand_write()
                assert (await demo.write_request.call_try(sim, addr=addr, data=data, strb=strb)) is not None
                update_mem(mem, idx, data, strb)

            while not g.written:
                await sim.tick()

            for idx in range(2**6):
                addr = (idx << 2) + random.randint(0, 0x3)
                assert (await demo.read_request.call_try(sim, addr=addr)) is not None

        async def consumer(sim):
            await demo.write_reply.call(sim)
            for _ in range(g.nwrite - 1):
                reply = await demo.write_reply.call_try(sim)
                assert reply is not None
                assert reply.resp == 0
            for _ in range(100):
                assert (await demo.write_reply.call_try(sim)) is None
            g.written = True
            data0 = (await demo.read_reply.call(sim)).data
            assert data0 == mem[0]
            for idx in range(1, 2**6):
                reply = await demo.read_reply.call_try(sim)
                assert reply is not None
                assert reply.data == mem[idx]
                assert reply.resp == 0

        with self.run_simulation(demo) as sim:
            sim.add_testbench(producer)
            sim.add_testbench(consumer)

    @pytest.mark.parametrize("in_buffered", [False, True])
    @pytest.mark.parametrize("out_buffered", [False, True])
    @pytest.mark.parametrize("align_address", [False, True])
    def test_backpressure(self, in_buffered, out_buffered, align_address):
        demo = DemoAXIWrapper(in_buffered, out_buffered, align_address)

        mem = [0 for _ in range(2**6)]

        async def do_rand_write(sim):
            idx, addr, data, strb = gen_rand_write()
            req = await demo.write_request.call_try(sim, addr=addr, data=data, strb=strb)
            if req is not None:
                update_mem(mem, idx, data, strb)
            return req

        async def write_unblocked(sim, nwrite):
            for _ in range(nwrite):
                assert (await do_rand_write(sim)) is not None

        async def write_until_blocked(sim):
            nwrite = 0
            while True:
                if (await do_rand_write(sim)) is None:
                    return nwrite
                nwrite += 1

        async def check_write_blocked(sim, n=100):
            for _ in range(n):
                assert (await do_rand_write(sim)) is None

        async def receive_write_unblocked(sim, nwrite):
            for _ in range(nwrite):
                reply = await demo.write_reply.call_try(sim)
                assert reply is not None
                assert reply.resp == 0

        async def receive_write_blocked(sim, n=100):
            for _ in range(n):
                assert (await demo.write_reply.call_try(sim)) is None

        async def do_rand_read(sim, idx):
            addr = (idx << 2) + random.randint(0, 0x3)
            return await demo.read_request.call_try(sim, addr=addr)

        async def read_unblocked(sim, start=0, end=2**6):
            for idx in range(start, end):
                assert (await do_rand_read(sim, idx)) is not None

        async def read_until_blocked(sim, start=0):
            nread = 0
            for idx in range(start, 2**6):
                req = await do_rand_read(sim, idx)
                if req is None:
                    return nread
                nread += 1
            assert False

        async def check_read_blocked(sim, n=100):
            for _ in range(n):
                assert (await do_rand_read(sim, random.randint(0, 2**6 - 1))) is None

        async def receive_read_unblocked(sim, start=0, end=2**6):
            for idx in range(start, end):
                reply = await demo.read_reply.call_try(sim)
                assert reply is not None
                assert reply.data == mem[idx]
                assert reply.resp == 0

        async def receive_read_blocked(sim, n=100):
            for _ in range(n):
                assert (await demo.read_reply.call_try(sim)) is None

        # Steps:
        # * Write until blocked
        # * Verify that the correct number is received
        # * Write more until blocked
        # * Start concurrent receiving and make sure we can write for a long time.

        # * Read until blocked
        # * Verify that the correct number is received
        # * Read more until blocked
        # * Start concurrent receiving and make sure we can read for a long time.

        g = SimpleNamespace()
        g.nwrite = 0
        g.start_receive_write = False
        g.start_receive_read = False

        async def wait_flag(sim, attr):
            while not getattr(g, attr):
                await sim.tick()
                await sim.delay(0)

        async def producer(sim):
            nwrite = await write_until_blocked(sim)
            await check_write_blocked(sim)
            await receive_write_unblocked(sim, nwrite)
            await receive_write_blocked(sim)

            nwrite = await write_until_blocked(sim)
            g.nwrite = nwrite + 500
            g.start_receive_write = True
            unblocked = False
            for _ in range(5):
                if (await do_rand_write(sim)) is not None:
                    unblocked = True
                    break
            assert unblocked
            await write_unblocked(sim, 499)

            nread = await read_until_blocked(sim)
            await check_read_blocked(sim)
            await receive_read_unblocked(sim, 0, nread)
            await receive_read_blocked(sim)

            nread = await read_until_blocked(sim)
            g.start_receive_read = True

            unblocked = False
            for _ in range(5):
                if (await do_rand_read(sim, nread)) is not None:
                    unblocked = True
                    break
            assert unblocked
            await read_unblocked(sim, nread + 1)

        async def consumer(sim):
            await wait_flag(sim, 'start_receive_write')
            await receive_write_unblocked(sim, g.nwrite)
            await receive_write_blocked(sim)

            await wait_flag(sim, 'start_receive_read')
            await receive_read_unblocked(sim)
            await receive_read_blocked(sim)

        with self.run_simulation(demo) as sim:
            sim.add_testbench(producer)
            sim.add_testbench(consumer)

    @pytest.mark.parametrize("in_buffered", [False, True])
    @pytest.mark.parametrize("out_buffered", [False, True])
    @pytest.mark.parametrize("align_address", [False, True])
    @pytest.mark.parametrize("maxwait", [2, 6])
    def test_random(self, in_buffered, out_buffered, align_address, maxwait):
        demo = DemoAXIWrapper(in_buffered, out_buffered, align_address)

        mem = [0 for _ in range(2**6)]
        write_count = [0 for _ in range(2**6)]
        nwrite = 1000
        nread = 1000
        write_req = []
        read_req = []

        async def rand_wait(sim):
            for _ in range(random.randint(0, maxwait)):
                await sim.tick()

        async def do_rand_write(sim):
            await rand_wait(sim)
            idx, addr, data, strb = gen_rand_write()
            write_req.append(idx)
            write_count[idx] += 1
            await demo.write_request.call(sim, addr=addr, data=data, strb=strb)
            update_mem(mem, idx, data, strb)

        async def do_rand_read(sim):
            await rand_wait(sim)
            idx = random.randint(0, 2**6 - 1)
            read_req.append(idx)
            addr = (idx << 2) + random.randint(0, 0x3)
            # Write reply not yet received and the write might not have gone through
            # We need to wait so that the read can see the final result
            while write_count[idx] > 0:
                await sim.tick()
            await demo.read_request.call(sim, addr=addr)

        async def receive_write(sim):
            await rand_wait(sim)
            reply = await demo.write_reply.call(sim)
            idx = write_req.pop(0)
            assert write_count[idx] >= 1
            write_count[idx] -= 1
            assert reply.resp == 0

        async def receive_write_blocked(sim, n=100):
            for _ in range(n):
                assert (await demo.write_reply.call_try(sim)) is None

        async def receive_read(sim):
            await rand_wait(sim)
            reply = await demo.read_reply.call(sim)
            assert reply.data == mem[read_req.pop(0)]
            assert reply.resp == 0

        async def receive_read_blocked(sim, n=100):
            for _ in range(n):
                assert (await demo.read_reply.call_try(sim)) is None

        async def producer(sim):
            for _ in range(nwrite):
                await do_rand_write(sim)
            for _ in range(nread):
                await do_rand_read(sim)

        async def consumer(sim):
            for _ in range(nwrite):
                await receive_write(sim)
            await receive_write_blocked(sim, 10)
            for _ in range(nread):
                await receive_read(sim)
            await receive_read_blocked(sim, 10)
            await receive_write_blocked(sim, 5)

        with self.run_simulation(demo) as sim:
            sim.add_testbench(producer)
            sim.add_testbench(consumer)
