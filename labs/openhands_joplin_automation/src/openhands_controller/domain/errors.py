class EventConflict(ValueError):
    """An event identity was reused with different content."""


class VersionConflict(ValueError):
    """A workflow was changed by another writer."""


class CreateNotSent(RuntimeError):
    """An adapter can prove that no remote create request was transmitted."""
