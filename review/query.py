from archive.readback import ArchiveVerificationError, ArchivedWindow, WindowReader, WindowSummary


class ReviewQuery:
    def __init__(self, reader: WindowReader, session: str) -> None:
        self._reader = reader
        self._session = session

    def summaries(self) -> tuple[WindowSummary, ...]:
        return self._reader.list_summaries(self._session)

    def read_selected(self, selected: WindowSummary) -> ArchivedWindow:
        if selected.session != self._session:
            raise ArchiveVerificationError('selected summary belongs to another session')
        window = self._reader.read_window(self._session, selected.capture_id)
        if window is None or window.summary != selected:
            raise ArchiveVerificationError(
                f'window {self._session!r}/{selected.capture_id} disagrees with its selected summary'
            )
        return window
