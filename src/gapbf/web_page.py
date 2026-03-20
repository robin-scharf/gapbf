from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_PLACEHOLDER_NAMES = (
    "settings_panel",
    "grid_panel",
    "log_panel",
    "controls_panel",
)


@lru_cache(maxsize=1)
def render_index_html(static_dir: str) -> str:
    resolved_static_dir = Path(static_dir)
    shell = (resolved_static_dir / "index.html").read_text(encoding="utf-8")
    components_dir = resolved_static_dir / "components"
    rendered = shell

    for placeholder_name in _PLACEHOLDER_NAMES:
        component_path = components_dir / f"{placeholder_name}.html"
        rendered = rendered.replace(
            f"{{{{ {placeholder_name} }}}}",
            component_path.read_text(encoding="utf-8").strip(),
        )

    return rendered