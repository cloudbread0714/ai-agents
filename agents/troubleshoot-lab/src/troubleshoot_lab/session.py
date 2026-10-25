"""Local, uncommitted session state: the mission in progress and its current step."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from shared.files import write_text_atomic


@dataclass(frozen=True)
class ActiveMission:
    id: str
    step_index: int


class Session:
    def __init__(self, state_dir: Path):
        self.path = state_dir / "session.json"

    def get(self) -> ActiveMission | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return ActiveMission(id=str(data["id"]), step_index=int(data["step_index"]))
        except (FileNotFoundError, ValueError, KeyError, TypeError):
            return None

    def set(self, mission_id: str, step_index: int) -> None:
        write_text_atomic(self.path, json.dumps({"id": mission_id, "step_index": step_index}))

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
