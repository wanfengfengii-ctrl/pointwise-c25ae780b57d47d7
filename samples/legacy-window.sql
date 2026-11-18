PRAGMA foreign_keys = ON;
BEGIN TRANSACTION;
CREATE TABLE profiles (
    camera TEXT NOT NULL,
    revision TEXT NOT NULL,
    width TEXT NOT NULL,
    height TEXT NOT NULL,
    threshold INTEGER NOT NULL CHECK (threshold BETWEEN 0 AND 255),
    PRIMARY KEY (camera, revision)
);
CREATE TABLE sessions (
    session TEXT NOT NULL PRIMARY KEY,
    camera TEXT NOT NULL,
    revision TEXT NOT NULL,
    FOREIGN KEY (camera, revision) REFERENCES profiles (camera, revision)
);
CREATE TABLE windows (
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
);
CREATE TABLE frames (
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
);
CREATE INDEX windows_session_capture ON windows (session, capture_id);
INSERT INTO profiles VALUES ('C1','R1','2','1',20);
INSERT INTO sessions VALUES ('A','C1','R1');
INSERT INTO windows VALUES (1,'A','old-A','C1','R1','2','1',20,'5','4','5','3c','4','dark',
    '9e1cc6adf4523eacb6a319b990b1ab41fd3ecc446b0753852f08168b064654fb',
    'e7ef154e07301692a8498e1039f49695802d54658ababd9597399547759523d3');
INSERT INTO frames VALUES (1,0,'4','2','1',X'0A1E','C1','head-left','191');
INSERT INTO frames VALUES (1,1,'5','2','1',X'0014','C1','head-left','192');
PRAGMA user_version = 1;
COMMIT;
