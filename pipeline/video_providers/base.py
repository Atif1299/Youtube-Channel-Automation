from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pipeline.models import Scene


class VideoProvider(ABC):
    name: str

    @abstractmethod
    def generate_clip(self, scene: Scene, work_dir: Path) -> Path | None:
        pass
