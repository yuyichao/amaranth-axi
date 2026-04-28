#

from amaranth import *
from amaranth.utils import exact_log2

from transactron import TModule, Method, def_method

from .adaptors import InAdaptor, OutAdaptor
from .utils import StructCat

def _parse_buffered(buffered=None, in_buffered=None, out_buffered=None):
    if buffered is not None:
        if in_buffered is None:
            in_buffered = buffered
        if out_buffered is None:
            out_buffered = buffered
    return bool(in_buffered), bool(out_buffered)


class AXILSlaveWriteIFace(Elaboratable):
    def __init__(self, axil, *, domain='sync', align_address=True, **kws):
        self._axil = axil
        self._data_width = len(axil.WDATA)
        self.domain = domain
        self._in_buffered, self._out_buffered = _parse_buffered(**kws)
        self._clear_bits = exact_log2(self._data_width//8) if align_address else 0
        self.get = Method(o=[('addr', len(axil.AWADDR)), ('data', self._data_width),
                             ('strb', self._data_width//8)])
        self._done = Method(i=[('resp', 2)])

    def done(self, m, /, resp=0):
        return self._done(m, resp=resp)

    def elaborate(self, plat):
        m = TModule()

        axil = self._axil
        addr_width = len(axil.AWADDR)

        m.submodules.wa_adapt = wa_adapt = InAdaptor.from_signal(
            ready=axil.AWREADY, valid=axil.AWVALID,
            data=axil.AWADDR[self._clear_bits:], buffered=self._in_buffered)

        m.submodules.wd_adapt = wd_adapt = InAdaptor.from_signal(
            ready=axil.WREADY, valid=axil.WVALID,
            data=StructCat(data=axil.WDATA, strb=axil.WSTRB),
            buffered=self._in_buffered)

        @def_method(m, self.get)
        def _():
            addr = Cat(C(0, self._clear_bits), wa_adapt.input(m).DATA)
            wd_data = wd_adapt.input(m)
            return dict(addr=addr, data=wd_data.data, strb=wd_data.strb)

        m.submodules.b_adapt = b_adapt = OutAdaptor.from_signal(
            ready=axil.BREADY, valid=axil.BVALID,
            data=axil.BRESP, buffered=self._out_buffered)

        @def_method(m, self._done)
        def _(resp):
            b_adapt.output(m, resp)

        return m


class AXILSlaveReadIFace(Elaboratable):
    def __init__(self, axil, *, domain='sync', align_address=True, **kws):
        self._axil = axil
        self._data_width = len(axil.RDATA)
        self.domain = domain
        self._in_buffered, self._out_buffered = _parse_buffered(**kws)
        self._clear_bits = exact_log2(self._data_width//8) if align_address else 0
        self.get = Method(o=[('addr', len(axil.ARADDR))])
        self._done = Method(i=[('data', self._data_width), ('resp', 2)])

    def done(self, m, /, data, resp=0):
        return self._done(m, data=data, resp=resp)

    def elaborate(self, plat):
        m = TModule()

        axil = self._axil

        m.submodules.ra_adapt = ra_adapt = InAdaptor.from_signal(
            ready=axil.ARREADY, valid=axil.ARVALID,
            data=axil.ARADDR[self._clear_bits:], buffered=self._in_buffered)

        @def_method(m, self.get)
        def _():
            return dict(addr=Cat(C(0, self._clear_bits), ra_adapt.input(m).DATA))

        m.submodules.rd_adapt = rd_adapt = OutAdaptor.from_signal(
            ready=axil.RREADY, valid=axil.RVALID,
            data=StructCat(data=axil.RDATA, resp=axil.RRESP), buffered=self._out_buffered)

        @def_method(m, self._done)
        def _(data, resp):
            rd_adapt.output(m, data=data, resp=resp)

        return m


class AXILMasterWriteIFace(Elaboratable):
    def __init__(self, axil, *, domain='sync', align_address=True, **kws):
        self._axil = axil
        self._data_width = len(axil.WDATA)
        self.domain = domain
        self._in_buffered, self._out_buffered = _parse_buffered(**kws)
        self._clear_bits = exact_log2(self._data_width//8) if align_address else 0
        self._request = Method(i=[('addr', len(axil.AWADDR)), ('data', self._data_width),
                                  ('strb', self._data_width//8)])
        self.reply = Method(o=[('resp', 2)])

    def request(self, m, /, addr, data, strb=None):
        nbytes = self._data_width // 8
        if strb is None:
            strb = (1 << nbytes) - 1
        return self._request(m, addr=addr, data=data, strb=strb)

    def elaborate(self, plat):
        m = TModule()

        axil = self._axil
        addr_width = len(axil.AWADDR)

        m.submodules.wa_adapt = wa_adapt = OutAdaptor.from_signal(
            ready=axil.AWREADY, valid=axil.AWVALID,
            data=axil.AWADDR[self._clear_bits:], buffered=self._out_buffered)
        m.d.comb += axil.AWADDR[:self._clear_bits].eq(0)

        m.submodules.wd_adapt = wd_adapt = OutAdaptor.from_signal(
            ready=axil.WREADY, valid=axil.WVALID,
            data=StructCat(data=axil.WDATA, strb=axil.WSTRB), buffered=self._out_buffered)

        @def_method(m, self._request)
        def _(addr, data, strb):
            wa_adapt.output(m, addr[self._clear_bits:])
            wd_adapt.output(m, data=data, strb=strb)

        m.submodules.b_adapt = b_adapt = InAdaptor.from_signal(
            ready=axil.BREADY, valid=axil.BVALID,
            data=axil.BRESP, buffered=self._in_buffered)

        @def_method(m, self.reply)
        def _():
            return b_adapt.input(m).DATA

        return m


class AXILMasterReadIFace(Elaboratable):
    def __init__(self, axil, *, domain='sync', align_address=True, **kws):
        self._axil = axil
        self._data_width = len(axil.RDATA)
        self.domain = domain
        self._in_buffered, self._out_buffered = _parse_buffered(**kws)
        self._clear_bits = exact_log2(self._data_width//8) if align_address else 0
        self.request = Method(i=[('addr', len(axil.ARADDR))])
        self.reply = Method(o=[('data', self._data_width), ('resp', 2)])

    def elaborate(self, plat):
        m = TModule()

        axil = self._axil

        m.submodules.ra_adapt = ra_adapt = OutAdaptor.from_signal(
            ready=axil.ARREADY, valid=axil.ARVALID,
            data=axil.ARADDR[self._clear_bits:], buffered=self._out_buffered)

        @def_method(m, self.request)
        def _(addr):
            ra_adapt.output(m, addr[self._clear_bits:])

        m.submodules.rd_adapt = rd_adapt = InAdaptor.from_signal(
            ready=axil.RREADY, valid=axil.RVALID,
            data=StructCat(data=axil.RDATA, resp=axil.RRESP), buffered=self._in_buffered)

        @def_method(m, self.reply)
        def _():
            d = rd_adapt.input(m).DATA
            return dict(data=d.data, resp=d.resp)

        return m


def axi_write_reg(m, reg, data, strb, *, domain='sync'):
    width = len(data)
    for i in range(width//8):
        with m.If(strb[i]):
            m.d[domain] += reg[i * 8:i * 8 + 8].eq(data[i * 8:i * 8 + 8])
