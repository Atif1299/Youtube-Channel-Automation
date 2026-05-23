from __future__ import annotations



from abc import ABC, abstractmethod

from pathlib import Path



from pipeline.models import Scene, VisualBible





class VideoProvider(ABC):

    name: str



    @abstractmethod

    def generate_clip(

        self,

        scene: Scene,

        work_dir: Path,

        topic: str = "",

        *,

        visual_bible: VisualBible | None = None,

        prior_scene: Scene | None = None,

    ) -> Path | None:

        pass

