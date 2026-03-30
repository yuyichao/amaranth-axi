#

from amaranth import *
from transactron import TModule, Method, def_method


class ReadyBuffer(Elaboratable):
    def __init__(self, *, ready, valid, data, domain='sync', buffered=False):
        self._ready = ready
        self._valid = valid
        self._data = data
        self.domain = domain
        self._buffered = buffered
        self.get = Method(o=[('data', data.shape())])
        self.peek = Method(o=[('valid', 1), ('data', data.shape())])

    def _elaborate_unbuffered(self, m):
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

    def _elaborate_buffered(self, m):
        buf0 = Signal(self._data.shape())
        buf1 = Signal(self._data.shape())

        in_ready = Signal(1, init=1)
        out_valid = Signal(1)

        m.d.comb += self._ready.eq(in_ready)

        def setn(n):
            if n == 0:
                m.d[self.domain] += [in_ready.eq(1),
                                     out_valid.eq(0)]
            elif n == 1:
                m.d[self.domain] += [in_ready.eq(1),
                                     out_valid.eq(1)]
            else:
                assert n == 2
                m.d[self.domain] += [in_ready.eq(0),
                                     out_valid.eq(1)]

        def checkn(n):
            if n == 0:
                return in_ready & ~out_valid
            elif n == 1:
                return in_ready & out_valid
            else:
                return ~in_ready & out_valid

        out_data = buf0

        with m.If(~self.get.run & self._valid):
            with m.If(checkn(0)):
                setn(1)
                m.d[self.domain] += buf0.eq(self._data)
            with m.If(checkn(1)):
                setn(2)
                m.d[self.domain] += buf1.eq(self._data)

        @def_method(m, self.get, ready=out_valid)
        def _():
            with m.If(self._valid):
                with m.If(checkn(1)):
                    m.d[self.domain] += [buf0.eq(self._data)]
                with m.If(checkn(2)):
                    setn(1)
                    m.d[self.domain] += [buf0.eq(buf1)]
            with m.Else():
                with m.If(checkn(1)):
                    setn(0)
                with m.If(checkn(2)):
                    setn(1)
                    m.d[self.domain] += buf0.eq(buf1)
            return dict(data=out_data)

        @def_method(m, self.peek, nonexclusive=True)
        def _():
            return dict(valid=out_valid, data=out_data)

    def elaborate(self, plat):
        m = TModule()

        if self._buffered:
            self._elaborate_buffered(m)
        else:
            self._elaborate_unbuffered(m)

        return m


class AXILSlaveWriteIFace(Elaboratable):
    def __init__(self, axil, *, domain='sync', buffered=False):
        self._axil = axil
        self._data_width = len(axil.WDATA)
        self.domain = domain
        self._buffered = buffered
        self.get = Method(o=[('addr', len(axil.AWADDR)), ('data', self._data_width),
                             ('strb', self._data_width//8)])
        self._done = Method(i=[('resp', 2)])

    def done(self, m, /, resp=0):
        return self._done(m, resp=resp)

    def elaborate(self, plat):
        m = TModule()

        axil = self._axil

        m.submodules.wa_buff = wa_buff = ReadyBuffer(ready=axil.AWREADY,
                                                     valid=axil.AWVALID,
                                                     data=axil.AWADDR,
                                                     buffered=self._buffered)

        m.submodules.wd_buff = wd_buff = ReadyBuffer(ready=axil.WREADY,
                                                     valid=axil.WVALID,
                                                     data=Cat(axil.WDATA, axil.WSTRB),
                                                     buffered=self._buffered)

        bresp = Signal(2, init=0)
        m.d.comb += axil.BRESP.eq(bresp)

        @def_method(m, self.get)
        def _():
            addr = wa_buff.get(m).data
            wd_data = wd_buff.get(m).data
            return dict(addr=addr,
                        data=wd_data[:self._data_width],
                        strb=wd_data[self._data_width:])

        with m.If(axil.BREADY):
            # Assume a transfer has happened unless override by `done()`
            m.d[self.domain] += axil.BVALID.eq(0)

        @def_method(m, self._done, ready=axil.BREADY)
        def _(resp):
            m.d[self.domain] += [axil.BVALID.eq(1),
                                 bresp.eq(resp)]

        return m


class AXILSlaveReadIFace(Elaboratable):
    def __init__(self, axil, *, domain='sync', buffered=False):
        self._axil = axil
        self._data_width = len(axil.RDATA)
        self.domain = domain
        self._buffered = buffered
        self.get = Method(o=[('addr', len(axil.ARADDR))])
        self._done = Method(i=[('data', self._data_width), ('resp', 2)])

    def done(self, m, /, data, resp=0):
        return self._done(m, data=data, resp=resp)

    def elaborate(self, plat):
        m = TModule()

        axil = self._axil

        m.submodules.ra_buff = ra_buff = ReadyBuffer(ready=axil.ARREADY,
                                                     valid=axil.ARVALID,
                                                     data=axil.ARADDR,
                                                     buffered=self._buffered)

        rresp = Signal(2, init=0)
        m.d.comb += axil.RRESP.eq(rresp)

        @def_method(m, self.get)
        def _():
            return dict(addr=ra_buff.get(m).data)

        with m.If(axil.RREADY):
            # Assume a transfer has happened unless override by `done()`
            m.d[self.domain] += axil.RVALID.eq(0)

        @def_method(m, self._done, ready=axil.RREADY)
        def _(data, resp):
            m.d[self.domain] += [axil.RDATA.eq(data),
                                 axil.RVALID.eq(1),
                                 rresp.eq(resp)]

        return m


def axi_write_reg(m, reg, data, strb, *, domain='sync'):
    width = len(data)
    for i in range(width//8):
        with m.If(strb[i]):
            m.d[domain] += reg[i * 8:i * 8 + 8].eq(data[i * 8:i * 8 + 8])
