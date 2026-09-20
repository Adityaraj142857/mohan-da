"""Load and render messages.yaml (SPEC 8.1, Appendix C)."""

from __future__ import annotations

from pathlib import Path

import yaml


class Templates:
    def __init__(self, path: str | Path):
        self._data: dict[str, str] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}

    def render(self, key: str, **kwargs) -> str:
        template = self._data.get(key, "")
        try:
            return template.format(**kwargs)
        except KeyError:
            return template
