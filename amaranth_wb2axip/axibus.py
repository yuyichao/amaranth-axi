#

from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

class Signature(wiring.Signature):
    def __init__(self, data_width, addr_width, id_width=0, user_width=0, *,
                 version, lite):
        assert version in [3, 4]
        if lite or user_width != 0:
            assert version != 3
        self._data_width = data_width
        self._addr_width = addr_width
        self._id_width = id_width
        self._user_width = user_width
        self._version = version
        self._lite = lite
        pins = {
            'ARADDR': Out(addr_width),
            'ARPROT': Out(3),
            'ARREADY': In(1),
            'ARVALID': Out(1),

            'AWADDR': Out(addr_width),
            'AWPROT': Out(3),
            'AWREADY': In(1),
            'AWVALID': Out(1),

            'BREADY': Out(1),
            'BRESP': In(2),
            'BVALID': In(1),

            'RDATA': In(data_width),
            'RREADY': Out(1),
            'RRESP': In(2),
            'RVALID': In(1),

            'WDATA': Out(data_width),
            'WREADY': In(1),
            'WSTRB': Out(data_width // 8),
            'WVALID': Out(1),
        }
        if not lite:
            pins.update({
                "ARBURST": Out(2),
                "ARCACHE": Out(4),
                "ARID": Out(id_width),
                "ARLEN": Out(8 if version == 4 else 4),
                "ARLOCK": Out(1 if version == 4 else 2),
                "ARSIZE": Out(3),

                "AWBURST": Out(2),
                "AWCACHE": Out(4),
                "AWID": Out(id_width),
                "AWLEN": Out(8 if version == 4 else 4),
                "AWLOCK": Out(1 if version == 4 else 2),
                "AWSIZE": Out(3),

                "BID": In(id_width),

                "RID": In(id_width),
                "RLAST": In(1),

                "WLAST": Out(1),
            })
            if version == 4:
                pins.update({
                    "ARQOS": Out(4),
                    # "ARREGION": Out(4),

                    "AWQOS": Out(4),
                    # "AWREGION": Out(4),
                })
                if user_width != 0:
                    pins.update({
                        "ARUSER": Out(user_width),
                        "AWUSER": Out(user_width),
                        # "BUSER": In(user_width)
                    })
            # Ignore AXI3-only WID signal.
        super().__init__(pins)

    def __repr__(self):
        return f'axibus.Signature({self._data_width}, {self._addr_width}, {self._id_width}, {self._user_width}, version={self._version}, lite={self._lite})'

    def __eq__(self, other):
        return (isinstance(other, Signature) and
                self._data_width == other._data_width and
                self._addr_width == other._addr_width and
                self._id_width == other._id_width and
                self._user_width == other._user_width and
                self._version == other._version and
                self._lite == other._lite)

    @property
    def data_width(self):
        return self._data_width

    @property
    def addr_width(self):
        return self._addr_width

    @property
    def id_width(self):
        return self._id_width

    @property
    def user_width(self):
        return self._user_width

    @property
    def axi_version(self):
        return self._version

    @property
    def is_lite(self):
        return self._lite

    @property
    def is_master(self):
        return not isinstance(self, wiring.FlippedSignature)

    @property
    def is_slave(self):
        return isinstance(self, wiring.FlippedSignature)

    def create(self, *, path=None, src_loc_at=0):
        return Interface(self, path=path, src_loc_at=src_loc_at + 1)

    def get_port_for_instance(self, iface, prefix=''):
        return {('i_' if port.flow is In else 'o_') + prefix + name: getattr(iface, name)
                for name, port in self.members.items()}

class Interface(wiring.PureInterface):
    def get_ports_for_instance(self, prefix=''):
        return self.signature.get_port_for_instance(self, prefix)

    @property
    def all_ports(self):
        return [signal for path, _, signal in self.signature.flatten(self)]

    def _cast_signal(self, m, name, port, width, is_slave):
        orig_w = len(port)
        if orig_w == width:
            return port
        if isinstance(port, Const):
            return Const(port.value, width)
        new_port = Signal(width, name=name + '_cast')
        min_w = min(width, orig_w)
        if is_slave:
            m.d.comb += port[:min_w].eq(new_port[:min_w])
        else:
            m.d.comb += port[:min_w].eq(port[:min_w])
            if width > min_w:
                m.d.comb += new_port[min_w:].eq(Const(0, width - min_w))
        return new_port

    def cast(self, m, addr_width=None, user_width=None, src_loc_at=0):
        old_sig = self.signature
        if user_width is None:
            user_width = old_sig.user_width
        elif user_width != 0:
            assert old_sig.axi_version == 4 and not old_sig.is_lite
        if addr_width is None:
            addr_width = old_sig.addr_width
        if addr_width == old_sig.addr_width and user_width == old_sig.user_width:
            return self
        sig = Signature(old_sig.data_width, addr_width, old_sig.id_width, user_width,
                        version=old_sig.axi_version, lite=old_sig.is_lite)
        is_slave = old_sig.is_slave
        if is_slave:
            sig = sig.flip()
        new_iface = sig.create(src_loc_at=src_loc_at + 1)
        for name in sig.members.keys():
            if (name == 'ARUSER' or name == 'AWUSER') and old_sig.user_width == 0:
                port = Signal(0, name=name + '_dummy')
            else:
                port = getattr(self, name)
            if name == 'ARADDR' or name == 'AWADDR':
                port = self._cast_signal(m, name, port, addr_width, is_slave)
            elif name == 'ARUSER' or name == 'AWUSER':
                port = self._cast_signal(m, name, port, user_width, is_slave)
            setattr(new_iface, name, port)
        return new_iface

def AXI3(data_width, addr_width, id_width):
    return Signature(data_width, addr_width, id_width, 0, version=3, lite=False)

def AXI4(data_width, addr_width, id_width, user_width=0):
    return Signature(data_width, addr_width, id_width, user_width, version=4, lite=False)

def AXI4Lite(data_width, addr_width):
    return Signature(data_width, addr_width, 0, 0, version=4, lite=True)
