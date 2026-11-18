import argparse
import json
import tempfile
import unittest
from os import PathLike
from pathlib import Path

from archive.profile_store import ProfileStore
from archive.schema import open_archive_connection
from archive.window_store import WindowStore
from camera.profiles import ProfileRegistry
from camera.sessions import SessionRegistry
from review.handover import HandoverService
from source.replay import PacketCapture, ReplaySource

ROOT = Path(__file__).resolve().parent


class Station:
    def __init__(self, database: str | PathLike[str]) -> None:
        self.connection = open_archive_connection(database)
        self.profiles = ProfileRegistry(ProfileStore(self.connection))
        self.sessions = SessionRegistry(self.connection, self.profiles)
        self.windows = WindowStore(self.connection)
        self.capture = PacketCapture(self.sessions, self.windows)
        self.review = HandoverService(self.windows)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> 'Station':
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _verify() -> int:
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


def _scenario(
    case_id: str, inputs: dict, expected: object, actual: object,
    downstream_expected: object, downstream_actual: object, code_paths: list[str], oracle: str,
) -> None:
    if actual != expected or downstream_actual != downstream_expected:
        raise AssertionError(f'{case_id}: {(actual, downstream_actual)!r} disagrees with the sample')
    record = {
        'case_id': case_id, 'input': inputs, 'expected': expected, 'actual': actual,
        'downstream_expected': downstream_expected, 'downstream_actual': downstream_actual,
        'code_paths': code_paths, 'oracle': oracle,
    }
    print('POINTWISE_SCENARIO ' + json.dumps(record, ensure_ascii=False, sort_keys=True))


def _demo() -> None:
    with tempfile.TemporaryDirectory(prefix='strip-station-') as directory:
        database = Path(directory) / 'handover.sqlite3'
        received = []
        with Station(database) as station:
            profile = station.profiles.register_profile('C1', 'R1', 1, 1, 20)
            station.sessions.open_session('A', profile)
            with ReplaySource((ROOT / 'samples' / 'day-shift.jsonl').open(encoding='utf-8')) as source:
                while (packet := source.next_packet()) is not None:
                    received.append((packet, station.capture.capture_packet('A', packet)))
            station.profiles.register_profile('C1', 'R2', 1, 1, 5)

        with Station(database) as station:
            (light_packet, light), (dark_packet, dark) = received
            fixed = station.windows.read_window('A', light.capture_id)
            dark_fixed = station.windows.read_window('A', dark.capture_id)
            if fixed is None or dark_fixed is None:
                raise RuntimeError('published sample window missing after reopening')
            entries = station.review.handover('A', dark_only=True)
            light_totals = [light.totals.gray_sum, light.totals.pixel_count, light.grade.value]
            light_frames = [[f.slot, list(f.payload), f.origin.position] for f in fixed.frames]
            _scenario(
                'exact_luminance_case',
                {'threshold': fixed.summary.profile.threshold,
                 'frames': [list(f.payload) for f in light_packet.frames]},
                [60, 3, 'pass'], light_totals,
                [[4, [10], 101], [5, [20], 108], [6, [30], 121]], light_frames,
                ['inspection/admission.py', 'inspection/luminance.py', 'archive/readback.py'],
                '10 + 20 + 30 = 60, with three pixels and 60 equal to 20 × 3',
            )
            report = [{
                'capture_id': entry.capture_id, 'packet_id': entry.packet_id,
                'threshold': entry.profile.threshold, 'grade': entry.grade.value,
                'totals': [entry.totals.gray_sum, entry.totals.pixel_count],
                'origins': [[slot, origin.camera, origin.device, origin.position]
                            for slot, origin in entry.origins],
            } for entry in entries]
            _scenario(
                'reopen_case',
                {'session': 'A', 'dark_only': True,
                 'candidate_frames': [[list(f.payload) for f in p.frames] for p, _ in received]},
                {'totals': [20, 2], 'payloads': [[0], [20]], 'grade': 'dark'},
                {'totals': [dark_fixed.summary.totals.gray_sum, dark_fixed.summary.totals.pixel_count],
                 'payloads': [list(f.payload) for f in dark_fixed.frames],
                 'grade': dark_fixed.summary.grade.value},
                [{'capture_id': 2, 'packet_id': 'dark-B', 'threshold': 20, 'grade': 'dark',
                  'totals': [20, 2], 'origins': [[9, 'C1', 'head-left', 201],
                                                 [10, 'C1', 'head-left', 202]]}],
                report,
                ['archive/readback.py', 'review/selection.py', 'review/verify.py', 'review/handover.py'],
                '0 and 20 are both valid pixels, so their mean is 10 under the fixed threshold 20',
            )
            if fixed.packet != light_packet or dark_fixed.packet != dark_packet:
                raise AssertionError('reopened packets disagree with camera input')


def main() -> int:
    parser = argparse.ArgumentParser(description='Offline strip inspection handover')
    parser.add_argument('action', choices=('verify', 'demo'))
    args = parser.parse_args()
    if args.action == 'verify':
        return _verify()
    _demo()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
