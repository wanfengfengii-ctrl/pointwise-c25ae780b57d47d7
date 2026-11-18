import json
import tempfile
import unittest
from collections.abc import Iterable, Iterator
from pathlib import Path

from source.frame import GrayFrame
from source.origin import FrameOrigin
from source.packet import PacketHeader, SourcePacket
from station import Station


class StationCase(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix='strip-station-test-')
        self.addCleanup(directory.cleanup)
        self.database = Path(directory.name) / 'archive.sqlite3'
        self.station = self.open_station()

    def open_station(self) -> Station:
        station = Station(self.database)
        self.addCleanup(station.close)
        return station

    def bind(
        self, session: str = 'A', camera: str = 'C1', revision: str = 'R1',
        width: int = 1, height: int = 1, threshold: int = 20,
    ):
        key = self.station.profiles.register_profile(camera, revision, width, height, threshold)
        return self.station.sessions.open_session(session, key)


def packet(
    packet_id: str, payloads: Iterable[bytes], *, camera: str = 'C1', first: int = 4,
    last: int | None = None, trigger: int | None = None, width: int = 1, height: int = 1,
    slots: Iterable[int] | None = None, positions: Iterable[int] | None = None,
) -> SourcePacket:
    values = tuple(payloads)
    if last is None:
        last = first + len(values) - 1
    if trigger is None:
        trigger = first
    if slots is None:
        slots = range(first, first + len(values))
    if positions is None:
        positions = range(100, 100 + len(values))
    header = PacketHeader(camera, packet_id, trigger, first, last)
    frames = tuple(
        GrayFrame(slot, width, height, payload, FrameOrigin(camera, 'head-left', position))
        for slot, payload, position in zip(slots, values, positions, strict=True)
    )
    return SourcePacket(header, frames)


def tape_record(source: SourcePacket) -> dict[str, object]:
    header = source.header
    return {
        'camera': header.camera, 'packet_id': header.packet_id,
        'trigger_slot': header.trigger_slot, 'first_slot': header.first_slot,
        'last_slot': header.last_slot,
        'frames': [
            {'slot': frame.slot, 'width': frame.width, 'height': frame.height,
             'gray_hex': frame.payload.hex(), 'origin': {
                 'camera': frame.origin.camera, 'device': frame.origin.device,
                 'position': frame.origin.position,
             }} for frame in source.frames
        ],
    }


def tape_line(source: SourcePacket) -> str:
    return json.dumps(tape_record(source))


class SinglePassTape:
    def __init__(self, lines: Iterable[str]) -> None:
        self._lines = iter(lines)
        self._started = False
        self.closed = False
        self.read_count = 0

    def __iter__(self) -> Iterator[str]:
        if self._started:
            raise AssertionError('replay tape was opened twice')
        self._started = True
        return self._read_lines()

    def _read_lines(self) -> Iterator[str]:
        for line in self._lines:
            if self.closed:
                raise AssertionError('read after closing the tape')
            self.read_count += 1
            yield line

    def close(self) -> None:
        self.closed = True
