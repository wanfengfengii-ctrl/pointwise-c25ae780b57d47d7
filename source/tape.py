import json
from collections.abc import Iterable, Iterator


class TapeRecordError(ValueError):
    pass


def _unique_members(pairs: list[tuple[str, object]]) -> dict[str, object]:
    members = {}
    for key, value in pairs:
        if key in members:
            raise ValueError(f'duplicate JSON member {key!r}')
        members[key] = value
    return members


def _decode_record(line: tuple[int, str]) -> dict[str, object]:
    number, raw = line
    if not isinstance(raw, str):
        raise TapeRecordError(f'line {number} is not text')
    try:
        record = json.loads(raw, object_pairs_hook=_unique_members)
    except (ValueError, RecursionError) as exc:
        raise TapeRecordError(f'line {number}: {exc}') from exc
    if not isinstance(record, dict):
        raise TapeRecordError(f'line {number} must contain one JSON object')
    return record


def iter_packet_records(lines: Iterable[str]) -> Iterator[dict[str, object]]:
    return map(_decode_record, enumerate(lines, start=1))
