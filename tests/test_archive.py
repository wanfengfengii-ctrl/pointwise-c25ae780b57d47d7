import sqlite3

from support import StationCase, packet


class ArchiveTests(StationCase):
    def test_partial_write_rollback(self):
        self.bind()
        first = packet('first', [b'\x0a'], positions=[211])
        second = packet('second', [b'\x14', b'\x1e'], first=10, positions=[311, 312])
        kept = self.station.capture.capture_packet('A', first)
        reader_station = self.open_station()
        observations = []

        def observe(capture_id, staged_frames):
            writer = self.station.connection
            staged_header = writer.execute(
                'SELECT packet_id FROM windows WHERE capture_id = ?', (capture_id,)
            ).fetchone()
            with reader_station.windows.read_snapshot() as reader:
                observations.append((
                    capture_id, staged_frames, staged_header[0],
                    reader.read_window('A', capture_id),
                    tuple(s.capture_id for s in reader.list_summaries('A')),
                    reader.read_window('A', kept.capture_id).packet,
                ))

        writer = self.station.connection
        writer.create_function('observe_inflight', 2, observe)
        writer.execute('''CREATE TEMP TRIGGER abort_second_frame
                          BEFORE INSERT ON frames WHEN NEW.ordinal = 1
                          BEGIN
                              SELECT observe_inflight(NEW.capture_id, (
                                  SELECT count(*) FROM frames WHERE capture_id = NEW.capture_id
                              ));
                              SELECT RAISE(ABORT, 'frame write interrupted');
                          END''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'frame write interrupted'):
            self.station.capture.capture_packet('A', second)
        self.assertEqual(len(observations), 1)
        failed_id, frame_count, packet_id, visible, visible_ids, old_packet = observations[0]
        self.assertEqual((frame_count, packet_id), (1, 'second'))
        self.assertIsNone(visible)
        self.assertEqual(visible_ids, (kept.capture_id,))
        self.assertEqual(old_packet, first)
        reader_station.close()
        self.station.close()

        with self.open_station() as reopened:
            self.assertEqual(reopened.windows.read_window('A', kept.capture_id).packet, first)
            self.assertIsNone(reopened.windows.read_window('A', failed_id))
            self.assertEqual(reopened.connection.execute('SELECT count(*) FROM frames').fetchone()[0], 1)
            retried = reopened.capture.capture_packet('A', second)
            self.assertEqual((retried.totals.gray_sum, retried.totals.pixel_count), (50, 2))
            self.assertEqual(reopened.windows.read_window('A', retried.capture_id).packet, second)
            self.assertEqual(reopened.capture.capture_packet('A', second), retried)
            self.assertEqual(reopened.windows.read_window('A', kept.capture_id).packet, first)
            with reopened.windows.read_snapshot() as reader:
                self.assertEqual(tuple(s.capture_id for s in reader.list_summaries('A')),
                                 (kept.capture_id, retried.capture_id))
