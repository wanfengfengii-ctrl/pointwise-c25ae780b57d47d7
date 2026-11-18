import json
from dataclasses import replace

from archive.window_store import PacketConflictError
from inspection.admission import AdmissionError
from source.packet import PacketFormatError
from source.replay import ReplayClosedError, ReplaySource
from source.tape import TapeRecordError
from support import SinglePassTape, StationCase, packet, tape_line, tape_record


class CaptureTests(StationCase):
    def assert_window_ids(self, *expected):
        with self.station.windows.read_snapshot() as reader:
            self.assertEqual(tuple(s.capture_id for s in reader.list_summaries('A')), expected)

    def test_dense_window_at_threshold(self):
        self.bind()
        source = packet('equal', [b'\x0a', b'\x14', b'\x1e'], trigger=5, positions=[101, 108, 121])
        with ReplaySource([tape_line(source)]) as replay:
            receipt = self.station.capture.capture_packet('A', replay.next_packet())
        self.assertEqual((receipt.totals.gray_sum, receipt.totals.pixel_count, receipt.grade.value),
                         (60, 3, 'pass'))
        with self.open_station() as reopened:
            fixed = reopened.windows.read_window('A', receipt.capture_id)
            self.assertEqual((fixed.summary.header.first_slot, fixed.summary.header.last_slot), (4, 6))
            self.assertEqual([(f.slot, f.payload, f.origin.camera, f.origin.device, f.origin.position)
                              for f in fixed.frames],
                             [(4, b'\x0a', 'C1', 'head-left', 101),
                              (5, b'\x14', 'C1', 'head-left', 108),
                              (6, b'\x1e', 'C1', 'head-left', 121)])

    def test_single_pass_replay(self):
        self.bind()
        first = packet('first', [b'\x07'])
        second = packet('second', [b'\x1b', b'\x19'], first=6)
        tape = SinglePassTape([tape_line(first), tape_line(second)])
        source = ReplaySource(tape)
        self.addCleanup(source.close)
        self.assertEqual(tape.read_count, 0)
        observed = source.next_packet()
        self.assertEqual(observed, first)
        one = self.station.capture.capture_packet('A', observed)
        self.assertEqual(tape.read_count, 1)
        observed = source.next_packet()
        self.assertEqual(observed, second)
        two = self.station.capture.capture_packet('A', observed)
        self.assertIsNone(source.next_packet())
        self.assertIsNone(source.next_packet())
        self.assertEqual(tape.read_count, 2)
        source.close()
        source.close()
        self.assertTrue(tape.closed)
        with self.assertRaises(ReplayClosedError):
            source.next_packet()
        self.assertEqual((one.totals.gray_sum, two.totals.gray_sum), (7, 52))
        self.assertEqual((one.totals.pixel_count, two.totals.pixel_count), (1, 2))
        self.assertEqual(self.station.windows.read_window('A', one.capture_id).packet, first)
        self.assertEqual(self.station.windows.read_window('A', two.capture_id).packet, second)

    def test_malformed_record(self):
        self.bind()
        good = packet('control', [b'\x17'])
        missing = tape_record(packet('missing', [b'\x17']))
        del missing['trigger_slot']
        invalid_hex = tape_record(packet('hex', [b'\x17']))
        invalid_hex['frames'][0]['gray_hex'] = '1z'
        records = [tape_line(good), json.dumps(missing), json.dumps(invalid_hex), '{not JSON}',
                   '{"camera":"C1","camera":"C2"}', tape_line(good)]
        with ReplaySource(records) as source:
            receipt = self.station.capture.capture_packet('A', source.next_packet())
            for error in (PacketFormatError, PacketFormatError, TapeRecordError, TapeRecordError):
                with self.assertRaises(error):
                    source.next_packet()
            self.assertEqual(source.next_packet(), good)
            self.assertIsNone(source.next_packet())
        self.assert_window_ids(receipt.capture_id)
        self.assertEqual(self.station.windows.read_window('A', receipt.capture_id).packet, good)

    def test_dense_gap_rejection(self):
        self.bind()
        control = packet('control', [b'\x0a'])
        receipt = self.station.capture.capture_packet('A', control)
        broken = packet('gap', [b'\x0a', b'\x1e'], last=6, trigger=5, slots=[4, 6])
        with self.assertRaises(AdmissionError):
            self.station.capture.capture_packet('A', broken)
        self.assert_window_ids(receipt.capture_id)
        self.assertEqual(self.station.windows.read_window('A', receipt.capture_id).packet, control)

    def test_out_of_order_and_other_bad_slot_domains(self):
        self.bind()
        control = packet('control', [b'\x0a'])
        kept = self.station.capture.capture_packet('A', control)
        for slots in ([4, 6, 5], [4, 5, 5], [4, 5, 7]):
            invalid = packet('bad-slots', [b'\x10'] * 3, last=6, trigger=5, slots=slots)
            with self.subTest(slots=slots), self.assertRaises(AdmissionError):
                self.station.capture.capture_packet('A', invalid)
        for invalid in (packet('empty', [], last=6), packet('outside', [b'\x10'], trigger=5)):
            with self.subTest(header=invalid.header), self.assertRaises(AdmissionError):
                self.station.capture.capture_packet('A', invalid)
        self.assert_window_ids(kept.capture_id)
        self.assertEqual(self.station.windows.read_window('A', kept.capture_id).packet, control)

    def test_bad_source(self):
        self.bind()
        control = packet('control', [b'\x10'])
        kept = self.station.capture.capture_packet('A', control)
        wrong_packet = packet('wrong-packet', [b'\x10'], camera='C2')
        candidate = packet('wrong-origin', [b'\x10'])
        frame = candidate.frames[0]
        wrong_origin = replace(candidate, frames=(replace(frame, origin=replace(frame.origin, camera='C2')),))
        for bad in (wrong_packet, wrong_origin):
            with self.assertRaises(AdmissionError):
                self.station.capture.capture_packet('A', bad)
        self.assert_window_ids(kept.capture_id)
        self.assertEqual(self.station.windows.read_window('A', kept.capture_id).packet, control)

    def test_frame_shape(self):
        self.bind(width=2)
        original = packet('control', [b'\x0a\x1e'], width=2)
        kept = self.station.capture.capture_packet('A', original)
        swapped = packet('candidate', [b'\x0a\x1e'], height=2)
        short = packet('candidate', [b'\x0a'], width=2)
        for invalid in (swapped, short):
            with self.assertRaises(AdmissionError):
                self.station.capture.capture_packet('A', invalid)
        self.assert_window_ids(kept.capture_id)
        self.assertEqual(self.station.windows.read_window('A', kept.capture_id).packet, original)
        fixed = packet('candidate', [b'\x0a\x1e'], width=2)
        receipt = self.station.capture.capture_packet('A', fixed)
        self.assert_window_ids(kept.capture_id, receipt.capture_id)
        self.assertEqual(self.station.windows.read_window('A', receipt.capture_id).packet, fixed)

    def test_multi_pixel_near_threshold(self):
        self.bind(width=2)
        for name, payload, gray_sum, grade in (
            ('near', b'\x13\x14', 39, 'dark'), ('black-valid', b'\x00\x28', 40, 'pass'),
        ):
            with self.subTest(packet=name):
                receipt = self.station.capture.capture_packet('A', packet(name, [payload], width=2))
                fixed = self.station.windows.read_window('A', receipt.capture_id)
                self.assertEqual((receipt.totals.gray_sum, receipt.totals.pixel_count, receipt.grade.value),
                                 (gray_sum, 2, grade))
                self.assertEqual((fixed.summary.totals.gray_sum, fixed.summary.totals.pixel_count,
                                  fixed.summary.grade.value, fixed.frames[0].payload),
                                 (gray_sum, 2, grade, payload))
        self.assertEqual([e.packet_id for e in self.station.review.handover('A', True)], ['near'])

    def test_packet_retry(self):
        self.bind()
        original = packet('repeated', [b'\x0a', b'\x0b'], positions=[101, 108])
        kept = self.station.capture.capture_packet('A', original)
        with self.open_station() as reopened:
            self.assertEqual(reopened.capture.capture_packet('A', original), kept)
            changed = packet('repeated', [b'\x0a', b'\x0c'], positions=[101, 108])
            with self.assertRaises(PacketConflictError):
                reopened.capture.capture_packet('A', changed)
            self.assertEqual(reopened.windows.read_window('A', kept.capture_id).packet, original)
        self.assert_window_ids(kept.capture_id)

    def test_origin_only_change(self):
        self.bind()
        original = packet('position', [b'\x0a', b'\x0b'], positions=[101, 108])
        kept = self.station.capture.capture_packet('A', original)
        self.assertEqual(self.station.capture.capture_packet('A', original), kept)
        altered = packet('position', [b'\x0a', b'\x0b'], positions=[101, 109])
        with self.assertRaises(PacketConflictError):
            self.station.capture.capture_packet('A', altered)
        fixed = self.station.windows.read_window('A', kept.capture_id)
        self.assertEqual([f.origin.position for f in fixed.frames], [101, 108])
        self.assert_window_ids(kept.capture_id)

    def test_same_packet_two_sessions(self):
        self.bind()
        self.bind(session='B')
        source = packet('shared', [b'\x0a'])
        first = self.station.capture.capture_packet('A', source)
        second = self.station.capture.capture_packet('B', source)
        self.assertNotEqual(first.capture_id, second.capture_id)
        self.assertIsNone(self.station.windows.read_window('A', second.capture_id))
        self.assertIsNone(self.station.windows.read_window('B', first.capture_id))
        for session, receipt in [('A', first), ('B', second)]:
            with self.subTest(session=session):
                self.assertEqual(self.station.windows.read_window(session, receipt.capture_id).packet, source)
                self.assertEqual(self.station.capture.capture_packet(session, source), receipt)
