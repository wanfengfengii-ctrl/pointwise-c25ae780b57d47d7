from archive.schema import initialize_archive
from camera.profiles import ProfileConflictError, ProfileKey
from camera.sessions import SessionBindingError
from support import StationCase, packet


class SetupTests(StationCase):
    def test_session_pins_profile(self):
        original = self.bind()
        self.assertEqual(self.station.profiles.register_profile('C1', 'R1', 1, 1, 20), original.profile.key)
        self.assertEqual(self.station.sessions.open_session('A', original.profile.key), original)
        second = self.station.profiles.register_profile('C1', 'R2', 1, 1, 30)
        self.assertEqual(self.station.profiles.get_profile(second).threshold, 30)
        self.assertEqual(self.station.sessions.get_session('A'), original)
        receipt = self.station.capture.capture_packet('A', packet('sample', [b'\x14']))
        self.assertEqual(receipt.grade.value, 'pass')
        self.assertEqual(self.station.windows.read_window('A', receipt.capture_id).summary.profile.threshold, 20)

    def test_profile_conflict(self):
        original = self.bind()
        with self.assertRaises(ProfileConflictError):
            self.station.profiles.register_profile('C1', 'R1', 2, 1, 20)
        with self.open_station() as reopened:
            profile = reopened.profiles.get_profile(original.profile.key)
            self.assertEqual((profile.spec.width, profile.spec.height, profile.threshold), (1, 1, 20))
            self.assertEqual(reopened.sessions.get_session('A'), original)

    def test_invalid_profile_values(self):
        original = self.bind()
        bad_values = [(0, 1, 20), (1, -1, 20), (1.5, 1, 20), (1, True, 20),
                      (1, 1, -1), (1, 1, 256), (1, 1, 20.0)]
        for width, height, threshold in bad_values:
            with self.subTest(values=(width, height, threshold)):
                with self.assertRaises(ValueError):
                    self.station.profiles.register_profile('C1', 'invalid', width, height, threshold)
                self.assertIsNone(self.station.profiles.get_profile(ProfileKey('C1', 'invalid')))
        self.assertEqual(self.station.profiles.get_profile(original.profile.key), original.profile)

    def test_session_rebind(self):
        original = self.bind()
        another = self.station.profiles.register_profile('C1', 'R2', 2, 1, 30)
        with self.assertRaises(SessionBindingError):
            self.station.sessions.open_session('A', another)
        with self.assertRaises(SessionBindingError):
            self.station.sessions.open_session('B', ProfileKey('C1', 'unknown'))
        with self.open_station() as reopened:
            self.assertEqual(reopened.sessions.get_session('A'), original)
            self.assertEqual(reopened.profiles.get_profile(original.profile.key).threshold, 20)
            self.assertEqual(reopened.profiles.get_profile(another).threshold, 30)
            with self.assertRaises(SessionBindingError):
                reopened.sessions.get_session('B')

    def test_reinitialize_existing(self):
        original = self.bind('user-shift', 'C7', 'stored', 2, 1, 23)
        source = packet('user-packet', [b'\x16\x17'], camera='C7', width=2)
        receipt = self.station.capture.capture_packet('user-shift', source)
        expected = self.station.windows.read_window('user-shift', receipt.capture_id)
        initialize_archive(self.station.connection)
        self.station.close()
        with self.open_station() as reopened:
            initialize_archive(reopened.connection)
            key = reopened.profiles.register_profile('C7', 'stored', 2, 1, 23)
            self.assertEqual(reopened.sessions.open_session('user-shift', key), original)
            self.assertEqual(reopened.windows.read_window('user-shift', receipt.capture_id), expected)
            self.assertEqual(reopened.capture.capture_packet('user-shift', source), receipt)
