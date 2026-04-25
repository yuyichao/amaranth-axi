#

from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.data import StructLayout
from amaranth.lib.wiring import In, Out

from transactron import TModule, Transaction, Method, def_method

def _try_layout(layout):
    if isinstance(layout, StructLayout):
        return layout
    try:
        Shape.cast(layout)
        return [('DATA', layout)]
    except:
        return layout

class OutAdaptor(wiring.Component):
    @classmethod
    def from_signal(cls, *, ready, valid, data, **kws):
        adaptor = cls([('DATA', data.shape())], **kws)
        adaptor.READY = ready
        adaptor.VALID = valid
        adaptor.DATA = data
        return adaptor

    def __init__(self, layout, *, domain='sync', buffered=False):
        self.domain = domain
        self.buffered = buffered
        self.output = Method(i=_try_layout(layout))

        ports = dict(READY=In(1), VALID=Out(1), LEVEL=Out(2 if buffered else 1))
        for k, v in self.output.layout_in.members.items():
            if k == 'READY' or k == 'VALID':
                raise ValueError("Field name cannot be READY or VALID")
            ports[k] = Out(v)

        self.peek = Method(o=[('READY', 1)])
        super().__init__(ports)

    def elaborate(self, plat):
        m = TModule()

        out_buff = Signal(self.output.layout_in)
        for k, _ in self.output.layout_in.members.items():
            m.d.comb += getattr(self, k).eq(getattr(out_buff, k))

        buff = Signal(self.output.layout_in)
        meth_ready = Signal(init=1)

        @def_method(m, self.peek, nonexclusive=True)
        def _():
            return dict(READY=meth_ready)

        if not self.buffered:
            with m.If(self.READY):
                m.d[self.domain] += self.VALID.eq(0)

            m.d.comb += [meth_ready.eq(~self.VALID | self.READY),
                         self.LEVEL.eq(self.VALID)]
            with m.If(meth_ready):
                # We can override the output even when the method isn't running
                # as long as we don't need to hold the output.
                # This is the same condition as the condition when the output
                # will become useless with no input,
                # or basically that we are ready to run the method.
                m.d[self.domain] += out_buff.eq(buff)

            @def_method(m, self.output, ready=meth_ready)
            def _(arg):
                m.d.top_comb += buff.eq(arg)
                m.d[self.domain] += self.VALID.eq(1)
        else:
            def setn(n):
                if n == 0:
                    m.d[self.domain] += [meth_ready.eq(1),
                                         self.VALID.eq(0)]
                elif n == 1:
                    m.d[self.domain] += [meth_ready.eq(1),
                                         self.VALID.eq(1)]
                else:
                    assert n == 2
                    m.d[self.domain] += [meth_ready.eq(0),
                                         self.VALID.eq(1)]
            def checkn(n):
                if n == 0:
                    return meth_ready & ~self.VALID
                elif n == 1:
                    return meth_ready & self.VALID
                else:
                    return ~meth_ready & self.VALID

            with m.If(checkn(0)):
                m.d.comb += self.LEVEL.eq(0)
            with m.If(checkn(1)):
                m.d.comb += self.LEVEL.eq(1)
            with m.If(checkn(2)):
                m.d.comb += self.LEVEL.eq(2)
            with m.Else():
                # Dummy
                m.d.comb += self.LEVEL.eq(3)

            with m.If(~self.output.run & self.READY):
                # Potential output without input, it is always safe to
                # update the output using the buffer
                # since the 2->1 case is the only one where we still have a valid output
                m.d[self.domain] += out_buff.eq(buff)
                with m.If(checkn(1)):
                    setn(0)
                with m.If(checkn(2)):
                    setn(1)

            @def_method(m, self.output, ready=meth_ready)
            def _(arg):
                # We only care about the content of the internal buffer if `n == 2`
                # since we are never in `n == 2` if the method runs,
                # it is always safe to override the buffer in the method.
                m.d[self.domain] += buff.eq(arg)
                with m.If(checkn(1) & ~self.READY):
                    setn(2)
                with m.Else():
                    setn(1)
                    m.d[self.domain] += out_buff.eq(arg)

        return m

class InAdaptor(wiring.Component):
    @classmethod
    def from_signal(cls, *, ready, valid, data, **kws):
        adaptor = cls([('DATA', data.shape())], **kws)
        adaptor.READY = ready
        adaptor.VALID = valid
        adaptor.DATA = data
        return adaptor

    def __init__(self, layout, *, domain='sync', buffered=False):
        self.domain = domain
        self.buffered = buffered
        self.input = Method(o=_try_layout(layout))

        peek_layout = [('VALID', 1)]
        ports = dict(READY=Out(1), VALID=In(1), LEVEL=Out(2 if buffered else 1))
        for k, v in self.input.layout_out.members.items():
            if k == 'READY' or k == 'VALID':
                raise ValueError("Field name cannot be READY or VALID")
            ports[k] = In(v)
            peek_layout.append((k, v))

        self.peek = Method(o=peek_layout)
        super().__init__(ports)

    def elaborate(self, plat):
        m = TModule()

        in_buff = Signal(self.input.layout_out)
        for k, _ in self.input.layout_out.members.items():
            m.d.comb += getattr(in_buff, k).eq(getattr(self, k))
        out_buff = Signal(self.input.layout_out)
        buff = Signal(self.input.layout_out)

        in_ready = Signal(init=1)
        m.d.comb += self.READY.eq(in_ready)
        meth_ready = Signal(1)

        if not self.buffered:
            empty = in_ready
            with m.If(self.VALID):
                m.d[self.domain] += empty.eq(0)

            with m.If(empty):
                m.d[self.domain] += buff.eq(in_buff)

            m.d.comb += [meth_ready.eq(~empty | self.VALID),
                         out_buff.eq(Mux(empty, in_buff, buff)),
                         self.LEVEL.eq(~empty)]

            @def_method(m, self.input, ready=meth_ready)
            def _():
                m.d[self.domain] += empty.eq(1)
                return out_buff
        else:
            def setn(n):
                if n == 0:
                    m.d[self.domain] += [in_ready.eq(1),
                                         meth_ready.eq(0)]
                elif n == 1:
                    m.d[self.domain] += [in_ready.eq(1),
                                         meth_ready.eq(1)]
                else:
                    assert n == 2
                    m.d[self.domain] += [in_ready.eq(0),
                                         meth_ready.eq(1)]

            def checkn(n):
                if n == 0:
                    return in_ready & ~meth_ready
                elif n == 1:
                    return in_ready & meth_ready
                else:
                    return ~in_ready & meth_ready

            with m.If(checkn(0)):
                m.d.comb += self.LEVEL.eq(0)
            with m.If(checkn(1)):
                m.d.comb += self.LEVEL.eq(1)
            with m.If(checkn(2)):
                m.d.comb += self.LEVEL.eq(2)
            with m.Else():
                # Dummy
                m.d.comb += self.LEVEL.eq(3)

            with m.If(~self.input.run & self.VALID):
                with m.If(checkn(0)):
                    setn(1)
                    m.d[self.domain] += out_buff.eq(in_buff)
                with m.If(checkn(1)):
                    setn(2)
                    m.d[self.domain] += buff.eq(in_buff)

            @def_method(m, self.input, ready=meth_ready)
            def _():
                with m.If(checkn(1)):
                    with m.If(~self.VALID):
                        setn(0)
                    m.d[self.domain] += out_buff.eq(in_buff)
                with m.Else(): # n == 2
                    setn(1)
                    m.d[self.domain] += out_buff.eq(buff)
                return out_buff

        @def_method(m, self.peek, nonexclusive=True)
        def _():
            res = {'VALID': meth_ready}
            for k, _ in self.input.layout_out.members.items():
                res[k] = getattr(out_buff, k)
            return res

        return m
