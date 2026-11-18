import sqlite3
from dataclasses import dataclass

from archive.session_catalog import bind_session_once, find_session_binding
from camera.profiles import ProfileKey, ProfileRegistry, ProfileRevision, validate_identifier


class SessionBindingError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SessionBinding:
    session: str
    profile: ProfileRevision

    def __post_init__(self) -> None:
        validate_identifier(self.session, 'session')


class SessionRegistry:
    def __init__(self, connection: sqlite3.Connection, profiles: ProfileRegistry) -> None:
        self._connection = connection
        self._profiles = profiles

    def open_session(self, session: str, profile_revision: ProfileKey) -> SessionBinding:
        validate_identifier(session, 'session')
        profile = self._profiles.get_profile(profile_revision)
        if profile is None:
            raise SessionBindingError(f'unknown profile {profile_revision!r}')
        fixed_key = bind_session_once(
            self._connection, session, profile.key.camera, profile.key.revision
        )
        if fixed_key != (profile.key.camera, profile.key.revision):
            raise SessionBindingError(f'session {session!r} already has a fixed profile')
        return SessionBinding(session, profile)

    def get_session(self, session: str) -> SessionBinding:
        validate_identifier(session, 'session')
        fixed_key = find_session_binding(self._connection, session)
        if fixed_key is None:
            raise SessionBindingError(f'unknown session {session!r}')
        profile = self._profiles.get_profile(ProfileKey(*fixed_key))
        if profile is None:
            raise SessionBindingError(f'session {session!r} references a missing profile')
        return SessionBinding(session, profile)
