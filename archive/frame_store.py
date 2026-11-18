import sqlite3
from collections.abc import Iterable, Iterator

from archive.schema import decode_natural, encode_natural
from source.frame import GrayFrame
from source.origin import FrameOrigin


def _frame_rows(capture_id: int, frames: Iterable[GrayFrame]) -> Iterator[tuple]:
    for ordinal, frame in enumerate(frames):
        yield (
            capture_id, ordinal, encode_natural(frame.slot),
            encode_natural(frame.width), encode_natural(frame.height), frame.payload,
            frame.origin.camera, frame.origin.device, encode_natural(frame.origin.position),
        )


def insert_window_frames(
    connection: sqlite3.Connection, capture_id: int, frames: Iterable[GrayFrame]
) -> None:
    connection.executemany(
        '''INSERT INTO frames (
               capture_id, ordinal, slot, width, height, payload, origin_camera, device, position
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        _frame_rows(capture_id, frames),
    )


def load_window_frames(connection: sqlite3.Connection, capture_id: int) -> tuple[GrayFrame, ...]:
    rows = connection.execute(
        '''SELECT ordinal, slot, width, height, payload, origin_camera, device, position
           FROM frames WHERE capture_id = ? ORDER BY ordinal''',
        (capture_id,),
    )
    frames = []
    for expected, row in enumerate(rows):
        ordinal, slot, width, height, payload, camera, device, position = row
        if type(ordinal) is not int or ordinal != expected:
            raise ValueError(f'frame ordinal {expected} is missing')
        origin = FrameOrigin(camera, device, decode_natural(position))
        frames.append(
            GrayFrame(decode_natural(slot), decode_natural(width), decode_natural(height), payload, origin)
        )
    return tuple(frames)
