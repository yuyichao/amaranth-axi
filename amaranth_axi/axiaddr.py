#

from amaranth import *
from amaranth.lib.wiring import Component, In, Out
from amaranth.utils import exact_log2

_pylen = len

class AXIAddr(Component):
    @classmethod
    def from_signal(cls, *, last_addr, size, burst, len, **kws):
        axiaddr = cls(addr_width=pylen(last_addr), len_width=pylen(len), **kws)
        axiaddr.last_addr = last_addr
        axiaddr.size = size
        axiaddr.burst = burst
        axiaddr.len = len
        return axiaddr

    def __init__(self, *, addr_width, data_width, len_width, do_realign=False):
        super().__init__(dict(
            last_addr=In(addr_width),
            size=In(3),
            burst=In(2),
            len=In(len_width),
            next_addr=Out(addr_width),
        ))
        self.addr_width = addr_width
        self.data_width = data_width
        self.len_width = len_width
        self.do_realign = do_realign

    def elaborate(self, plat):
        m = Module()

        maxbit = exact_log2(self.data_width) - 3

        if maxbit == 0:
            size = C(0)
            inc = C(1)
        elif maxbit == 1:
            size = self.size[0]
            inc = Mux(size, 2, 1)
        elif maxbit == 2:
            size = self.size[:2]
            inc = Mux(size[1], 4, Mux(size[0], 2, 1))
        elif maxbit == 3:
            size = self.size[:2]
            inc = 1 << size
        else:
            size = self.size
            inc = (1 << size)[:maxbit + 1]

        # Must not cross 4k boundary
        m.d.comb += self.next_addr[12:].eq(self.last_addr[12:])

        # Only need to care about the bottom 12 bits (4k)
        addr_in = self.last_addr[:12]
        addr_out = self.next_addr[:12]
        addr_width = len(addr_in)

        inc_addr = Signal.like(addr_in)
        m.d.comb += inc_addr.eq(addr_in + inc)

        # WRAP is the only valid burst type that has the top bit set
        iswrap = self.burst[1]

        wrapped_addr = Signal.like(addr_in)
        unaligned_addr = Signal.like(addr_in)
        aligned_addr = Signal.like(addr_in)

        m.d.comb += [wrapped_addr.eq(addr_in),
                     aligned_addr.eq(unaligned_addr),
                     unaligned_addr.eq(Mux(iswrap, wrapped_addr, inc_addr))]

        # For wrapping, we know that len[0] is 1
        wrap_len = Cat(1, self.len[1:])
        with m.If(size == 0):
            mask_len = self.len_width
            wrap_mask = wrap_len
            m.d.comb += [wrapped_addr[mask_len:].eq(addr_in[mask_len:]),
                         wrapped_addr[:mask_len].eq((inc_addr[:mask_len] & wrap_mask) |
                                                    (addr_in[:mask_len] & ~wrap_mask))]
        for bits in range(1, maxbit + 1):
            if maxbit == 2:
                if bits == 1:
                    cond = size[0]
                else:
                    assert bits == 2
                    cond = size[1]
            elif maxbit == 4 and bits == 4:
                cond = size[2]
            else:
                cond = size == bits

            mask_len = self.len_width + bits
            wrap_mask = (wrap_len << bits)[:mask_len]
            with m.If(cond):
                m.d.comb += [wrapped_addr[mask_len:].eq(addr_in[mask_len:]),
                             wrapped_addr[:mask_len].eq((inc_addr[:mask_len] & wrap_mask) |
                                                        (addr_in[:mask_len] & ~wrap_mask)),
                             aligned_addr.eq(Cat(C(0, bits), unaligned_addr[bits:]))]

        with m.If(self.burst == 0):
            m.d.comb += addr_out.eq(addr_in)
        with m.Else():
            m.d.comb += addr_out.eq(aligned_addr if self.do_realign else unaligned_addr)

        return m

def _axi_next_addr(m, last_addr, size, burst, _len, data_width, do_realign):
    axiaddr = AxiAddr(addr_width=len(last_addr), data_width=data_width,
                      len_width=len(_len), do_realign=do_realign)
    axiaddr.last_addr = last_addr
    axiaddr.size = size
    axiaddr.burst = burst
    axiaddr.len = _len
    m.submodules += axiaddr
    return axiaddr.next_addr

def axi_next_addr(m, *, last_addr, size, burst, len, data_width, do_realign=False):
    return _axi_next_addr(m, last_addr, size, burst, len, data_width, do_realign)

if __name__ == '__main__':
    from amaranth.back import verilog

    m = AXIAddr(addr_width=32, data_width=32, len_width=4, do_realign=True)
    print(verilog.convert(m, ports=[m.last_addr, m.size, m.burst, m.len, m.next_addr]))
