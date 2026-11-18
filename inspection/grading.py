from enum import Enum

from camera.calibration import threshold_total
from inspection.luminance import LuminanceTotals


class WindowGrade(str, Enum):
    DARK = 'dark'
    PASS = 'pass'


def grade_window(totals: LuminanceTotals, threshold: int) -> WindowGrade:
    if totals.gray_sum < threshold_total(threshold, totals.pixel_count):
        return WindowGrade.DARK
    return WindowGrade.PASS
