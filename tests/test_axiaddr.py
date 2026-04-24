#

from amaranth import *
from amaranth.lib.wiring import Component, In, Out
from amaranth.sim import Simulator

from amaranth_axi.axiaddr import axi_next_addr, AXIAddr

from .utils import synth

import pytest
import random

def test_synth_axiaddr():
    m = AXIAddr(addr_width=15, data_width=32, len_width=4, do_realign=True)
    synth(m, ports=[m.last_addr, m.size, m.burst, m.len, m.next_addr])

@pytest.mark.parametrize("addr_width", [2, 3, 4, 6, 8, 10, 12, 14, 16])
@pytest.mark.parametrize("data_width", [8, 16, 32, 64, 128, 256, 512, 1024])
@pytest.mark.parametrize("len_width", [4, 8])
@pytest.mark.parametrize("do_realign", [False, True])
def test_axiaddr(addr_width, data_width, len_width, do_realign):
    m = AXIAddr(addr_width=addr_width, data_width=data_width,
                len_width=len_width, do_realign=do_realign)

    cycles = 100

    async def f(ctx):
        # Fixed
        ctx.set(m.burst, 0)
        for lsz in range(8):
            nbytes = 1 << lsz
            nbits = nbytes * 8
            if nbits > data_width:
                break
            ctx.set(m.size, lsz)
            for _ in range(cycles):
                addr = random.randint(0, (1 << addr_width) - 1)
                l = random.randint(0, (1 << len_width) - 1)
                ctx.set(m.len, l)
                ctx.set(m.last_addr, addr)
                assert ctx.get(m.next_addr) == addr

        # Inc
        ctx.set(m.burst, 1)
        for lsz in range(8):
            nbytes = 1 << lsz
            nbits = nbytes * 8
            if nbits > data_width:
                break
            ctx.set(m.size, lsz)
            for _ in range(cycles):
                while True:
                    addr = random.randint(0, (1 << addr_width) - 1)
                    if (addr + nbytes) // 4096 == addr // 4096:
                        break
                l = random.randint(0, (1 << len_width) - 1)
                ctx.set(m.len, l)
                ctx.set(m.last_addr, addr)
                addr_mask = ~(nbytes - 1) & ((1 << addr_width) - 1)
                if do_realign:
                    assert ctx.get(m.next_addr) == (addr + nbytes) & addr_mask
                else:
                    assert ctx.get(m.next_addr) & addr_mask == (addr + nbytes) & addr_mask

        # Wrap
        ctx.set(m.burst, 2)
        for lsz in range(8):
            nbytes = 1 << lsz
            nbits = nbytes * 8
            if nbits > data_width:
                break
            ctx.set(m.size, lsz)
            for l in (1, 3, 7, 15):
                ctx.set(m.len, l)
                group_size = (l + 1) * nbytes
                group_mask = group_size - 1
                for _ in range(cycles):
                    addr = random.randint(0, (1 << addr_width) - 1)
                    ctx.set(m.last_addr, addr)
                    next_addr = ((addr + nbytes) & group_mask) | (addr & ~group_mask)
                    addr_mask = ~(nbytes - 1) & ((1 << addr_width) - 1)
                    if do_realign:
                        assert ctx.get(m.next_addr) == next_addr & addr_mask
                    else:
                        assert ctx.get(m.next_addr) & addr_mask == next_addr & addr_mask

    sim = Simulator(m)
    sim.add_testbench(f)
    sim.run()
