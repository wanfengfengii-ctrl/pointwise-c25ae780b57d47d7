from collections.abc import Mapping
from dataclasses import dataclass

from source.frame import GrayFrame, decode_gray_frame
from source.origin import require_source_label


class PacketFormatError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PacketHeader:
    camera: str
    packet_id: str
    trigger_slot: int
    first_slot: int
    last_slot: int

    def __post_init__(self) -> None:
        try:
            require_source_label(self.camera, 'packet camera')
            require_source_label(self.packet_id, 'packet identifier')
        except ValueError as exc:
            raise PacketFormatError(str(exc)) from exc
        for value in (self.trigger_slot, self.first_slot, self.last_slot):
            if type(value) is not int or value < 0:
                raise PacketFormatError('packet slots must be nonnegative integers')


@dataclass(frozen=True, slots=True)
class SourcePacket:
    header: PacketHeader
    frames: tuple[GrayFrame, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.header, PacketHeader):
            raise PacketFormatError('packet requires a header')
        if not isinstance(self.frames, tuple) or any(
            not isinstance(frame, GrayFrame) for frame in self.frames
        ):
            raise PacketFormatError('packet requires an immutable sequence of gray frames')


def decode_packet(record: Mapping[str, object]) -> SourcePacket:
    fields = {'camera', 'packet_id', 'trigger_slot', 'first_slot', 'last_slot', 'frames'}
    if not isinstance(record, Mapping) or set(record) != fields:
        raise PacketFormatError('packet record requires camera, packet_id, slot bounds and frames')
    raw_frames = record['frames']
    if not isinstance(raw_frames, list):
        raise PacketFormatError('packet frames must be a JSON array')
    header = PacketHeader(
        record['camera'], record['packet_id'], record['trigger_slot'],
        record['first_slot'], record['last_slot']
    )
    frames = []
    for index, raw in enumerate(raw_frames):
        try:
            frames.append(decode_gray_frame(raw))
        except ValueError as exc:
            raise PacketFormatError(f'packet {header.packet_id!r}, frame {index}: {exc}') from exc
    return SourcePacket(header, tuple(frames))
