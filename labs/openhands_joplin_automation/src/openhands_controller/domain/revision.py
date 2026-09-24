import hashlib


def revision_hash(title: str, body: str) -> str:
    """Identify the current issue text without depending on event delivery order."""
    return hashlib.sha256(title.encode() + b"\0" + body.encode()).hexdigest()
