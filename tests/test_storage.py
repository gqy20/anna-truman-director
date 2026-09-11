import pytest
from conftest import FakeStorage
from executa_sdk import StorageError

from truman_director.storage import KEY, load, save


async def test_save_then_load_roundtrip():
    storage = FakeStorage()
    await save(storage, {"run_id": "r1", "tick": 3})
    loaded = await load(storage)
    assert loaded == {"run_id": "r1", "tick": 3}


async def test_load_missing_returns_none():
    storage = FakeStorage()
    assert await load(storage) is None


async def test_load_tolerates_legacy_dev_backend_without_exists_flag():
    """Dev harness legacy backend answers bare {value} with no `exists`.

    A non-None value must still count as a hit; a bare None stays a miss.
    """

    class LegacyStorage:
        def __init__(self, value):
            self.value = value

        async def get(self, key, *, scope):
            return {"value": self.value}

        async def set(self, key, value, *, scope):
            self.value = value

    storage = LegacyStorage({"run_id": "r2"})
    assert await load(storage) == {"run_id": "r2"}

    empty = LegacyStorage(None)
    assert await load(empty) is None


async def test_uses_documented_key():
    storage = FakeStorage()
    await save(storage, {"x": 1})
    assert KEY in storage.data


@pytest.mark.parametrize("operation", ["read", "write"])
async def test_owner_contract_error_is_not_missing_data_or_scope_fallback(operation):
    failure = StorageError(-32029, "scope=tool requires owner_id")
    calls = []

    class RejectedStorage:
        async def get(self, key, *, scope):
            calls.append(("get", key, scope))
            raise failure

        async def set(self, key, value, *, scope):
            calls.append(("set", key, scope))
            raise failure

    storage = RejectedStorage()
    with pytest.raises(StorageError) as caught:
        if operation == "read":
            await load(storage)
        else:
            await save(storage, {"run_id": "test"})
    assert caught.value is failure
    assert len(calls) == 1
    assert calls[0][2] == "tool"
