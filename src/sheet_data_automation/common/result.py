from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RunResult:
    name: str
    exit_code: int
    failures: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def success(self) -> bool:
        return self.exit_code == 0
