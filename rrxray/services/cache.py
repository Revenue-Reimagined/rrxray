"""DiskCache: live | replay-only | refresh modes. Doubles as test-fixture mechanism."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal


class CacheMissError(Exception):
    """Raised in replay-only mode when no cached entry exists for the request."""


CacheMode = Literal["live", "replay-only", "refresh"]


class DiskCache:
    def __init__(self, dir: Path, mode: CacheMode = "live"):
        self.dir = Path(dir)
        self.mode = mode
        self.dir.mkdir(parents=True, exist_ok=True)

    def _key(self, method_name: str, args: dict[str, Any]) -> str:
        canonical = json.dumps({"m": method_name, "a": args}, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def _path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def _read(self, key: str) -> Any | None:
        p = self._path(key)
        if not p.exists():
            return None
        payload = json.loads(p.read_text())
        return payload["response"]

    def _write(self, key: str, response: Any) -> None:
        p = self._path(key)
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "response": response,
        }
        p.write_text(json.dumps(payload, indent=2, default=str))

    async def get_or_call(
        self,
        method_name: str,
        args: dict[str, Any],
        upstream: Callable[[], Awaitable[Any]],
    ) -> Any:
        key = self._key(method_name, args)

        if self.mode == "refresh":
            response = await upstream()
            self._write(key, response)
            return response

        cached = self._read(key)
        if cached is not None:
            return cached

        if self.mode == "replay-only":
            raise CacheMissError(
                f"No cached entry for method='{method_name}' args={args} (key={key}). "
                f"Bootstrap by running with mode='live' or 'refresh'."
            )

        # mode == "live": call upstream, write, return
        response = await upstream()
        self._write(key, response)
        return response
