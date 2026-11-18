from dataclasses import dataclass

from archive.profile_store import ProfileStore
from camera.calibration import validate_threshold
from camera.spec import CameraSpec


class ProfileConflictError(ValueError):
    pass


def validate_identifier(value: str, name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f'{name} must be a nonempty string')
    value.encode('utf-8')


@dataclass(frozen=True, slots=True)
class ProfileKey:
    camera: str
    revision: str

    def __post_init__(self) -> None:
        validate_identifier(self.camera, 'camera')
        validate_identifier(self.revision, 'revision')


@dataclass(frozen=True, slots=True)
class ProfileRevision:
    key: ProfileKey
    spec: CameraSpec
    threshold: int

    def __post_init__(self) -> None:
        validate_threshold(self.threshold)


class ProfileRegistry:
    def __init__(self, store: ProfileStore) -> None:
        self._store = store

    def register_profile(
        self, camera: str, revision: str, width: int, height: int, threshold: int
    ) -> ProfileKey:
        key = ProfileKey(camera, revision)
        offered = ProfileRevision(key, CameraSpec(width, height), threshold)
        values = (offered.spec.width, offered.spec.height, offered.threshold)
        fixed = self._store.insert_or_get_profile(key.camera, key.revision, *values)
        if fixed != values:
            raise ProfileConflictError(f'profile {key!r} already has a different definition')
        return key

    def get_profile(self, key: ProfileKey) -> ProfileRevision | None:
        values = self._store.find_profile(key.camera, key.revision)
        if values is None:
            return None
        width, height, threshold = values
        return ProfileRevision(key, CameraSpec(width, height), threshold)
