"""DiskCache: live, replay-only, refresh modes."""
import json
from pathlib import Path

import pytest

from rrxray.services.cache import CacheMissError, DiskCache


@pytest.fixture
def tmp_cache(tmp_path: Path) -> DiskCache:
    return DiskCache(dir=tmp_path, mode="live")


def test_live_mode_caches_on_first_call(tmp_cache: DiskCache):
    calls = []

    async def upstream():
        calls.append(1)
        return {"value": 42}

    import asyncio
    result1 = asyncio.run(tmp_cache.get_or_call("method", {"arg": "x"}, upstream))
    result2 = asyncio.run(tmp_cache.get_or_call("method", {"arg": "x"}, upstream))

    assert result1 == {"value": 42}
    assert result2 == {"value": 42}
    assert len(calls) == 1


def test_live_mode_different_args_separate_keys(tmp_cache: DiskCache):
    async def upstream_a():
        return {"a": 1}

    async def upstream_b():
        return {"b": 2}

    import asyncio
    a = asyncio.run(tmp_cache.get_or_call("method", {"arg": "a"}, upstream_a))
    b = asyncio.run(tmp_cache.get_or_call("method", {"arg": "b"}, upstream_b))

    assert a == {"a": 1}
    assert b == {"b": 2}


def test_replay_only_returns_cached_value(tmp_path: Path):
    cache = DiskCache(dir=tmp_path, mode="replay-only")
    # Pre-populate the cache file by computing what the key would be
    # Use the live cache to write, then switch modes
    live = DiskCache(dir=tmp_path, mode="live")

    async def upstream():
        return {"v": 1}

    import asyncio
    asyncio.run(live.get_or_call("method", {"arg": "x"}, upstream))

    async def should_not_call():
        raise AssertionError("should not call upstream in replay-only mode")

    result = asyncio.run(cache.get_or_call("method", {"arg": "x"}, should_not_call))
    assert result == {"v": 1}


def test_replay_only_raises_on_miss(tmp_path: Path):
    cache = DiskCache(dir=tmp_path, mode="replay-only")

    async def upstream():
        return {"v": 1}

    import asyncio
    with pytest.raises(CacheMissError) as exc:
        asyncio.run(cache.get_or_call("method", {"arg": "missing"}, upstream))
    assert "method" in str(exc.value)


def test_refresh_mode_overwrites_cache(tmp_path: Path):
    live = DiskCache(dir=tmp_path, mode="live")
    refresh = DiskCache(dir=tmp_path, mode="refresh")

    async def upstream_a():
        return {"v": "first"}

    async def upstream_b():
        return {"v": "second"}

    import asyncio
    asyncio.run(live.get_or_call("method", {"arg": "x"}, upstream_a))
    result = asyncio.run(refresh.get_or_call("method", {"arg": "x"}, upstream_b))
    assert result == {"v": "second"}

    # Live re-read confirms overwrite
    re_read = asyncio.run(live.get_or_call("method", {"arg": "x"}, upstream_a))
    assert re_read == {"v": "second"}


def test_cache_file_format(tmp_path: Path):
    cache = DiskCache(dir=tmp_path, mode="live")

    async def upstream():
        return {"hello": "world"}

    import asyncio
    asyncio.run(cache.get_or_call("foo", {"x": 1}, upstream))

    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text())
    assert "timestamp" in payload
    assert payload["response"] == {"hello": "world"}
