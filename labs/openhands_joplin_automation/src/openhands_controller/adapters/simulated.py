from ..contracts import CreateNotSent, Dispatch, IssueKey, RunObservation, ValidationResult


class SimulatedAgent:
    def __init__(self, fault: str | None = None):
        self.fault = fault
        self.created: list[str] = []
        self.status: dict[str, str] = {}
        self.results: dict[str, dict[str, object]] = {}
        self.usage: dict[str, int] = {}
        self.report_usage = True

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
        usage = ({"request_id": dispatch.id, "cumulative_microusd": self.usage[dispatch.id], "iterations": 1},) if dispatch.id in self.usage else ()
        return RunObservation(status, self.results.get(dispatch.id), usage)

    def stop(self, dispatch: Dispatch, *, cancel: bool) -> None:
        self.status[dispatch.id] = "failed" if cancel else "paused"

    def resume(self, dispatch: Dispatch) -> None:
        self.status[dispatch.id] = "running"

    def complete(self, dispatch_id: str, result: dict[str, object]) -> None:
        self.results[dispatch_id] = result
        if self.report_usage:
            self.usage[dispatch_id] = 100_000
        self.status[dispatch_id] = "finished"


class SimulatedDelivery:
    """Records fake validation and publication without Git or HTTP."""

    def __init__(self):
        self.published: list[str] = []

    def capture(self, dispatch: Dispatch) -> str:
        return f"sha-{dispatch.id}"

    def validate(self, candidate_sha: str, profile: str) -> ValidationResult:
        return ValidationResult(candidate_sha, profile, True, "simulated-evidence")

    def publish(self, issue: IssueKey, candidate_sha: str) -> str:
        self.published.append(candidate_sha)
        return f"https://example.invalid/{issue[1]}/draft"
