"""A captured frame. Timestamps are kept apart on purpose (docs/data-flow.md, ADR-010)."""

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import numpy.typing as npt

Image = npt.NDArray[np.uint8]


@dataclass(frozen=True, slots=True)
class Frame:
    image: Image  # HxWx3 BGR; never mutated after capture
    frame_id: int  # monotonic within one camera session run
    source_ts_ms: float  # source time: video position (file/mock) or capture monotonic (live)
    captured_at: datetime  # wall clock UTC
    # True for the first frame after the source jumped back (file loop): trackers must reset.
    discontinuity: bool = False

    @property
    def size(self) -> tuple[int, int]:
        height, width = self.image.shape[:2]
        return width, height
