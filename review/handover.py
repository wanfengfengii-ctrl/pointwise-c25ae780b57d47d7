from dataclasses import dataclass

from archive.window_store import WindowStore
from camera.profiles import ProfileRevision
from inspection.grading import WindowGrade
from inspection.luminance import LuminanceTotals
from review.query import ReviewQuery
from review.selection import select_windows
from review.verify import verify_window
from source.origin import FrameOrigin


@dataclass(frozen=True, slots=True)
class HandoverEntry:
    session: str
    capture_id: int
    packet_id: str
    trigger_slot: int
    first_slot: int
    last_slot: int
    profile: ProfileRevision
    totals: LuminanceTotals
    grade: WindowGrade
    origins: tuple[tuple[int, FrameOrigin], ...]


class HandoverService:
    def __init__(self, windows: WindowStore) -> None:
        self._windows = windows

    def handover(self, session: str, dark_only: bool = False) -> list[HandoverEntry]:
        with self._windows.read_snapshot() as reader:
            query = ReviewQuery(reader, session)
            selected = select_windows(query.summaries(), dark_only)
            report = []
            for summary in selected:
                verified = verify_window(query.read_selected(summary))
                header = summary.header
                report.append(HandoverEntry(
                    session, summary.capture_id, header.packet_id, header.trigger_slot,
                    header.first_slot, header.last_slot, summary.profile,
                    verified.totals, verified.grade, verified.origins,
                ))
            return report
