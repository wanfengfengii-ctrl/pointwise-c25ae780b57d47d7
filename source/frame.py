import binascii
from collections.abc import Mapping
from dataclasses import dataclass

from camera.spec import CameraSpec, validate_dimensions
from source.origin import FrameOrigin, decode_origin


class FrameLayoutError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GrayFrame:
    slot: int
    width: int
    height: int
    payload: bytes
    origin: FrameOrigin

    def __post_init__(self) -> None:
        if type(self.slot) is not int or self.slot < 0:
            raise FrameLayoutError('frame slot must be a nonnegative integer')
        try:
            validate_dimensions(self.width, self.height)
        except ValueError as exc:
            raise FrameLayoutError(str(exc)) from exc
        if not isinstance(self.payload, bytes) or not isinstance(self.origin, FrameOrigin):
            raise FrameLayoutError('a frame requires immutable gray bytes and a frame origin')


def decode_gray_frame(record: Mapping[str, object]) -> GrayFrame:
    fields = {'slot', 'width', 'height', 'gray_hex', 'origin'}
    if not isinstance(record, Mapping) or set(record) != fields:
        raise FrameLayoutError('frame record requires slot, width, height, gray_hex and origin')
    gray_hex = record['gray_hex']
    if not isinstance(gray_hex, str):
        raise FrameLayoutError('gray_hex must be a hexadecimal string')
    try:
        payload = binascii.unhexlify(gray_hex)
    except (ValueError, binascii.Error) as exc:
        raise FrameLayoutError('gray_hex must contain pairs of hexadecimal digits') from exc
    return GrayFrame(
        record['slot'], record['width'], record['height'], payload, decode_origin(record['origin'])
    )


def require_frame_layout(frame: GrayFrame, spec: CameraSpec) -> None:
    if (frame.width, frame.height) != (spec.width, spec.height):
        raise FrameLayoutError(
            f'slot {frame.slot} has shape {frame.width}×{frame.height}, '
            f'expected {spec.width}×{spec.height}'
        )
    if len(frame.payload) != spec.pixel_count:
        raise FrameLayoutError(
            f'slot {frame.slot} has {len(frame.payload)} bytes, expected {spec.pixel_count}'
        )
