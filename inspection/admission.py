from dataclasses import dataclass, field

from camera.sessions import SessionBinding
from inspection.dense_slots import require_dense_slots
from inspection.grading import WindowGrade, grade_window
from inspection.luminance import LuminanceTotals, accumulate_luminance
from source.frame import require_frame_layout
from source.origin import require_origin_camera
from source.packet import SourcePacket


class AdmissionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PreparedWindow:
    binding: SessionBinding
    packet: SourcePacket
    totals: LuminanceTotals = field(init=False)
    grade: WindowGrade = field(init=False)

    def __post_init__(self) -> None:
        profile = self.binding.profile
        camera = self.packet.header.camera
        if camera != profile.key.camera:
            raise AdmissionError(f'packet camera {camera!r} does not match session camera')
        try:
            require_dense_slots(self.packet)
            for frame in self.packet.frames:
                require_frame_layout(frame, profile.spec)
                require_origin_camera(frame.origin, camera)
            totals = accumulate_luminance(self.packet.frames)
            grade = grade_window(totals, profile.threshold)
        except ValueError as exc:
            raise AdmissionError(f'packet {self.packet.header.packet_id!r}: {exc}') from exc
        object.__setattr__(self, 'totals', totals)
        object.__setattr__(self, 'grade', grade)


def prepare_dense_window(binding: SessionBinding, packet: SourcePacket) -> PreparedWindow:
    return PreparedWindow(binding, packet)
