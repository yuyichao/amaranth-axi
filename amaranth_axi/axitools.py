#

from amaranth import *
from amaranth.utils import exact_log2

from transactron import TModule, Method, def_method
from transactron.lib import condition

from .adaptors import InAdaptor, OutAdaptor
from .axiaddr import AXIAddr
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
            data=axil.AWADDR[self._clear_bits:], buffered=self._in_buffered,
            domain=self.domain)

        m.submodules.wd_adapt = wd_adapt = InAdaptor.from_signal(
            ready=axil.WREADY, valid=axil.WVALID,
            data=StructCat(data=axil.WDATA, strb=axil.WSTRB),
            buffered=self._in_buffered,
            domain=self.domain)

        @def_method(m, self.get)
        def _():
            addr = Cat(C(0, self._clear_bits), wa_adapt.input(m).DATA)
            wd_data = wd_adapt.input(m)
            return dict(addr=addr, data=wd_data.data, strb=wd_data.strb)

        m.submodules.b_adapt = b_adapt = OutAdaptor.from_signal(
            ready=axil.BREADY, valid=axil.BVALID,
            data=StructCat(resp=axil.BRESP), buffered=self._out_buffered,
            domain=self.domain)

        self._done.provide(b_adapt.output)

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
            data=axil.ARADDR[self._clear_bits:], buffered=self._in_buffered,
            domain=self.domain)

        @def_method(m, self.get)
        def _():
            return dict(addr=Cat(C(0, self._clear_bits), ra_adapt.input(m).DATA))

        m.submodules.rd_adapt = rd_adapt = OutAdaptor.from_signal(
            ready=axil.RREADY, valid=axil.RVALID,
            data=StructCat(data=axil.RDATA, resp=axil.RRESP),
            buffered=self._out_buffered, domain=self.domain)

        self._done.provide(rd_adapt.output)

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
            data=axil.AWADDR[self._clear_bits:],
            buffered=self._out_buffered, domain=self.domain)
        m.d.comb += axil.AWADDR[:self._clear_bits].eq(0)

        m.submodules.wd_adapt = wd_adapt = OutAdaptor.from_signal(
            ready=axil.WREADY, valid=axil.WVALID,
            data=StructCat(data=axil.WDATA, strb=axil.WSTRB),
            buffered=self._out_buffered, domain=self.domain)

        @def_method(m, self._request)
        def _(addr, data, strb):
            wa_adapt.output(m, addr[self._clear_bits:])
            wd_adapt.output(m, data=data, strb=strb)

        m.submodules.b_adapt = b_adapt = InAdaptor.from_signal(
            ready=axil.BREADY, valid=axil.BVALID,
            data=StructCat(resp=axil.BRESP),
            buffered=self._in_buffered, domain=self.domain)

        self.reply.provide(b_adapt.input)

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
            data=axil.ARADDR[self._clear_bits:],
            buffered=self._out_buffered, domain=self.domain)

        @def_method(m, self.request)
        def _(addr):
            ra_adapt.output(m, addr[self._clear_bits:])

        m.submodules.rd_adapt = rd_adapt = InAdaptor.from_signal(
            ready=axil.RREADY, valid=axil.RVALID,
            data=StructCat(data=axil.RDATA, resp=axil.RRESP),
            buffered=self._in_buffered, domain=self.domain)

        self.reply.provide(rd_adapt.input)

        return m


class AXISlaveWriteIFace(Elaboratable):
    def __init__(self, axi, *, domain='sync', align_address=True,
                 use_cache=False, use_lock=False, use_size=False,
                 use_user=False, **kws):
        self.domain = domain

        self._axi = axi
        self._data_width = len(axi.WDATA)
        self._id_width = len(axi.AWID)

        self._in_buffered, self._out_buffered = _parse_buffered(**kws)
        self._align_address = align_address
        self._clear_bits = exact_log2(self._data_width//8) if align_address else 0
        self._use_cache = use_cache
        self._use_lock = use_lock
        self._use_size = use_size
        self._use_user = use_user

        get_layout = [('addr', len(axi.AWADDR)), ('data', self._data_width),
                      ('strb', self._data_width//8), ('id', self._id_width),
                      ('last', 1)]
        if use_cache:
            get_layout.append(('cache', len(axi.AWCACHE)))
        if use_lock:
            get_layout.append(('lock', len(axi.AWLOCK)))
        if use_size:
            get_layout.append(('size', len(axi.AWSIZE)))
        if use_user:
            get_layout.append(('user', len(axi.AWUSER)))

        self.get = Method(o=get_layout)
        self._done = Method(i=[('id', self._id_width), ('resp', 2)])

    def done(self, m, /, id, resp=0):
        return self._done(m, id=id, resp=resp)

    def elaborate(self, plat):
        m = TModule()

        axi = self._axi
        addr_width = len(axi.AWADDR)

        # We need the full address to handle burst correctly.
        wa_data = dict(addr=axi.AWADDR, id=axi.AWID, size=axi.AWSIZE,
                       burst=axi.AWBURST, len=axi.AWLEN)

        if self._use_cache:
            wa_data['cache'] = axi.AWCACHE
        if self._use_lock:
            wa_data['lock'] = axi.AWLOCK
        if self._use_user:
            wa_data['user'] = axi.AWUSER

        m.submodules.wa_adapt = wa_adapt = InAdaptor.from_signal(
            ready=axi.AWREADY, valid=axi.AWVALID,
            data=StructCat(**wa_data), buffered=self._in_buffered, domain=self.domain)

        m.submodules.wd_adapt = wd_adapt = InAdaptor.from_signal(
            ready=axi.WREADY, valid=axi.WVALID,
            data=StructCat(data=axi.WDATA, strb=axi.WSTRB, last=axi.WLAST),
            buffered=self._in_buffered, domain=self.domain)

        get_wa = Method.like(wa_adapt.input)
        wa_cache = Signal(wa_adapt.input.layout_out)
        wa_saved = Signal()
        @def_method(m, get_wa)
        def _():
            m.d[self.domain] += wa_saved.eq(1)
            with condition(m, nonblocking=True) as branch:
                with branch(~wa_saved):
                    new_wa = wa_adapt.input(m)
                    m.d[self.domain] += wa_cache.eq(new_wa)

            res = Signal.like(new_wa)
            m.d.top_comb += res.eq(Mux(wa_saved, wa_cache, new_wa))

            wraddr = AXIAddr.from_signal(last_addr=res.addr,
                                         size=res.size,
                                         burst=res.burst, len=res.len,
                                         data_width=self._data_width,
                                         do_realign=not self._align_address)
            m.submodules.wraddr = wraddr
            m.d[self.domain] += wa_cache.addr.eq(wraddr.next_addr)
            return res


        @def_method(m, self.get)
        def _():
            wa = get_wa(m)
            wd = wd_adapt.input(m)
            with m.If(wd.last):
                m.d[self.domain] += wa_saved.eq(0) # Release address cache
            res = dict(addr=Cat(C(0, self._clear_bits), wa.addr[self._clear_bits:]),
                       data=wd.data, strb=wd.strb, id=wa.id, last=wd.last)
            if self._use_cache:
                res['cache'] = wa.cache
            if self._use_lock:
                res['lock'] = wa.lock
            if self._use_size:
                res['size'] = wa.size
            if self._use_user:
                res['user'] = wa.user
            return res

        m.submodules.b_adapt = b_adapt = OutAdaptor.from_signal(
            ready=axi.BREADY, valid=axi.BVALID,
            data=StructCat(id=axi.BID, resp=axi.BRESP),
            buffered=self._out_buffered, domain=self.domain)

        self._done.provide(b_adapt.output)

        return m


class AXISlaveReadIFace(Elaboratable):
    def __init__(self, axi, *, domain='sync', align_address=True,
                 use_cache=False, use_lock=False, use_size=False,
                 use_user=False, **kws):
        self.domain = domain

        self._axi = axi
        self._data_width = len(axi.RDATA)
        self._id_width = len(axi.ARID)

        self._in_buffered, self._out_buffered = _parse_buffered(**kws)
        self._align_address = align_address
        self._clear_bits = exact_log2(self._data_width//8) if align_address else 0
        self._use_cache = use_cache
        self._use_lock = use_lock
        self._use_size = use_size
        self._use_user = use_user

        get_layout = [('addr', len(axi.ARADDR)), ('id', self._id_width), ('last', 1)]
        if use_cache:
            get_layout.append(('cache', len(axi.ARCACHE)))
        if use_lock:
            get_layout.append(('lock', len(axi.ARLOCK)))
        if use_size:
            get_layout.append(('size', len(axi.ARSIZE)))
        if use_user:
            get_layout.append(('user', len(axi.ARUSER)))

        self.get = Method(o=get_layout)
        self._done = Method(i=[('id', self._id_width), ('data', self._data_width),
                               ('last', 1), ('resp', 2)])

    def done(self, m, /, id, data, last, resp=0):
        return self._done(m, id=id, data=data, last=last, resp=resp)

    def elaborate(self, plat):
        m = TModule()

        axi = self._axi
        addr_width = len(axi.ARADDR)

        # We need the full address to handle burst correctly.
        ra_data = dict(addr=axi.ARADDR, id=axi.ARID, size=axi.ARSIZE,
                       burst=axi.ARBURST, len=axi.ARLEN)

        if self._use_cache:
            ra_data['cache'] = axi.ARCACHE
        if self._use_lock:
            ra_data['lock'] = axi.ARLOCK
        if self._use_user:
            ra_data['user'] = axi.ARUSER

        m.submodules.ra_adapt = ra_adapt = InAdaptor.from_signal(
            ready=axi.ARREADY, valid=axi.ARVALID,
            data=StructCat(**ra_data), buffered=self._in_buffered, domain=self.domain)

        ra_cache = Signal(ra_adapt.input.layout_out)
        ra_count = Signal(len(axi.ARLEN))
        ra_saved = Signal()

        @def_method(m, self.get)
        def _():
            with condition(m, nonblocking=True) as branch:
                with branch(~ra_saved):
                    new_ra = ra_adapt.input(m)
                    m.d[self.domain] += ra_cache.eq(new_ra)

            ra = Signal.like(new_ra)
            m.d.top_comb += ra.eq(Mux(ra_saved, ra_cache, new_ra))

            count = Signal.like(ra_count)
            m.d.top_comb += count.eq(Mux(ra_saved, ra_count, new_ra.len))
            m.d[self.domain] += ra_count.eq(count - 1)

            last = count == 0
            m.d[self.domain] += ra_saved.eq(~last)

            rdaddr = AXIAddr.from_signal(last_addr=ra.addr,
                                         size=ra.size,
                                         burst=ra.burst, len=ra.len,
                                         data_width=self._data_width,
                                         do_realign=not self._align_address)
            m.submodules.rdaddr = rdaddr
            m.d[self.domain] += ra_cache.addr.eq(rdaddr.next_addr)

            res = dict(addr=Cat(C(0, self._clear_bits), ra.addr[self._clear_bits:]),
                       id=ra.id, last=last)
            if self._use_cache:
                res['cache'] = ra.cache
            if self._use_lock:
                res['lock'] = ra.lock
            if self._use_size:
                res['size'] = ra.size
            if self._use_user:
                res['user'] = ra.user

            return res

        m.submodules.rd_adapt = rd_adapt = OutAdaptor.from_signal(
            ready=axi.RREADY, valid=axi.RVALID,
            data=StructCat(id=axi.RID, data=axi.RDATA, last=axi.RLAST, resp=axi.RRESP),
            buffered=self._out_buffered, domain=self.domain)

        self._done.provide(rd_adapt.output)

        return m


class AXIMasterWriteIFace(Elaboratable):
    def __init__(self, axi, *, domain='sync', align_address=True,
                 use_cache=False, use_lock=False, use_user=False, **kws):
        self.domain = domain

        self._axi = axi
        self._data_width = len(axi.WDATA)
        self._id_width = len(axi.AWID)

        self._in_buffered, self._out_buffered = _parse_buffered(**kws)
        self._align_address = align_address
        self._clear_bits = exact_log2(self._data_width//8) if align_address else 0
        self._use_cache = use_cache
        self._use_lock = use_lock
        self._use_user = use_user

        addr_req_layout = [('addr', len(axi.AWADDR)), ('id', self._id_width),
                           ('size', len(axi.AWSIZE)), ('len', len(axi.AWLEN)),
                           ('burst', 2)]
        if use_cache:
            addr_req_layout.append(('cache', len(axi.AWCACHE)))
        if use_lock:
            addr_req_layout.append(('lock', len(axi.AWLOCK)))
        if use_user:
            addr_req_layout.append(('user', len(axi.AWUSER)))
        self.addr_request = Method(i=addr_req_layout)

        data_req_layout = [('data', self._data_width), ('last', 1),
                           ('strb', self._data_width//8)]
        if hasattr(axi, 'WID'):
            data_req_layout.append(('id', len(axi.WID)))
        self._data_request = Method(i=data_req_layout)

        self.reply = Method(o=[('id', self._id_width), ('resp', 2)])

    def data_request(self, m, /, data, last, strb=None):
        nbytes = self._data_width // 8
        if strb is None:
            strb = (1 << nbytes) - 1
        return self._data_request(m, data=data, last=last, strb=strb)

    def elaborate(self, plat):
        m = TModule()

        axi = self._axi
        addr_width = len(axi.AWADDR)

        wa_data = dict(addr=axi.AWADDR[self._clear_bits:], id=axi.AWID, size=axi.AWSIZE,
                       burst=axi.AWBURST, len=axi.AWLEN)
        if self._use_cache:
            wa_data['cache'] = axi.AWCACHE
        if self._use_lock:
            wa_data['lock'] = axi.AWLOCK
        if self._use_user:
            wa_data['user'] = axi.AWUSER

        m.submodules.wa_adapt = wa_adapt = OutAdaptor.from_signal(
            ready=axi.AWREADY, valid=axi.AWVALID,
            data=StructCat(**wa_data), buffered=self._out_buffered, domain=self.domain)
        m.d.comb += axi.AWADDR[:self._clear_bits].eq(0)

        @def_method(m, self.addr_request)
        def _(arg):
            out_data = dict(addr=arg.addr[self._clear_bits:],
                            id=arg.id, size=arg.size, burst=arg.burst, len=arg.len)
            if self._use_cache:
                out_data['cache'] = arg.cache
            if self._use_lock:
                out_data['lock'] = arg.lock
            if self._use_user:
                out_data['user'] = arg.user
            wa_adapt.output(m, **out_data)

        widkws = {}
        if hasattr(axi, 'WID'):
            widkws['id'] = axi.WID
        m.submodules.wd_adapt = wd_adapt = OutAdaptor.from_signal(
            ready=axi.WREADY, valid=axi.WVALID,
            data=StructCat(data=axi.WDATA, last=axi.WLAST, strb=axi.WSTRB, **widkws),
            buffered=self._out_buffered, domain=self.domain)

        self._data_request.provide(wd_adapt.output)

        m.submodules.b_adapt = b_adapt = InAdaptor.from_signal(
            ready=axi.BREADY, valid=axi.BVALID,
            data=StructCat(id=axi.BID, resp=axi.BRESP),
            buffered=self._in_buffered, domain=self.domain)

        self.reply.provide(b_adapt.input)

        return m


class AXIMasterReadIFace(Elaboratable):
    def __init__(self, axi, *, domain='sync', align_address=True,
                 use_cache=False, use_lock=False, use_user=False, **kws):
        self.domain = domain

        self._axi = axi
        self._data_width = len(axi.RDATA)
        self._id_width = len(axi.ARID)

        self._in_buffered, self._out_buffered = _parse_buffered(**kws)
        self._align_address = align_address
        self._clear_bits = exact_log2(self._data_width//8) if align_address else 0
        self._use_cache = use_cache
        self._use_lock = use_lock
        self._use_user = use_user

        req_layout = [('addr', len(axi.ARADDR)), ('id', self._id_width),
                      ('size', len(axi.ARSIZE)), ('len', len(axi.ARLEN)),
                      ('burst', 2)]
        if use_cache:
            req_layout.append(('cache', len(axi.ARCACHE)))
        if use_lock:
            req_layout.append(('lock', len(axi.ARLOCK)))
        if use_user:
            req_layout.append(('user', len(axi.ARUSER)))
        self.request = Method(i=req_layout)

        self.reply = Method(o=[('id', self._id_width), ('data', self._data_width),
                               ('last', 1), ('resp', 2)])

    def elaborate(self, plat):
        m = TModule()

        axi = self._axi
        addr_width = len(axi.ARADDR)

        ra_data = dict(addr=axi.ARADDR[self._clear_bits:], id=axi.ARID, size=axi.ARSIZE,
                       burst=axi.ARBURST, len=axi.ARLEN)
        if self._use_cache:
            ra_data['cache'] = axi.ARCACHE
        if self._use_lock:
            ra_data['lock'] = axi.ARLOCK
        if self._use_user:
            ra_data['user'] = axi.ARUSER

        m.submodules.ra_adapt = ra_adapt = OutAdaptor.from_signal(
            ready=axi.ARREADY, valid=axi.ARVALID,
            data=StructCat(**ra_data), buffered=self._out_buffered, domain=self.domain)
        m.d.comb += axi.ARADDR[:self._clear_bits].eq(0)

        @def_method(m, self.request)
        def _(arg):
            out_data = dict(addr=arg.addr[self._clear_bits:],
                            id=arg.id, size=arg.size, burst=arg.burst, len=arg.len)
            if self._use_cache:
                out_data['cache'] = arg.cache
            if self._use_lock:
                out_data['lock'] = arg.lock
            if self._use_user:
                out_data['user'] = arg.user
            ra_adapt.output(m, **out_data)

        m.submodules.rd_adapt = rd_adapt = InAdaptor.from_signal(
            ready=axi.RREADY, valid=axi.RVALID,
            data=StructCat(id=axi.RID, data=axi.RDATA, last=axi.RLAST, resp=axi.RRESP),
            buffered=self._in_buffered, domain=self.domain)

        self.reply.provide(rd_adapt.input)

        return m


def axi_write_reg(m, reg, data, strb, *, domain='sync'):
    width = len(data)
    for i in range(width//8):
        with m.If(strb[i]):
            m.d[domain] += reg[i * 8:i * 8 + 8].eq(data[i * 8:i * 8 + 8])
