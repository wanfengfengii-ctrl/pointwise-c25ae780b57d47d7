from collections.abc import Mapping
from dataclasses import dataclass


def require_source_label(value: str, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f'{field} must be a nonempty string')
    value.encode('utf-8')


@dataclass(frozen=True, slots=True)
class FrameOrigin:
    camera: str
    device: str
    position: int

    def __post_init__(self) -> None:
        require_source_label(self.camera, 'origin camera')
        require_source_label(self.device, 'origin device')
        if type(self.position) is not int or self.position < 0:
            raise ValueError('origin position must be a nonnegative integer')


def decode_origin(record: Mapping[str, object]) -> FrameOrigin:
    if not isinstance(record, Mapping) or set(record) != {'camera', 'device', 'position'}:
        raise ValueError('origin record requires camera, device and position')
    return FrameOrigin(record['camera'], record['device'], record['position'])


def require_origin_camera(origin: FrameOrigin, camera: str) -> None:
    if origin.camera != camera:
        raise ValueError(f'origin camera {origin.camera!r} differs from packet camera {camera!r}')
