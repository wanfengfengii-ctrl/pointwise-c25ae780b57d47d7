from archive.readback import ArchiveVerificationError
from camera.sessions import SessionBindingError
from source.replay import ReplayClosedError, ReplaySource
from support import SinglePassTape, StationCase, packet, tape_line


class HandoverTests(StationCase):
    def _publish(self, name, gray, *, session='A', first=4, position=101):
        source = packet(name, [bytes([gray])], first=first, positions=[position])
        return self.station.capture.capture_packet(session, source)

    def _damage_frame(self, capture_id, payload):
        self.station.connection.execute(
            'UPDATE frames SET payload = ? WHERE capture_id = ? AND ordinal = 0',
            (payload, capture_id),
        )

    def test_dark_handover_without_source(self):
        self.bind()
        dark = packet('dark', [b'\x0a'], positions=[403])
        threshold = packet('threshold', [b'\x14'], first=9, positions=[414])
        tape = SinglePassTape([tape_line(dark), tape_line(threshold)])
        with ReplaySource(tape) as source:
            first = self.station.capture.capture_packet('A', source.next_packet())
            second = self.station.capture.capture_packet('A', source.next_packet())
            self.assertIsNone(source.next_packet())
        self.assertTrue(tape.closed)
        with self.assertRaises(ReplayClosedError):
            source.next_packet()
        self.station.close()
        with self.open_station() as reopened:
            report = reopened.review.handover('A', dark_only=True)
            self.assertEqual([entry.capture_id for entry in report], [first.capture_id])
            entry = report[0]
            self.assertEqual((entry.packet_id, entry.profile.key.revision, entry.profile.threshold,
                              entry.totals.gray_sum, entry.totals.pixel_count, entry.grade.value),
                             ('dark', 'R1', 20, 10, 1, 'dark'))
            fixed = reopened.windows.read_window('A', entry.capture_id)
            self.assertEqual(fixed.packet, dark)
            self.assertEqual([(slot, origin.camera, origin.device, origin.position)
                              for slot, origin in entry.origins], [(4, 'C1', 'head-left', 403)])
            self.assertEqual(reopened.windows.read_window('A', second.capture_id).packet, threshold)

    def test_tie_trigger_order(self):
        self.bind()
        self.bind(session='B')
        late = self._publish('tie-first', 11, first=16, position=501)
        passing = self._publish('passing', 20, first=5, position=502)
        other = self._publish('foreign', 5, session='B', first=1, position=503)
        early = self._publish('early', 9, first=2, position=504)
        tie = self._publish('tie-second', 12, first=16, position=505)
        self.station.close()
        with self.open_station() as reopened:
            self.assertIsNone(reopened.windows.read_window('A', other.capture_id))
            for receipt in (late, tie):
                self.assertIsNotNone(reopened.windows.read_window('A', receipt.capture_id))
            dark = reopened.review.handover('A', True)
            self.assertEqual([(e.trigger_slot, e.capture_id, e.totals.gray_sum, e.origins[0][1].position)
                              for e in dark], [(2, early.capture_id, 9, 504),
                                               (16, late.capture_id, 11, 501),
                                               (16, tie.capture_id, 12, 505)])
            self.assertEqual([e.capture_id for e in reopened.review.handover('A', False)],
                             [early.capture_id, passing.capture_id, late.capture_id, tie.capture_id])
            self.assertEqual([e.capture_id for e in reopened.review.handover('B', True)],
                             [other.capture_id])

    def test_empty_session(self):
        self.bind('empty')
        self.assertEqual(self.station.review.handover('empty', True), [])
        self.assertEqual(self.station.review.handover('empty', False), [])
        with self.assertRaises(SessionBindingError):
            self.station.review.handover('unregistered', False)

    def test_newer_profile(self):
        self.bind()
        old = self._publish('old-dark', 10)
        newest = self.station.profiles.register_profile('C1', 'R2', 1, 1, 5)
        self.station.sessions.open_session('B', newest)
        new = self._publish('new-pass', 10, session='B')
        self.station.close()
        with self.open_station() as reopened:
            selected = reopened.review.handover('A', True)
            self.assertEqual([(e.capture_id, e.profile.threshold, e.grade.value) for e in selected],
                             [(old.capture_id, 20, 'dark')])
            self.assertEqual(reopened.review.handover('B', True), [])
            fixed = reopened.windows.read_window('B', new.capture_id)
            self.assertEqual((fixed.summary.profile.threshold, fixed.summary.grade.value), (5, 'pass'))

    def test_damaged_frame_rejected(self):
        self.bind()
        damaged = self._publish('damaged', 10)
        self._damage_frame(damaged.capture_id, b'\x0b')
        self.station.close()
        with self.open_station() as reopened:
            with self.assertRaises(ArchiveVerificationError):
                reopened.windows.read_window('A', damaged.capture_id)
            with self.assertRaises(ArchiveVerificationError):
                reopened.review.handover('A', True)

    def test_same_sum_payload(self):
        self.bind(width=2, threshold=25)
        original = packet('swapped-pixels', [b'\x0a\x1e'], width=2)
        receipt = self.station.capture.capture_packet('A', original)
        self.assertEqual((receipt.totals.gray_sum, receipt.totals.pixel_count, receipt.grade.value),
                         (40, 2, 'dark'))
        self._damage_frame(receipt.capture_id, b'\x1e\x0a')
        self.station.close()
        with self.open_station() as reopened:
            with self.assertRaisesRegex(ArchiveVerificationError, 'frame evidence digest mismatch'):
                reopened.windows.read_window('A', receipt.capture_id)
            with self.assertRaisesRegex(ArchiveVerificationError, 'frame evidence digest mismatch'):
                reopened.review.handover('A', True)

    def test_fixed_metadata(self):
        self.bind()
        dark = self._publish('mislabelled', 10)
        self.station.connection.execute(
            'UPDATE windows SET grade = ? WHERE capture_id = ?', ('pass', dark.capture_id)
        )
        self.station.close()
        with self.open_station() as reopened:
            with self.assertRaisesRegex(ArchiveVerificationError, 'header digest mismatch'):
                reopened.review.handover('A', True)

    def test_no_partial_report(self):
        self.bind()
        good = self._publish('earlier-dark', 9, first=2)
        damaged = self._publish('later-dark', 11, first=4)
        self._damage_frame(damaged.capture_id, b'\x0c')
        self.station.close()
        with self.open_station() as reopened:
            self.assertEqual(reopened.windows.read_window('A', good.capture_id).summary.totals.gray_sum, 9)
            with self.assertRaises(ArchiveVerificationError):
                reopened.review.handover('A', True)
