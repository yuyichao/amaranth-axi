#

from amaranth import *
from transactron import TModule, Method, def_method


class ReadyBuffer(Elaboratable):
    def __init__(self, *, ready, valid, data, domain='sync'):
        self._ready = ready
        self._valid = valid
        self._data = data
        self.domain = domain
        self.get = Method(o=[('data', data.shape())])
        self.peek = Method(o=[('valid', 1), ('data', data.shape())])

    def elaborate(self, plat):
        m = TModule()

        empty = Signal(1, init=1)

        buf = Signal(self._data.shape())

        m.d.comb += self._ready.eq(empty)

        out_valid = ~empty | self._valid
        out_data = Mux(empty, self._data, buf)

        with m.If(empty & self._valid):
            # If there's something coming in we'll assume it fills the cache.
            # If there's a simultaneous read the `get` method will set the `empty` flag.
            m.d[self.domain] += [empty.eq(0),
                                 buf.eq(self._data)]

        @def_method(m, self.get, ready=out_valid)
        def _():
            m.d[self.domain] += empty.eq(1)
            return dict(data=out_data)

        @def_method(m, self.peek, nonexclusive=True)
        def _():
            return dict(valid=out_valid, data=out_data)

        return m


def axi_write_reg(m, reg, data, strb, *, domain='sync'):
    width = len(data)
    for i in range(width//8):
        with m.If(strb[i]):
            m.d[domain] += reg[i * 8:i * 8 + 8].eq(data[i * 8:i * 8 + 8])
