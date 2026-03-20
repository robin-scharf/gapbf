from __future__ import annotations

import hashlib
import json

from .Config import Config


class DatabaseFingerprintMixin:
    @staticmethod
    def attempt_hash_for(device_id: str, grid_size: int, attempt: str) -> str:
        payload = json.dumps(
            {
                "attempt": str(attempt),
                "device_id": str(device_id),
                "grid_size": int(grid_size),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _config_snapshot(self, config: Config) -> dict[str, object]:
        snapshot = config.model_dump()
        snapshot.pop("total_paths", None)
        snapshot.pop("config_file_path", None)
        return snapshot

    def config_fingerprint(self, config: Config) -> str:
        payload = json.dumps(self._config_snapshot(config), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()