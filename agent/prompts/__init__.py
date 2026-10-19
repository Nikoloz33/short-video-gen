"""Prompt templates live in agent/prompts/*.md with a header `<!-- prompt: name | version: N -->`.

Placeholders use `$name` / `${name}` (string.Template), so JSON braces in prompts need no escaping.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from string import Template

PROMPTS_DIR = Path(__file__).parent
_HEADER = re.compile(r"^<!--\s*prompt:\s*(?P<name>[\w-]+)\s*\|\s*version:\s*(?P<version>\d+)\s*-->\s*\n")


@dataclass(frozen=True)
class Prompt:
    name: str
    version: int
    template: str

    def render(self, **values: object) -> str:
        """Substitutes every placeholder; a missing value is an error (no silent blanks)."""
        return Template(self.template).substitute({k: str(v) for k, v in values.items()})

    @property
    def tag(self) -> str:
        return f"{self.name}@v{self.version}"


@lru_cache(maxsize=64)
def load_prompt(name: str, root: Path = PROMPTS_DIR) -> Prompt:
    path = root / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    m = _HEADER.match(text)
    if not m:
        raise ValueError(f"{path.name}: missing header `<!-- prompt: {name} | version: N -->`")
    if m["name"] != name:
        raise ValueError(f"{path.name}: header names prompt {m['name']!r}")
    return Prompt(name=name, version=int(m["version"]), template=text[m.end() :].strip() + "\n")


def source_block(text: str, label: str = "SOURCE") -> str:
    """Uploaded text is data: wrap it in clearly delimited blocks the model is told never to obey."""
    safe = text.replace("<<<", "‹‹‹").replace(">>>", "›››")
    return f"<<<{label}\n{safe}\n{label}>>>"
