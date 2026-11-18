from collections.abc import Iterable

from archive.window_store import CaptureReceipt, WindowStore
from camera.sessions import SessionRegistry
from inspection.admission import prepare_dense_window
from source.packet import SourcePacket, decode_packet
from source.tape import iter_packet_records


class ReplayClosedError(RuntimeError):
    pass


class ReplaySource:
    def __init__(self, lines: Iterable[str]) -> None:
        self._records = iter_packet_records(lines)
        self._close_input = getattr(lines, 'close', None)
        self._closed = False
        self._exhausted = False

    def next_packet(self) -> SourcePacket | None:
        if self._closed:
            raise ReplayClosedError('camera source is closed')
        if self._exhausted:
            return None
        try:
            record = next(self._records)
        except StopIteration:
            self._exhausted = True
            return None
        return decode_packet(record)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._records = iter(())
        close_input = self._close_input
        self._close_input = None
        if close_input is not None:
            close_input()

    def __enter__(self) -> 'ReplaySource':
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class PacketCapture:
    def __init__(self, sessions: SessionRegistry, windows: WindowStore) -> None:
        self._sessions = sessions
        self._windows = windows

    def capture_packet(self, session: str, packet: SourcePacket) -> CaptureReceipt:
        binding = self._sessions.get_session(session)
        prepared = prepare_dense_window(binding, packet)
        return self._windows.publish_window(prepared)
