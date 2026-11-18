from dataclasses import dataclass


def validate_dimensions(width: int, height: int) -> None:
    if type(width) is not int or type(height) is not int:
        raise ValueError('frame dimensions must be integers')
    if width <= 0 or height <= 0:
        raise ValueError('frame dimensions must be positive')


@dataclass(frozen=True, slots=True)
class CameraSpec:
    width: int
    height: int

    def __post_init__(self) -> None:
        validate_dimensions(self.width, self.height)

    @property
    def pixel_count(self) -> int:
        return self.width * self.height
