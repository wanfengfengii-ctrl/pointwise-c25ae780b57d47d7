from source.packet import SourcePacket


class DenseSlotError(ValueError):
    pass


def require_dense_slots(packet: SourcePacket) -> None:
    header = packet.header
    if not header.first_slot <= header.trigger_slot <= header.last_slot:
        raise DenseSlotError('trigger must lie inside the declared closed interval')
    expected_count = header.last_slot - header.first_slot + 1
    if len(packet.frames) != expected_count:
        raise DenseSlotError(
            f'window declares {expected_count} slots but contains {len(packet.frames)} frames'
        )
    for expected, frame in enumerate(packet.frames, start=header.first_slot):
        if frame.slot != expected:
            raise DenseSlotError(f'expected frame at slot {expected}, received slot {frame.slot}')
