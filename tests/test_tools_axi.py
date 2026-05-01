#

from amaranth import *
from amaranth.utils import exact_log2
from amaranth.lib.wiring import In, Out

from transactron import TModule, Transaction, Method, def_method
from transactron.testing import TestCaseWithSimulator, TestbenchIO as _TestbenchIO, CallTrigger
from transactron.lib.adapters import AdapterTrans

from amaranth_axi.axitools import AXIMasterWriteIFace, AXISlaveWriteIFace, AXIMasterReadIFace, AXISlaveReadIFace
from amaranth_axi.axibus import AXI3, AXI4

import pytest
import random

def struct_to_dict(s):
    return {name: getattr(s, name) for name in s.shape().members}


# Use a separate function to not shadow the `len` name in the main function
def _len_kw(*, len=None):
    return len

def decode_addr(*, data_width, align_address, addr, id, size, burst,
                cache=None, lock=None, user=None,
                use_cache=False, use_lock=False, use_size=False, use_user=False,
                wid=None, **kws):
    _len = _len_kw(**kws)
    assert _len is not None
    extras = {}
    if use_cache:
        assert cache is not None
        extras['cache'] = cache
    if use_lock:
        assert lock is not None
        extras['lock'] = lock
    if use_user:
        assert user is not None
        extras['user'] = user
    if use_size:
        extras['size'] = size
    fullsize = 1 << size

    if align_address:
        align_mask0 = ~(data_width // 8 - 1)
        align_mask = align_mask0
        addr = addr & align_mask0
    else:
        align_mask0 = -1
        align_mask = ~(fullsize - 1)

    def align_addr(addr, i):
        mask = align_mask0 if i == 0 else align_mask
        return addr & mask

    if burst == 0:
        for i in range(_len + 1):
            yield dict(addr=align_addr(addr, 0), id=id, last=int(i == _len), **extras)
        return

    if burst == 1:
        for i in range(_len + 1):
            yield dict(addr=align_addr(addr + i * fullsize, i), id=id,
                       last=int(i == _len), **extras)
        return

    assert burst == 2
    assert _len in (1, 3, 7, 15)
    block_size = (_len + 1) << size
    block_start = (addr // block_size) * block_size
    block_end = block_start + block_size

    for i in range(_len + 1):
        ele_addr = addr + i * fullsize
        if ele_addr >= block_end:
            ele_addr -= block_size
        assert ele_addr < block_end
        yield dict(addr=align_addr(ele_addr, i), id=id,
                   last=int(i == _len), **extras)


def decode_write(*, datas, strbs, **kws):
    # Ignoring wid
    for (addr, data, strb) in zip(decode_addr(**kws), datas, strbs):
        yield dict(data=data, strb=strb, **addr)

def decode_read(**kws):
    return decode_addr(**kws)

def gen_rand_addr(*, data_width, addr_width, id_width, len_width,
                  id=None, size=None, burst=None, cache_width=0, lock_width=0,
                  user_width=0, **kws):
    _len = _len_kw(**kws)

    addr_req = {}

    max_size = exact_log2(data_width) - 3
    if id is None:
        addr_req['id'] = random.randint(0, (1 << id_width) - 1)
    else:
        addr_req['id'] = id
    if size is None:
        size = random.randint(0, max_size)
    assert 0 <= size <= max_size
    addr_req['size'] = size
    if burst is None:
        if _len is not None and _len not in (1, 3, 7, 15):
            burst = random.randint(0, 1)
        else:
            burst = random.randint(0, 2)
    addr_req['burst'] = burst
    if burst == 2:
        if _len is None:
            _len = random.choice([1, 3, 7, 15])
        assert _len in (1, 3, 7, 15)
    else:
        if _len is None:
            _len = random.randint(0, (1 << len_width) - 1)
        assert (_len >> len_width) == 0
    addr_req['len'] = _len

    if burst == 1:
        last_offset = _len << size
        while True:
            addr = random.randint(0, (1 << addr_width) - 1)
            if addr // 4096 == (addr + last_offset) // 4096:
                break
    else:
        addr = random.randint(0, (1 << addr_width) - 1)
    addr_req['addr'] = addr

    if cache_width:
        addr_req['cache'] = random.randint(0, (1 << cache_width) - 1)
    if lock_width:
        addr_req['lock'] = random.randint(0, (1 << lock_width) - 1)
    if user_width:
        addr_req['user'] = random.randint(0, (1 << user_width) - 1)

    return addr_req

def gen_rand_write(*, data_width, strb=None, **kws):
    addr_req = gen_rand_addr(data_width=data_width, **kws)
    _len = addr_req['len']
    data_req = {}
    data_req['datas'] = [random.randint(0, (1 << data_width) - 1) for _ in range(_len + 1)]
    if strb is None:
        data_req['strbs'] = [random.randint(0, (1 << data_width // 8) - 1) for _ in range(_len + 1)]
    else:
        data_req['strbs'] = [strb for _ in range(_len + 1)]
    data_req['wid'] = addr_req['id']
    return addr_req, data_req

def gen_rand_read(**kws):
    return gen_rand_addr(**kws)

class AXIWritePair(Elaboratable):
    def __init__(self, axi, in_buffered, out_buffered, align_address,
                 use_cache=False, use_lock=False, use_size=False, use_user=False,
                 const_id=None, const_size=None, const_len=None, const_burst=None,
                 const_strb=None):
        self.master = AXIMasterWriteIFace(axi, align_address=align_address,
                                          in_buffered=in_buffered,
                                          out_buffered=out_buffered,
                                          const_cache=None if use_cache else 0,
                                          const_lock=None if use_lock else 0,
                                          const_user=None if use_user else 0,
                                          const_id=const_id, const_size=const_size,
                                          const_len=const_len, const_burst=const_burst,
                                          const_strb=const_strb)
        self.slave = AXISlaveWriteIFace(axi, align_address=align_address,
                                        in_buffered=in_buffered,
                                        out_buffered=out_buffered,
                                        use_cache=use_cache, use_lock=use_lock,
                                        use_size=use_size, use_user=use_user)

        self.addr_request = _TestbenchIO(AdapterTrans.create(self.master.addr_request))
        self.data_request = _TestbenchIO(AdapterTrans.create(self.master._data_request))
        self.get_reply = _TestbenchIO(AdapterTrans.create(self.master.reply))

        self.get_request = _TestbenchIO(AdapterTrans.create(self.slave.get))
        self.send_reply = _TestbenchIO(AdapterTrans.create(self.slave._done))

    def elaborate(self, plat):
        m = TModule()

        m.submodules.master = self.master
        m.submodules.slave = self.slave

        m.submodules.addr_request = self.addr_request
        m.submodules.data_request = self.data_request
        m.submodules.get_reply = self.get_reply

        m.submodules.get_request = self.get_request
        m.submodules.send_reply = self.send_reply

        return m

class AXIReadPair(Elaboratable):
    def __init__(self, axi, in_buffered, out_buffered, align_address,
                 use_cache=False, use_lock=False, use_size=False, use_user=False,
                 const_id=None, const_size=None, const_len=None, const_burst=None):
        self.master = AXIMasterReadIFace(axi, align_address=align_address,
                                         in_buffered=in_buffered,
                                         out_buffered=out_buffered,
                                         const_cache=None if use_cache else 0,
                                         const_lock=None if use_lock else 0,
                                         const_user=None if use_user else 0,
                                         const_id=const_id, const_size=const_size,
                                         const_len=const_len, const_burst=const_burst)
        self.slave = AXISlaveReadIFace(axi, align_address=align_address,
                                       in_buffered=in_buffered,
                                       out_buffered=out_buffered,
                                       use_cache=use_cache, use_lock=use_lock,
                                       use_size=use_size, use_user=use_user)

        self.request = _TestbenchIO(AdapterTrans.create(self.master.request))
        self.get_reply = _TestbenchIO(AdapterTrans.create(self.master.reply))

        self.get_request = _TestbenchIO(AdapterTrans.create(self.slave.get))
        self.send_reply = _TestbenchIO(AdapterTrans.create(self.slave._done))

    def elaborate(self, plat):
        m = TModule()

        m.submodules.master = self.master
        m.submodules.slave = self.slave

        m.submodules.request = self.request
        m.submodules.get_reply = self.get_reply

        m.submodules.get_request = self.get_request
        m.submodules.send_reply = self.send_reply

        return m

class TestAXIWrite(TestCaseWithSimulator):
    @pytest.mark.parametrize("in_buffered", [False, True])
    @pytest.mark.parametrize("out_buffered", [False, True])
    @pytest.mark.parametrize("align_address", [False, True])
    def test_reply_full_throughput(self, in_buffered, out_buffered, align_address):
        axi = AXI4(32, 32, 6).create()
        writer = AXIWritePair(axi, in_buffered, out_buffered, align_address)

        requests = []

        cycles = 100
        async def producer(sim):
            for _ in range(cycles):
                id = random.randint(0, (1 << 6) - 1)
                resp = random.randint(0, 3)
                assert (await writer.send_reply.call_try(sim, id=id, resp=resp)) is not None
                requests.append((id, resp))

        def check_reply(reply):
            assert reply is not None
            expected = requests.pop(0)
            assert reply.id == expected[0]
            assert reply.resp == expected[1]

        async def consumer(sim):
            check_reply(await writer.get_reply.call(sim))
            for _ in range(cycles - 1):
                reply = await writer.get_reply.call_try(sim)
                check_reply(reply)

        with self.run_simulation(writer) as sim:
            sim.add_testbench(producer)
            sim.add_testbench(consumer)

    @pytest.mark.parametrize("in_buffered", [False, True])
    @pytest.mark.parametrize("out_buffered", [False, True])
    @pytest.mark.parametrize("align_address", [False, True])
    @pytest.mark.parametrize("AXI", [AXI3, AXI4])
    def test_request_full_throughput(self, in_buffered, out_buffered, align_address,
                                     AXI):
        data_width = 32
        addr_width = 32
        id_width = 6
        axi = AXI(data_width, addr_width, id_width).create()
        len_width = len(axi.AWLEN)
        writer = AXIWritePair(axi, in_buffered, out_buffered, align_address)

        requests = []

        async def producer(sim):
            for _ in range(100):
                addr_req, data_req = gen_rand_write(data_width=data_width,
                                                    addr_width=addr_width,
                                                    id_width=id_width,
                                                    len_width=len_width)
                datas = data_req['datas']
                strbs = data_req['strbs']
                _len = addr_req['len']
                requests.extend(decode_write(data_width=data_width,
                                             align_address=align_address,
                                             **addr_req, **data_req))

                widkw = {}
                if AXI is AXI3:
                    widkw['id'] = data_req['wid']

                addr_res, data_res = await CallTrigger(sim) \
                  .call(writer.addr_request, **addr_req) \
                  .call(writer.data_request, data=datas[0], strb=strbs[0],
                        last=int(_len == 0), **widkw)
                assert addr_res is not None
                assert data_res is not None

                for i in range(_len):
                    assert (await writer.data_request.call_try(
                        sim, data=datas[i + 1], strb=strbs[i + 1],
                        last=int(i == _len - 1), **widkw)) is not None

        def check_reply(reply):
            assert reply is not None
            expected = requests.pop(0)
            assert struct_to_dict(reply) == expected

        async def consumer(sim):
            check_reply(await writer.get_request.call(sim))
            while requests:
                check_reply(await writer.get_request.call_try(sim))

        with self.run_simulation(writer) as sim:
            sim.add_testbench(producer)
            sim.add_testbench(consumer)

    @pytest.mark.parametrize("in_buffered", [False, True])
    @pytest.mark.parametrize("out_buffered", [False, True])
    @pytest.mark.parametrize("align_address", [False, True])
    @pytest.mark.parametrize("AXI", [AXI3, AXI4])
    @pytest.mark.parametrize("use_cache", [False, True])
    @pytest.mark.parametrize("use_lock", [False, True])
    @pytest.mark.parametrize("use_size", [False, True])
    @pytest.mark.parametrize("use_user", [False, True])
    def test_request_side_channel(self, in_buffered, out_buffered, align_address,
                                  AXI, use_cache, use_lock, use_size, use_user):
        data_width = 32
        addr_width = 32
        id_width = 3
        if use_user:
            if AXI is AXI3:
                return
            user_width = 4
            axi = AXI(data_width, addr_width, id_width, user_width=user_width).create()
        else:
            user_width = 0
            axi = AXI(data_width, addr_width, id_width).create()
        len_width = len(axi.AWLEN)
        cache_width = len(axi.AWCACHE) if use_cache else 0
        lock_width = len(axi.AWLOCK) if use_lock else 0
        writer = AXIWritePair(axi, in_buffered, out_buffered, align_address,
                              use_cache=use_cache, use_lock=use_lock,
                              use_size=use_size, use_user=use_user)

        requests = []

        async def producer(sim):
            for _ in range(5):
                addr_req, data_req = gen_rand_write(data_width=data_width,
                                                    addr_width=addr_width,
                                                    id_width=id_width,
                                                    len_width=len_width,
                                                    cache_width=cache_width,
                                                    lock_width=lock_width,
                                                    user_width=user_width)
                datas = data_req['datas']
                strbs = data_req['strbs']
                _len = addr_req['len']
                requests.extend(decode_write(data_width=data_width,
                                             align_address=align_address,
                                             use_cache=use_cache, use_lock=use_lock,
                                             use_size=use_size, use_user=use_user,
                                             **addr_req, **data_req))

                widkw = {}
                if AXI is AXI3:
                    widkw['id'] = data_req['wid']

                addr_res, data_res = await CallTrigger(sim) \
                  .call(writer.addr_request, **addr_req) \
                  .call(writer.data_request, data=datas[0], strb=strbs[0],
                        last=int(_len == 0), **widkw)
                assert addr_res is not None
                assert data_res is not None

                for i in range(_len):
                    assert (await writer.data_request.call_try(
                        sim, data=datas[i + 1], strb=strbs[i + 1],
                        last=int(i == _len - 1), **widkw)) is not None

        def check_reply(reply):
            assert reply is not None
            expected = requests.pop(0)
            assert struct_to_dict(reply) == expected

        async def consumer(sim):
            check_reply(await writer.get_request.call(sim))
            while requests:
                check_reply(await writer.get_request.call_try(sim))

        with self.run_simulation(writer) as sim:
            sim.add_testbench(producer)
            sim.add_testbench(consumer)

    @pytest.mark.parametrize("in_buffered", [False, True])
    @pytest.mark.parametrize("out_buffered", [False, True])
    @pytest.mark.parametrize("align_address", [False, True])
    @pytest.mark.parametrize("AXI", [AXI3, AXI4])
    @pytest.mark.parametrize("const_id", [None, 5])
    @pytest.mark.parametrize("const_size", [None, 1])
    @pytest.mark.parametrize("const_len", [None, 0, 2])
    @pytest.mark.parametrize("const_burst", [None, 0, 1])
    @pytest.mark.parametrize("const_strb", [None, 3])
    def test_request_const(self, in_buffered, out_buffered, align_address,
                           const_id, const_size, const_len, const_burst,
                           const_strb, AXI):
        data_width = 32
        addr_width = 32
        id_width = 3
        axi = AXI(data_width, addr_width, id_width).create()
        len_width = len(axi.AWLEN)
        writer = AXIWritePair(axi, in_buffered, out_buffered, align_address,
                              const_id=const_id, const_size=const_size,
                              const_len=const_len, const_burst=const_burst,
                              const_strb=const_strb)

        requests = []

        const_last = 1 if const_len is not None and const_len == 0 else None

        async def producer(sim):
            for _ in range(2):
                addr_req, data_req = gen_rand_write(data_width=data_width,
                                                    addr_width=addr_width,
                                                    id_width=id_width,
                                                    len_width=len_width,
                                                    id=const_id,
                                                    size=const_size,
                                                    len=const_len,
                                                    burst=const_burst,
                                                    strb=const_strb)
                datas = data_req['datas']
                strbs = data_req['strbs']
                _len = addr_req['len']
                requests.extend(decode_write(data_width=data_width,
                                             align_address=align_address,
                                             **addr_req, **data_req))

                widkw = {}
                if AXI is AXI3 and const_id is None:
                    widkw['id'] = data_req['wid']

                if const_id is not None:
                    del addr_req['id']
                if const_size is not None:
                    del addr_req['size']
                if const_len is not None:
                    del addr_req['len']
                if const_burst is not None:
                    del addr_req['burst']

                data_arg0 = dict(data=datas[0], strb=strbs[0],
                                 last=int(_len == 0), **widkw)
                if const_strb is not None:
                    del data_arg0['strb']
                if const_last is not None:
                    del data_arg0['last']
                addr_res, data_res = await CallTrigger(sim) \
                  .call(writer.addr_request, **addr_req) \
                  .call(writer.data_request, **data_arg0)
                assert addr_res is not None
                assert data_res is not None

                for i in range(_len):
                    data_arg = dict(data=datas[i + 1], strb=strbs[i + 1],
                                    last=int(i == _len - 1), **widkw)
                    if const_strb is not None:
                        del data_arg['strb']
                    if const_last is not None:
                        del data_arg['last']
                    assert (await writer.data_request.call_try(
                        sim, **data_arg)) is not None

        def check_reply(reply):
            assert reply is not None
            expected = requests.pop(0)
            assert struct_to_dict(reply) == expected

        async def consumer(sim):
            check_reply(await writer.get_request.call(sim))
            while requests:
                check_reply(await writer.get_request.call_try(sim))

        with self.run_simulation(writer) as sim:
            sim.add_testbench(producer)
            sim.add_testbench(consumer)

    @pytest.mark.parametrize("in_buffered", [False, True])
    @pytest.mark.parametrize("out_buffered", [False, True])
    @pytest.mark.parametrize("align_address", [False, True])
    @pytest.mark.parametrize("AXI", [AXI3, AXI4])
    @pytest.mark.parametrize("maxwait", [2, 6])
    def test_random(self, in_buffered, out_buffered, align_address, AXI, maxwait):
        data_width = 32
        addr_width = 32
        id_width = 6
        axi = AXI(data_width, addr_width, id_width).create()
        len_width = len(axi.AWLEN)
        writer = AXIWritePair(axi, in_buffered, out_buffered, align_address)

        addr_reqs = []
        data_reqs = []
        decoded_reqs = []

        for _ in range(100):
            addr_req, data_req = gen_rand_write(data_width=data_width,
                                                addr_width=addr_width,
                                                id_width=id_width,
                                                len_width=len_width)
            addr_reqs.append(addr_req)
            data_reqs.append(data_req)
            decoded_reqs.extend(decode_write(data_width=data_width,
                                             align_address=align_address,
                                             **addr_req, **data_req))

        async def rand_wait(sim):
            for _ in range(random.randint(0, maxwait)):
                await sim.tick()

        async def addr_producer(sim):
            while addr_reqs:
                addr_req = addr_reqs.pop(0)
                await rand_wait(sim)
                await writer.addr_request.call(sim, **addr_req)

        async def data_producer(sim):
            while data_reqs:
                data_req = data_reqs.pop(0)
                datas = data_req['datas']
                strbs = data_req['strbs']
                widkw = {}
                if AXI is AXI3:
                    widkw['id'] = data_req['wid']
                l = len(datas)
                for i in range(l):
                    await rand_wait(sim)
                    await writer.data_request.call(sim, data=datas[i], strb=strbs[i],
                                                   last=int(i == l - 1), **widkw)

        def check_reply(reply):
            assert reply is not None
            expected = decoded_reqs.pop(0)
            assert struct_to_dict(reply) == expected

        async def consumer(sim):
            while decoded_reqs:
                check_reply(await writer.get_request.call(sim))

        with self.run_simulation(writer) as sim:
            sim.add_testbench(addr_producer)
            sim.add_testbench(data_producer)
            sim.add_testbench(consumer)


class TestAXIRead(TestCaseWithSimulator):
    @pytest.mark.parametrize("in_buffered", [False, True])
    @pytest.mark.parametrize("out_buffered", [False, True])
    @pytest.mark.parametrize("align_address", [False, True])
    def test_read_reply_full_throughput(self, in_buffered, out_buffered, align_address):
        data_width = 32
        addr_width = 32
        id_width = 6
        axi = AXI4(data_width, addr_width, id_width).create()
        reader = AXIReadPair(axi, in_buffered, out_buffered, align_address)

        requests = []

        cycles = 100
        async def producer(sim):
            for _ in range(cycles):
                id = random.randint(0, (1 << id_width) - 1)
                resp = random.randint(0, 3)
                data = random.randint(0, (1 << data_width) - 1)
                last = random.randint(0, 1)
                assert (await reader.send_reply.call_try(sim, id=id, data=data,
                                                         last=last, resp=resp)) is not None
                requests.append(dict(id=id, data=data, last=last, resp=resp))

        def check_reply(reply):
            assert reply is not None
            expected = requests.pop(0)
            assert struct_to_dict(reply) == expected

        async def consumer(sim):
            check_reply(await reader.get_reply.call(sim))
            for _ in range(cycles - 1):
                reply = await reader.get_reply.call_try(sim)
                check_reply(reply)

        with self.run_simulation(reader) as sim:
            sim.add_testbench(producer)
            sim.add_testbench(consumer)

    @pytest.mark.parametrize("in_buffered", [False, True])
    @pytest.mark.parametrize("out_buffered", [False, True])
    @pytest.mark.parametrize("align_address", [False, True])
    @pytest.mark.parametrize("AXI", [AXI3, AXI4])
    def test_read_request_full_throughput(self, in_buffered, out_buffered, align_address,
                                          AXI):
        data_width = 32
        addr_width = 32
        id_width = 6
        axi = AXI(data_width, addr_width, id_width).create()
        len_width = len(axi.ARLEN)
        reader = AXIReadPair(axi, in_buffered, out_buffered, align_address)

        requests = []

        async def producer(sim):
            for _ in range(100):
                addr_req = gen_rand_read(data_width=data_width,
                                         addr_width=addr_width,
                                         id_width=id_width,
                                         len_width=len_width)
                requests.extend(decode_read(data_width=data_width,
                                            align_address=align_address,
                                            **addr_req))
                assert (await reader.request.call(sim, **addr_req)) is not None

        def check_reply(reply):
            assert reply is not None
            expected = requests.pop(0)
            assert struct_to_dict(reply) == expected

        async def consumer(sim):
            check_reply(await reader.get_request.call(sim))
            while requests:
                check_reply(await reader.get_request.call_try(sim))

        with self.run_simulation(reader) as sim:
            sim.add_testbench(producer)
            sim.add_testbench(consumer)

    @pytest.mark.parametrize("in_buffered", [False, True])
    @pytest.mark.parametrize("out_buffered", [False, True])
    @pytest.mark.parametrize("align_address", [False, True])
    @pytest.mark.parametrize("AXI", [AXI3, AXI4])
    @pytest.mark.parametrize("use_cache", [False, True])
    @pytest.mark.parametrize("use_lock", [False, True])
    @pytest.mark.parametrize("use_size", [False, True])
    @pytest.mark.parametrize("use_user", [False, True])
    def test_read_request_side_channel(self, in_buffered, out_buffered, align_address,
                                       AXI, use_cache, use_lock, use_size, use_user):
        data_width = 32
        addr_width = 32
        id_width = 3
        if use_user:
            if AXI is AXI3:
                return
            user_width = 4
            axi = AXI(data_width, addr_width, id_width, user_width=user_width).create()
        else:
            user_width = 0
            axi = AXI(data_width, addr_width, id_width).create()
        len_width = len(axi.ARLEN)
        cache_width = len(axi.ARCACHE) if use_cache else 0
        lock_width = len(axi.ARLOCK) if use_lock else 0
        reader = AXIReadPair(axi, in_buffered, out_buffered, align_address,
                             use_cache=use_cache, use_lock=use_lock,
                             use_size=use_size, use_user=use_user)

        requests = []

        async def producer(sim):
            for _ in range(5):
                addr_req = gen_rand_read(data_width=data_width,
                                         addr_width=addr_width,
                                         id_width=id_width,
                                         len_width=len_width,
                                         cache_width=cache_width,
                                         lock_width=lock_width,
                                         user_width=user_width)
                requests.extend(decode_read(data_width=data_width,
                                            align_address=align_address,
                                            use_cache=use_cache, use_lock=use_lock,
                                            use_size=use_size, use_user=use_user,
                                            **addr_req))
                assert (await reader.request.call(sim, **addr_req)) is not None

        def check_reply(reply):
            assert reply is not None
            expected = requests.pop(0)
            assert struct_to_dict(reply) == expected

        async def consumer(sim):
            check_reply(await reader.get_request.call(sim))
            while requests:
                check_reply(await reader.get_request.call_try(sim))

        with self.run_simulation(reader) as sim:
            sim.add_testbench(producer)
            sim.add_testbench(consumer)

    @pytest.mark.parametrize("in_buffered", [False, True])
    @pytest.mark.parametrize("out_buffered", [False, True])
    @pytest.mark.parametrize("align_address", [False, True])
    @pytest.mark.parametrize("AXI", [AXI3, AXI4])
    @pytest.mark.parametrize("const_id", [None, 5])
    @pytest.mark.parametrize("const_size", [None, 1])
    @pytest.mark.parametrize("const_len", [None, 0, 2])
    @pytest.mark.parametrize("const_burst", [None, 0, 1])
    def test_read_request_const(self, in_buffered, out_buffered, align_address,
                                const_id, const_size, const_len,
                                const_burst, AXI):
        data_width = 32
        addr_width = 32
        id_width = 3
        axi = AXI(data_width, addr_width, id_width).create()
        len_width = len(axi.ARLEN)
        reader = AXIReadPair(axi, in_buffered, out_buffered, align_address,
                             const_id=const_id, const_size=const_size,
                             const_len=const_len, const_burst=const_burst)

        requests = []

        async def producer(sim):
            for _ in range(2):
                addr_req = gen_rand_read(data_width=data_width,
                                         addr_width=addr_width,
                                         id_width=id_width,
                                         len_width=len_width,
                                         id=const_id,
                                         size=const_size,
                                         len=const_len,
                                         burst=const_burst)
                requests.extend(decode_read(data_width=data_width,
                                            align_address=align_address,
                                            **addr_req))

                if const_id is not None:
                    del addr_req['id']
                if const_size is not None:
                    del addr_req['size']
                if const_len is not None:
                    del addr_req['len']
                if const_burst is not None:
                    del addr_req['burst']
                assert (await reader.request.call(sim, **addr_req)) is not None

        def check_reply(reply):
            assert reply is not None
            expected = requests.pop(0)
            assert struct_to_dict(reply) == expected

        async def consumer(sim):
            check_reply(await reader.get_request.call(sim))
            while requests:
                check_reply(await reader.get_request.call_try(sim))

        with self.run_simulation(reader) as sim:
            sim.add_testbench(producer)
            sim.add_testbench(consumer)

    @pytest.mark.parametrize("in_buffered", [False, True])
    @pytest.mark.parametrize("out_buffered", [False, True])
    @pytest.mark.parametrize("align_address", [False, True])
    @pytest.mark.parametrize("AXI", [AXI3, AXI4])
    @pytest.mark.parametrize("maxwait", [2, 6])
    def test_read_random(self, in_buffered, out_buffered, align_address, AXI, maxwait):
        data_width = 32
        addr_width = 32
        id_width = 6
        axi = AXI(data_width, addr_width, id_width).create()
        len_width = len(axi.ARLEN)
        reader = AXIReadPair(axi, in_buffered, out_buffered, align_address)

        addr_reqs = []
        decoded_reqs = []

        for _ in range(100):
            addr_req = gen_rand_read(data_width=data_width,
                                     addr_width=addr_width,
                                     id_width=id_width,
                                     len_width=len_width)
            addr_reqs.append(addr_req)
            decoded_reqs.extend(decode_read(data_width=data_width,
                                            align_address=align_address,
                                            **addr_req))

        async def rand_wait(sim):
            for _ in range(random.randint(0, maxwait)):
                await sim.tick()

        async def addr_producer(sim):
            while addr_reqs:
                addr_req = addr_reqs.pop(0)
                await rand_wait(sim)
                await reader.request.call(sim, **addr_req)

        def check_reply(reply):
            assert reply is not None
            expected = decoded_reqs.pop(0)
            assert struct_to_dict(reply) == expected

        async def consumer(sim):
            while decoded_reqs:
                check_reply(await reader.get_request.call(sim))

        with self.run_simulation(reader) as sim:
            sim.add_testbench(addr_producer)
            sim.add_testbench(consumer)
