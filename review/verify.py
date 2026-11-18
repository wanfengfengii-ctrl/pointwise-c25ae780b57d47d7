from dataclasses import dataclass

from archive.readback import ArchiveVerificationError, ArchivedWindow
from inspection.dense_slots import require_dense_slots
from inspection.grading import WindowGrade, grade_window
from inspection.luminance import LuminanceTotals, accumulate_luminance
from source.frame import require_frame_layout
from source.origin import FrameOrigin, require_origin_camera


@dataclass(frozen=True, slots=True)
class VerifiedWindow:
    totals: LuminanceTotals
    grade: WindowGrade
    origins: tuple[tuple[int, FrameOrigin], ...]


def verify_window(window: ArchivedWindow) -> VerifiedWindow:
    fixed = window.summary
    try:
        if window.packet.header != fixed.header or fixed.header.camera != fixed.profile.key.camera:
            raise ValueError('packet header disagrees with the fixed profile or summary')
        require_dense_slots(window.packet)
        for frame in window.frames:
            require_frame_layout(frame, fixed.profile.spec)
            require_origin_camera(frame.origin, fixed.profile.key.camera)
        totals = accumulate_luminance(window.frames)
        grade = grade_window(totals, fixed.profile.threshold)
        if totals != fixed.totals or grade != fixed.grade:
            raise ValueError('fixed luminance totals or grade disagree with the original frames')
    except ValueError as exc:
        raise ArchiveVerificationError(f'window {fixed.session!r}/{fixed.capture_id}: {exc}') from exc
    return VerifiedWindow(totals, grade, tuple((frame.slot, frame.origin) for frame in window.frames))
