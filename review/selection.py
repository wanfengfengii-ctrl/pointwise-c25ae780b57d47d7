from collections.abc import Iterable

from archive.readback import WindowSummary
from inspection.grading import WindowGrade


def select_windows(summaries: Iterable[WindowSummary], dark_only: bool) -> list[WindowSummary]:
    selected = (
        summary for summary in summaries if not dark_only or summary.grade == WindowGrade.DARK
    )
    return sorted(selected, key=lambda summary: (summary.header.trigger_slot, summary.capture_id))
