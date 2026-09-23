import fcntl
from pathlib import Path


class SchedulerLock:
    """Hold an exclusive process lock for a state directory."""

    def __init__(self, state_dir: Path):
        state_dir.mkdir(parents=True, exist_ok=True)
        self.file = (state_dir / "controller.lock").open("a+")
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.file.close()
            raise RuntimeError("another controller owns this state directory") from None

    def close(self):
        fcntl.flock(self.file, fcntl.LOCK_UN)
        self.file.close()
