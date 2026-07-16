from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def render_index_html(static_dir: str) -> str:
    """Return the SPA shell. The UI is a Preact app mounted into #app; there is
    no server-side component assembly."""
    return (Path(static_dir) / "index.html").read_text(encoding="utf-8")
