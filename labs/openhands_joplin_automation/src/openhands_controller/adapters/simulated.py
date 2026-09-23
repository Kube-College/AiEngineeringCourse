from ..contracts import CreateNotSent, Dispatch, RunObservation


class SimulatedAgent:
    def __init__(self, fault: str | None = None):
        self.fault = fault
        self.created: list[str] = []
        self.status: dict[str, str] = {}
        self.results: dict[str, dict[str, object]] = {}

    def create(self, dispatch: Dispatch) -> str:
        if self.fault == "before_agent_create":
            self.fault = None
            raise CreateNotSent("fault before create")
        self.created.append(dispatch.id)
        self.status[dispatch.id] = "created"
        if self.fault == "after_agent_create":
            self.fault = None
            raise RuntimeError("fault after create")
        return f"conversation-{dispatch.id}"

    def start(self, dispatch: Dispatch) -> None:
        self.status[dispatch.id] = "running"
        if self.fault == "after_agent_start":
            self.fault = None
            raise RuntimeError("fault after start")

    def observe(self, dispatch: Dispatch) -> RunObservation:
        status = self.status.get(dispatch.id, "missing")
        return RunObservation(status, self.results.get(dispatch.id))

    def stop(self, dispatch: Dispatch, *, cancel: bool) -> None:
        self.status[dispatch.id] = "failed" if cancel else "paused"

    def resume(self, dispatch: Dispatch) -> None:
        self.status[dispatch.id] = "running"

    def complete(self, dispatch_id: str, result: dict[str, object]) -> None:
        self.results[dispatch_id] = result
        self.status[dispatch_id] = "finished"
