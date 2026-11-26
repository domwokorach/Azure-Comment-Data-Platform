import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAKE = ROOT / "data" / "lake"


@dataclass(frozen=True)
class Source:
    source_system: str
    entity: str
    format: str
    path: str
    primary_key: list
    owner: str
    classification: str
    load_type: str

    @property
    def name(self) -> str:
        return f"{self.source_system}.{self.entity}"


def load_sources(path: Path = ROOT / "config" / "sources.json") -> list[Source]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Source(**s) for s in raw["sources"]]
