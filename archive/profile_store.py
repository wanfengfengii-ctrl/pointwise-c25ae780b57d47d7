import sqlite3

from archive.schema import decode_natural, encode_natural


class ProfileStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def find_profile(self, camera: str, revision: str) -> tuple[int, int, int] | None:
        row = self._connection.execute(
            'SELECT width, height, threshold FROM profiles WHERE camera = ? AND revision = ?',
            (camera, revision),
        ).fetchone()
        if row is None:
            return None
        return decode_natural(row[0]), decode_natural(row[1]), row[2]

    def insert_or_get_profile(
        self, camera: str, revision: str, width: int, height: int, threshold: int
    ) -> tuple[int, int, int]:
        self._connection.execute(
            '''INSERT INTO profiles (camera, revision, width, height, threshold)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (camera, revision) DO NOTHING''',
            (camera, revision, encode_natural(width), encode_natural(height), threshold),
        )
        stored = self.find_profile(camera, revision)
        if stored is None:
            raise sqlite3.DatabaseError('profile insert did not preserve a record')
        return stored
