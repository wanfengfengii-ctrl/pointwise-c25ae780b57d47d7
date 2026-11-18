from collections.abc import Iterable
from dataclasses import dataclass

from camera.calibration import MAX_GRAY
from source.frame import GrayFrame


@dataclass(frozen=True, slots=True)
class LuminanceTotals:
    gray_sum: int
    pixel_count: int

    def __post_init__(self) -> None:
        if type(self.gray_sum) is not int or type(self.pixel_count) is not int:
            raise ValueError('luminance totals must be integers')
        if self.pixel_count < 0 or not 0 <= self.gray_sum <= MAX_GRAY * self.pixel_count:
            raise ValueError('luminance total is outside the range for its pixel count')


def accumulate_luminance(frames: Iterable[GrayFrame]) -> LuminanceTotals:
    gray_sum = 0
    pixel_count = 0
    for frame in frames:
        gray_sum += sum(frame.payload)
        pixel_count += len(frame.payload)
    return LuminanceTotals(gray_sum, pixel_count)
