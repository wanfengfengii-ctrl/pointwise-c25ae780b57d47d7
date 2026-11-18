import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from archive.evidence import frame_evidence_digest, window_header_digest
from archive.frame_store import insert_window_frames
from archive.profile_store import ProfileStore
from archive.readback import ArchiveVerificationError, ArchivedWindow, WindowReader
from archive.schema import encode_natural
from archive.session_catalog import find_capture_by_packet, find_session_binding
from camera.sessions import SessionBindingError
from inspection.admission import PreparedWindow
from inspection.grading import WindowGrade
from inspection.luminance import LuminanceTotals


@dataclass(frozen=True, slots=True)
class CaptureReceipt:
    capture_id: int
    totals: LuminanceTotals
    grade: WindowGrade


class PacketConflictError(ValueError):
    pass


class WindowStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._profiles = ProfileStore(connection)

    @contextmanager
    def _transaction(self, begin: str) -> Iterator[None]:
        connection = self._connection
        connection.execute(begin)
        try:
            yield
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    def _require_fixed_binding(self, window: PreparedWindow) -> None:
        profile = window.binding.profile
        key = (profile.key.camera, profile.key.revision)
        if find_session_binding(self._connection, window.binding.session) != key:
            raise SessionBindingError('prepared window does not match the archive session binding')
        stored = self._profiles.find_profile(*key)
        if stored != (profile.spec.width, profile.spec.height, profile.threshold):
            raise SessionBindingError('prepared window does not match the fixed archive profile')

    def _retry(self, window: PreparedWindow, capture_id: int) -> CaptureReceipt:
        session = window.binding.session
        existing = WindowReader(self._connection).read_window(session, capture_id)
        if existing is None:
            raise ArchiveVerificationError(f'catalogued window {session!r}/{capture_id} is missing')
        if existing.packet != window.packet:
            raise PacketConflictError(f'packet {window.packet.header.packet_id!r} has different content')
        summary = existing.summary
        if (summary.profile, summary.totals, summary.grade) != (
            window.binding.profile, window.totals, window.grade
        ):
            raise ArchiveVerificationError(f'window {session!r}/{capture_id} has inconsistent fixed results')
        return CaptureReceipt(capture_id, summary.totals, summary.grade)

    def _insert(self, window: PreparedWindow) -> CaptureReceipt:
        connection = self._connection
        session = window.binding.session
        profile = window.binding.profile
        header = window.packet.header
        frames_digest = frame_evidence_digest(window.packet.frames)
        cursor = connection.execute(
            '''INSERT INTO windows (
                   session, packet_id, camera, revision, width, height, threshold,
                   trigger_slot, first_slot, last_slot, gray_sum, pixel_count,
                   grade, frames_digest, header_digest
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '')''',
            (
                session, header.packet_id, header.camera, profile.key.revision,
                encode_natural(profile.spec.width), encode_natural(profile.spec.height),
                profile.threshold, encode_natural(header.trigger_slot),
                encode_natural(header.first_slot), encode_natural(header.last_slot),
                encode_natural(window.totals.gray_sum), encode_natural(window.totals.pixel_count),
                window.grade.value, frames_digest,
            ),
        )
        capture_id = cursor.lastrowid
        digest = window_header_digest(
            session, capture_id, header, profile, window.totals, window.grade, frames_digest
        )
        connection.execute(
            'UPDATE windows SET header_digest = ? WHERE capture_id = ?', (digest, capture_id)
        )
        insert_window_frames(connection, capture_id, window.packet.frames)
        return CaptureReceipt(capture_id, window.totals, window.grade)

    def publish_window(self, window: PreparedWindow) -> CaptureReceipt:
        with self._transaction('BEGIN IMMEDIATE'):
            self._require_fixed_binding(window)
            capture_id = find_capture_by_packet(
                self._connection, window.binding.session, window.packet.header.packet_id
            )
            if capture_id is None:
                return self._insert(window)
            return self._retry(window, capture_id)

    @contextmanager
    def read_snapshot(self) -> Iterator[WindowReader]:
        with self._transaction('BEGIN'):
            yield WindowReader(self._connection)

    def read_window(self, session: str, capture_id: int) -> ArchivedWindow | None:
        with self.read_snapshot() as reader:
            return reader.read_window(session, capture_id)
