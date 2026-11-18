import sqlite3
from os import PathLike

SCHEMA_VERSION = 1

_SCHEMA = (
    '''CREATE TABLE profiles (
           camera TEXT NOT NULL,
           revision TEXT NOT NULL,
           width TEXT NOT NULL,
           height TEXT NOT NULL,
           threshold INTEGER NOT NULL CHECK (threshold BETWEEN 0 AND 255),
           PRIMARY KEY (camera, revision)
       )''',
    '''CREATE TABLE sessions (
           session TEXT NOT NULL PRIMARY KEY,
           camera TEXT NOT NULL,
           revision TEXT NOT NULL,
           FOREIGN KEY (camera, revision) REFERENCES profiles (camera, revision)
       )''',
    '''CREATE TABLE windows (
           capture_id INTEGER PRIMARY KEY,
           session TEXT NOT NULL REFERENCES sessions (session),
           packet_id TEXT NOT NULL,
           camera TEXT NOT NULL,
           revision TEXT NOT NULL,
           width TEXT NOT NULL,
           height TEXT NOT NULL,
           threshold INTEGER NOT NULL CHECK (threshold BETWEEN 0 AND 255),
           trigger_slot TEXT NOT NULL,
           first_slot TEXT NOT NULL,
           last_slot TEXT NOT NULL,
           gray_sum TEXT NOT NULL,
           pixel_count TEXT NOT NULL,
           grade TEXT NOT NULL CHECK (grade IN ('dark', 'pass')),
           frames_digest TEXT NOT NULL,
           header_digest TEXT NOT NULL,
           UNIQUE (session, packet_id)
       )''',
    '''CREATE TABLE frames (
           capture_id INTEGER NOT NULL REFERENCES windows (capture_id),
           ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
           slot TEXT NOT NULL,
           width TEXT NOT NULL,
           height TEXT NOT NULL,
           payload BLOB NOT NULL,
           origin_camera TEXT NOT NULL,
           device TEXT NOT NULL,
           position TEXT NOT NULL,
           PRIMARY KEY (capture_id, ordinal),
           UNIQUE (capture_id, slot)
       )''',
    'CREATE INDEX windows_session_capture ON windows (session, capture_id)',
)


def encode_natural(value: int) -> str:
    if type(value) is not int or value < 0:
        raise ValueError('stored quantities must be nonnegative integers')
    return format(value, 'x')


def decode_natural(value: str) -> int:
    if not isinstance(value, str):
        raise ValueError('stored quantity must use the archive text encoding')
    number = int(value, 16)
    if number < 0 or encode_natural(number) != value:
        raise ValueError('stored quantity has a noncanonical encoding')
    return number


def _schema_version(connection: sqlite3.Connection) -> int:
    return connection.execute('PRAGMA user_version').fetchone()[0]


def initialize_archive(connection: sqlite3.Connection) -> None:
    version = _schema_version(connection)
    if version == SCHEMA_VERSION:
        return
    if version != 0:
        raise sqlite3.DatabaseError(f'unsupported archive schema version {version}')
    connection.execute('BEGIN IMMEDIATE')
    try:
        version = _schema_version(connection)
        if version == 0:
            for statement in _SCHEMA:
                connection.execute(statement)
            connection.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
        elif version != SCHEMA_VERSION:
            raise sqlite3.DatabaseError(f'unsupported archive schema version {version}')
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def open_archive_connection(path: str | PathLike[str]) -> sqlite3.Connection:
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys = ON')
        initialize_archive(connection)
    except BaseException:
        connection.close()
        raise
    return connection
