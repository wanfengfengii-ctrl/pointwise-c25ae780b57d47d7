import sqlite3
import unittest
from contextlib import closing
from pathlib import Path

from archive.readback import ArchiveVerificationError
from source.replay import ReplaySource
from station import Station

HERE = Path(__file__).resolve().parent


def capture_sample(station: Station) -> dict[str, int]:
    profile = station.profiles.register_profile("C1", "R1", 2, 1, 20)
    station.sessions.open_session("A", profile)
    ids = {}
    with ReplaySource((HERE / "recovery-windows.jsonl").open(encoding="utf-8")) as source:
        while (packet := source.next_packet()) is not None:
            receipt = station.capture.capture_packet("A", packet)
            ids[packet.header.packet_id] = receipt.capture_id
    return ids


def damage_original(
    connection: sqlite3.Connection, capture_id: int, slot: int, payload: bytes,
) -> None:
    cursor = connection.execute(
        "UPDATE frames SET payload = ? WHERE capture_id = ? AND slot = ?",
        (payload, capture_id, format(slot, "x")),
    )
    if cursor.rowcount != 1:
        raise ValueError(f"fixture could not modify window {capture_id}, slot {slot}")


def load_legacy_archive(connection: sqlite3.Connection) -> None:
    connection.executescript((HERE / "legacy-window.sql").read_text(encoding="utf-8"))


class RecoveryMaterialsTests(unittest.TestCase):
    def test_recording_and_local_damage(self) -> None:
        with Station(":memory:") as station:
            ids = capture_sample(station)
            self.assertEqual(ids, {"target": 1, "equal-sum": 2, "neighbor-damage": 3, "later-copy": 4})
            target = station.windows.read_window("A", ids["target"])
            self.assertEqual([frame.payload for frame in target.frames], [bytes([10, 30]), bytes([0, 20])])
            totals = target.summary.totals
            self.assertEqual((totals.gray_sum, totals.pixel_count, target.summary.grade.value), (60, 4, "dark"))
            damage_original(station.connection, ids["target"], 4, bytes([11, 29]))
            damage_original(station.connection, ids["neighbor-damage"], 33, bytes([90, 0]))
            for label in ("target", "neighbor-damage"):
                with self.assertRaises(ArchiveVerificationError):
                    station.windows.read_window("A", ids[label])
            damage_original(station.connection, ids["target"], 5, b"")
            self.assertEqual(station.connection.execute(
                "SELECT length(payload) FROM frames WHERE capture_id = ? AND ordinal = 1",
                (ids["target"],),
            ).fetchone()[0], 0)
            self.assertEqual(station.windows.read_window("A", ids["later-copy"]).frames[0].payload,
                             bytes([10, 30]))

    def test_legacy_dump(self) -> None:
        with closing(sqlite3.connect(":memory:")) as connection:
            load_legacy_archive(connection)
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone(), (1,))
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(connection.execute(
                "SELECT session, capture_id, packet_id FROM windows"
            ).fetchall(), [("A", 1, "old-A")])
            self.assertEqual(connection.execute(
                "SELECT slot, payload, position FROM frames ORDER BY ordinal"
            ).fetchall(), [("4", bytes([10, 30]), "191"), ("5", bytes([0, 20]), "192")])
