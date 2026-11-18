import sqlite3


def find_session_binding(connection: sqlite3.Connection, session: str) -> tuple[str, str] | None:
    row = connection.execute(
        'SELECT camera, revision FROM sessions WHERE session = ?', (session,)
    ).fetchone()
    if row is None:
        return None
    return row[0], row[1]


def bind_session_once(
    connection: sqlite3.Connection, session: str, camera: str, revision: str
) -> tuple[str, str]:
    connection.execute(
        '''INSERT INTO sessions (session, camera, revision) VALUES (?, ?, ?)
           ON CONFLICT (session) DO NOTHING''',
        (session, camera, revision),
    )
    binding = find_session_binding(connection, session)
    if binding is None:
        raise sqlite3.DatabaseError('session insert did not preserve a binding')
    return binding


def find_capture_by_packet(
    connection: sqlite3.Connection, session: str, packet_id: str
) -> int | None:
    row = connection.execute(
        'SELECT capture_id FROM windows WHERE session = ? AND packet_id = ?',
        (session, packet_id),
    ).fetchone()
    return None if row is None else row[0]


def list_session_capture_ids(connection: sqlite3.Connection, session: str) -> tuple[int, ...]:
    rows = connection.execute(
        'SELECT capture_id FROM windows WHERE session = ? ORDER BY capture_id', (session,)
    )
    return tuple(row[0] for row in rows)
