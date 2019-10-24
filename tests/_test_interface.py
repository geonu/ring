
import asyncio
import pytest
import ring.func.sync
from ring.func.base import BaseUserInterface, NotFound, factory


class DoubleCacheUserInterface(BaseUserInterface):

    @asyncio.coroutine
    def execute(self, wire, **kwargs):
        result = yield from wire.__func__(**kwargs)
        return result

    def key2(self, wire, **kwargs):
        return wire.key(**kwargs) + ':back'

    @asyncio.coroutine
    def get(self, wire, **kwargs):
        key1 = wire.key(**kwargs)
        key2 = wire.key2(**kwargs)

        result = ...
        for key in [key1, key2]:
            try:
                result = yield from wire._rope.storage.get(key)
            except NotFound:
                continue
            else:
                break
        if result is ...:
            result = wire._rope.miss_value
        return result

    @asyncio.coroutine
    def update(self, wire, **kwargs):
        key = wire.key(**kwargs)
        key2 = wire.key2(**kwargs)
        result = yield from wire.execute(**kwargs)
        yield from wire._rope.storage.set(key, result)
        yield from wire._rope.storage.set(key2, result, None)
        return result

    @asyncio.coroutine
    def get_or_update(self, wire, **kwargs):
        key = wire.key(**kwargs)
        key2 = wire.key2(**kwargs)
        try:
            result = yield from wire._rope.storage.get(key)
        except NotFound:
            try:
                result = yield from wire.execute(**kwargs)
            except Exception:
                try:
                    result = yield from wire._rope.storage.get(key2)
                except NotFound:
                    pass
                else:
                    return result
                raise
            else:
                yield from wire._rope.storage.set(key, result)
                yield from wire._rope.storage.set(key2, result, None)
        return result

    @asyncio.coroutine
    def delete(self, wire, **kwargs):
        key = wire.key(**kwargs)
        key2 = wire.key2(**kwargs)
        yield from wire._rope.storage.delete(key)
        yield from wire._rope.storage.delete(key2)

    @asyncio.coroutine
    def touch(self, wire, **kwargs):
        key = wire.key(**kwargs)
        key2 = wire.key(**kwargs)
        yield from wire._rope.storage.touch(key)
        yield from wire._rope.storage.touch(key2)


def doublecache(
        client, key_prefix, expire=0, coder=None,
        user_interface=DoubleCacheUserInterface):
    from ring.func.sync import ExpirableDictStorage
    from ring.func.asyncio import convert_storage

    return factory(
        client, key_prefix=key_prefix, on_manufactured=None,
        user_interface=user_interface,
        storage_class=convert_storage(ExpirableDictStorage),
        miss_value=None, expire_default=expire, coder=coder)


@pytest.mark.asyncio
def test_x():
    storage = {}

    f_value = 0

    @doublecache(storage, key_prefix='f', expire=10)
    @asyncio.coroutine
    def f():
        nonlocal f_value
        if f_value < 0:
            raise Exception
        return f_value

    assert storage == {}
    assert 0 == (yield from f())
    assert 'f' in storage
    assert 'f:back' in storage
    assert 0 == (yield from f.get())

    del storage['f']
    assert 0 == (yield from f.get())
    assert len(storage) == 1

    f_value = -1

    assert 0 == (yield from f.get())
    assert len(storage) == 1
    assert 0 == (yield from f())
    assert len(storage) == 1

    yield from f.delete()
    assert storage == {}

    assert None is (yield from f.get())

    f_value = 2
    yield from f.update()
    assert 2 == (yield from f())

    storage['f'] = storage['f'][0], 1
    assert 1 == (yield from f.get())
    assert 1 == (yield from f())
    del storage['f']
    f_value = 3
    assert 2 == (yield from f.get())
    assert 3 == (yield from f())
    assert 3 == (yield from f.get())


def test_coder_func():

    storage = {}

    @ring.dict(storage)
    def f(a):
        return a

    encoded_value = f.encode('value')
    decoded_value = f.decode(encoded_value)
    assert encoded_value == decoded_value

    assert f('10') == '10'
    raw_value = storage.get(f.key('10'))  # raw value
    value = f.decode(raw_value)
    assert f.get('10') == value


def test_coder_method():

    storage = {}

    class Object(object):

        def __init__(self, **kwargs):
            self._data = kwargs

        def __getattr__(self, key):
            if key in self._data:
                return self._data[key]
            return getattr(super(Object, self), key)

    class User(Object):
        def __ring_key__(self):
            return 'User{self.user_id}'.format(self=self)

        @ring.dict(storage)
        def data(self):
            return self._data.copy()

    u1 = User(user_id=42, name='User 1')
    u1.data()

    encoded_value = u1.data.encode(u1.data.key())
    decoded_value = u1.data.decode(encoded_value)
    assert encoded_value == decoded_value

    raw_value = storage.get(u1.data.key())
    value = u1.data.decode(raw_value)
    assert u1.data.get() == value
