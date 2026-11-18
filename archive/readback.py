import sqlite3
from dataclasses import dataclass

from archive.evidence import frame_evidence_digest, window_header_digest
from archive.frame_store import load_window_frames
from archive.schema import decode_natural
from archive.session_catalog import find_session_binding, list_session_capture_ids
from camera.profiles import ProfileKey, ProfileRevision
from camera.sessions import SessionBindingError
from camera.spec import CameraSpec
from inspection.dense_slots import require_dense_slots
from inspection.grading import WindowGrade
from inspection.luminance import LuminanceTotals
from source.frame import GrayFrame, require_frame_layout
from source.origin import require_origin_camera
from source.packet import PacketHeader, SourcePacket


class ArchiveVerificationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WindowSummary:
    session: str
    capture_id: int
    header: PacketHeader
    profile: ProfileRevision
    totals: LuminanceTotals
    grade: WindowGrade
    frames_digest: str


@dataclass(frozen=True, slots=True)
class ArchivedWindow:
    summary: WindowSummary
    packet: SourcePacket

    @property
    def frames(self) -> tuple[GrayFrame, ...]:
        return self.packet.frames


def _decode_summary(row: sqlite3.Row) -> WindowSummary:
    header = PacketHeader(
        row['camera'], row['packet_id'], decode_natural(row['trigger_slot']),
        decode_natural(row['first_slot']), decode_natural(row['last_slot']),
    )
    profile = ProfileRevision(
        ProfileKey(row['camera'], row['revision']),
        CameraSpec(decode_natural(row['width']), decode_natural(row['height'])),
        row['threshold'],
    )
    totals = LuminanceTotals(decode_natural(row['gray_sum']), decode_natural(row['pixel_count']))
    grade = WindowGrade(row['grade'])
    if not header.first_slot <= header.trigger_slot <= header.last_slot:
        raise ValueError('invalid fixed slot interval')
    expected_count = (header.last_slot - header.first_slot + 1) * profile.spec.pixel_count
    if totals.pixel_count != expected_count:
        raise ValueError('fixed pixel count disagrees with the slot interval and frame shape')
    expected_digest = window_header_digest(
        row['session'], row['capture_id'], header, profile, totals, grade, row['frames_digest'],
    )
    if expected_digest != row['header_digest']:
        raise ValueError('fixed window header digest mismatch')
    return WindowSummary(
        row['session'], row['capture_id'], header, profile, totals, grade, row['frames_digest']
    )


class WindowReader:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def _read_summary(self, session: str, capture_id: int) -> WindowSummary | None:
        if type(capture_id) is not int or not 0 < capture_id < 1 << 63:
            return None
        row = self._connection.execute(
            'SELECT * FROM windows WHERE session = ? AND capture_id = ?', (session, capture_id)
        ).fetchone()
        if row is None:
            return None
        try:
            return _decode_summary(row)
        except (ValueError, TypeError) as exc:
            raise ArchiveVerificationError(f'window {session!r}/{capture_id}: {exc}') from exc

    def list_summaries(self, session: str) -> tuple[WindowSummary, ...]:
        if find_session_binding(self._connection, session) is None:
            raise SessionBindingError(f'unknown session {session!r}')
        summaries = []
        for capture_id in list_session_capture_ids(self._connection, session):
            summary = self._read_summary(session, capture_id)
            if summary is None:
                raise ArchiveVerificationError(f'catalogued window {session!r}/{capture_id} is missing')
            summaries.append(summary)
        return tuple(summaries)

    def read_window(self, session: str, capture_id: int) -> ArchivedWindow | None:
        summary = self._read_summary(session, capture_id)
        if summary is None:
            return None
        try:
            frames = load_window_frames(self._connection, capture_id)
            packet = SourcePacket(summary.header, frames)
            require_dense_slots(packet)
            for frame in frames:
                require_frame_layout(frame, summary.profile.spec)
                require_origin_camera(frame.origin, summary.header.camera)
            if frame_evidence_digest(frames) != summary.frames_digest:
                raise ValueError('frame evidence digest mismatch')
        except (ValueError, TypeError) as exc:
            raise ArchiveVerificationError(f'window {session!r}/{capture_id}: {exc}') from exc
        return ArchivedWindow(summary, packet)
