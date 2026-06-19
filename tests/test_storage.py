from conftest import FakeStorage

from truman_director.storage import KEY, load, save


async def test_save_then_load_roundtrip():
    storage = FakeStorage()
    await save(storage, {"run_id": "r1", "tick": 3})
    loaded = await load(storage)
    assert loaded == {"run_id": "r1", "tick": 3}


async def test_load_missing_returns_none():
    storage = FakeStorage()
    assert await load(storage) is None


async def test_uses_documented_key():
    storage = FakeStorage()
    await save(storage, {"x": 1})
    assert KEY in storage.data
