#

from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

class AXIInterface(wiring.PureInterface):
    class Signature(wiring.Signature):
        def __init__(self, data_w, addr_w, id_w=0, user_w=0, *, version, lite):
            assert version in [3, 4]
            if lite or user_w != 0:
                assert version != 3
            self._data_w = data_w
            self._addr_w = addr_w
            self._id_w = id_w
            self._user_w = user_w
            self._version = version
            self._lite = lite
            pins = {
                'ARADDR': Out(addr_w),
                'ARPROT': Out(3),
                'ARREADY': In(1),
                'ARVALID': Out(1),

                'AWADDR': Out(addr_w),
                'AWPROT': Out(3),
                'AWREADY': In(1),
                'AWVALID': Out(1),

                'BREADY': Out(1),
                'BRESP': In(2),
                'BVALID': In(1),

                'RDATA': In(data_w),
                'RREADY': Out(1),
                'RRESP': In(2),
                'RVALID': In(1),

                'WDATA': Out(data_w),
                'WREADY': In(1),
                'WSTRB': Out(data_w // 8),
                'WVALID': Out(1),
            }
            if not lite:
                pins.update({
                    "ARBURST": Out(2),
                    "ARCACHE": Out(4),
                    "ARID": Out(id_w),
                    "ARLEN": Out(8 if version == 4 else 4),
                    "ARLOCK": Out(1 if version == 4 else 2),
                    "ARSIZE": Out(3),

                    "AWBURST": Out(2),
                    "AWCACHE": Out(4),
                    "AWID": Out(id_w),
                    "AWLEN": Out(8 if version == 4 else 4),
                    "AWLOCK": Out(1 if version == 4 else 2),
                    "AWSIZE": Out(3),

                    "BID": In(id_w),

                    "RID": In(id_w),
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
                    if user_w != 0:
                        pins.update({
                            "ARUSER": Out(user_w),
                            "AWUSER": Out(user_w),
                            # "BUSER": In(user_w)
                        })
                # Ignore AXI3-only WID signal.
            super().__init__(pins)

        def __repr__(self):
            return f'AXIInterface.Signature({self._data_w}, {self._addr_w}, {self._id_w}, {self._user_w}, version={self._version}, lite={self._lite})'

        def __eq__(self, other):
            return (isinstance(other, AXIInterface.Signature) and
                    self._data_w == other._data_w and self._addr_w == other._addr_w and
                    self._id_w == other._id_w and self._user_w == other._user_w and
                    self._version == other._version and self._lite == other._lite)

        @property
        def data_width(self):
            return self._data_w

        @property
        def addr_width(self):
            return self._addr_w

        @property
        def id_width(self):
            return self._id_w

        @property
        def user_width(self):
            return self._user_w

        @property
        def axi_version(self):
            return self._version

        @property
        def is_lite(self):
            return self._lite

        def create(self, *, path=None, src_loc_at=0):
            return AXIInterface(self, path=path, src_loc_at=src_loc_at + 1)

        def get_port_for_instance(self, iface, prefix=''):
            return {('i_' if port.flow is In else 'o_') + prefix + name: getattr(iface, name)
                    for name, port in self.members.items()}

    def get_ports_for_instance(self, prefix=''):
        return self.signature.get_port_for_instance(self, prefix)

    @property
    def all_ports(self):
        return [signal for path, _, signal in self.signature.flatten(self)]

def AXI3(data_w, addr_w, id_w):
    return AXIInterface.Signature(data_w, addr_w, id_w, 0, version=3, lite=False)

def AXI4(data_w, addr_w, id_w, user_w=0):
    return AXIInterface.Signature(data_w, addr_w, id_w, user_w, version=4, lite=False)

def AXI4Lite(data_w, addr_w):
    return AXIInterface.Signature(data_w, addr_w, 0, 0, version=4, lite=True)
