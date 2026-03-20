from __future__ import annotations

from typing import Any

from .Config import Config
from .web_models import config_from_payload, config_meta, save_config_to_path, serialize_config


class WebRunControllerConfigMixin:
    def load_config(self, path: str) -> dict[str, Any]:
        config = Config.load_config(path)
        return {"config": serialize_config(config), "meta": config_meta(config.grid_size)}

    def validate_config(self, config_data: dict[str, Any]) -> dict[str, Any]:
        try:
            config = config_from_payload(config_data)
        except Exception as error:
            return {"valid": False, "errors": [str(error)]}
        return {
            "valid": True,
            "errors": [],
            "config": serialize_config(config),
            "meta": config_meta(config.grid_size),
        }

    def save_config(self, path: str, config_data: dict[str, Any]) -> dict[str, Any]:
        return save_config_to_path(path, config_data)