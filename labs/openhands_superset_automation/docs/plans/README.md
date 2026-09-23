# OpenHands demo implementation plans

The design is approved for planning. These plans have not been executed.
The course checkout is `teaching/Agentic_AI_Course/public`, branch
`codex/openhands-superset-automation`. The lab root is
`labs/openhands_superset_automation`. Run lab commands from that directory.

## Delivery order

| Plan | Depends on | Working result |
| --- | --- | --- |
| [01 Controller simulation](01-controller.md) | None | Restartable, credential-free workflow with approval, cancellation, and budget handoffs |
| [02 OpenHands runtime](02-runtime.md) | 01 contracts | Qualified Docker execution with OpenRouter, persistent conversations, and enforced limits |
| [03 Superset validation](03-superset.md) | 01 contracts; 02 image selection | Pinned dual-toolchain image and reproducible backend/frontend failing fixtures |
| [04 GitHub delivery](04-delivery.md) | 01–03 | Authorised polling, exact-commit validation/publication, review/fix, and two documented demos |

Complete 01 before integrating adapters. Read-only qualification for 02 and 03
can occur earlier, but finalise their pins and profiles together. Implement 04
with fakes before enabling external writes. There is no separate scaffolding
milestone: packaging belongs to the first runnable simulation.

## Source layout

| Path | Responsibility |
| --- | --- |
| `src/openhands_controller/contracts.py` | Provider-neutral event, workflow, dispatch, result, and validation records |
| `config.py`, `cli.py` | Validated configuration and CLI entry points |
| `store.py`, `schema.sql` | Transactions, durable state, constraints, and usage ledger |
| `controller.py`, `scheduler.py` | State transitions, dispatch and recovery, single-instance scheduling |
| `commands.py`, `revision.py`, `budget.py` | Approval parsing, issue revision identity, and per-request accounting |
| `adapters/simulated.py`, `adapters/openhands.py` | Implement the same agent protocol |
| `runtime/workspaces.py`, `runtime/prompts.py` | Docker lifecycle and typed role outputs |
| `github/client.py`, `github/polling.py`, `github/projection.py` | HTTP, event collection/actor evidence, and idempotent status projection |
| `delivery/candidate.py`, `delivery/validation.py`, `delivery/publication.py` | Trusted patch capture, isolated checks, and Git/PR operations |
| `fixtures/`, `validation/`, `docker/` | Attributed problem fixtures, trusted checks, and pinned image |
| `tests/`, `docs/evidence/` | Deterministic regression tests and sanitised qualification reports |

Paths in the table are beneath `src/openhands_controller/` unless they begin
with `tests/`, `docs/`, `fixtures/`, `validation/`, or `docker/`.

## Shared interfaces

Plan 01 owns these types. Later plans implement their protocols, keeping SDK
objects behind the adapter. Use frozen dataclasses or equivalently strict models.

```python
IssueKey = tuple[str, int]  # repository, issue number

@dataclass(frozen=True)
class Event:
    id: str
    kind: str
    issue: IssueKey
    revision: str
    actor: str
    payload: dict[str, object]

@dataclass(frozen=True)
class Dispatch:
    id: str
    issue: IssueKey
    revision: str
    role: str  # triage | implementation | review | fix
    attempt: int
    workspace_id: str
    conversation_id: str | None
    candidate_sha: str | None
    deadline: str  # UTC ISO 8601

@dataclass(frozen=True)
class RunObservation:
    status: str  # missing | created | running | paused | finished | failed | unknown
    result: dict[str, object] | None
    usage: tuple[dict[str, object], ...]
    error: str | None

class AgentAdapter(Protocol):
    def create(self, dispatch: Dispatch) -> str: ...
    def start(self, dispatch: Dispatch) -> None: ...
    def observe(self, dispatch: Dispatch) -> RunObservation: ...
    def stop(self, dispatch: Dispatch, *, cancel: bool) -> None: ...
    def resume(self, dispatch: Dispatch) -> None: ...

@dataclass(frozen=True)
class ValidationResult:
    candidate_sha: str
    profile: str
    passed: bool
    evidence_dir: str

class Delivery(Protocol):
    def capture(self, dispatch: Dispatch) -> str: ...  # immutable candidate SHA
    def validate(self, candidate_sha: str, profile: str) -> ValidationResult: ...
    def publish(self, issue: IssueKey, candidate_sha: str) -> str: ...  # draft PR URL
```

`Controller.handle(event: Event) -> None` is the single entry point for events.
`Controller.tick() -> None` processes one scheduling/reconciliation pass.
`Store.workflow(issue: IssueKey) -> dict[str, object]` returns a snapshot.
`Store.dispatches(issue: IssueKey) -> list[Dispatch]` exposes durable attempts.
The controller constructor takes `store`, `agent`, `delivery`, `permissions`,
and `clock`; fake implementations make tests independent of external services.
`permissions(actor: str, repo: str) -> str` returns GitHub's normalised role,
or raises on unavailable evidence.

Role results are strict: triage has `scope`, `summary`, `validation_profile`;
implementation/fix has `summary` and `changed_paths`; review has
`candidate_sha`, `verdict` (`pass` or `changes_requested`), and
`findings` (path, line, explanation). Results never contain executable commands
or authority to transition state.

## Common test harness

Task 01.1 supplies `tests/support.py` with `Harness(root, fault=None)`.
It exposes `controller`, `store`, `agent`, `delivery`, `clock`, and:
`issue()`, `emit(kind, **payload)`, `complete(role, **result)`,
`restart()`, and `run_to(state)`. It uses issue
`("demo/superset", 1)`, actor `maintainer`, and revision `r1`.
`agent.created` lists dispatch IDs; `delivery.published` lists candidate SHAs.
Fault injection raises at named persistence/external-call boundaries.
`clock.advance(seconds)` makes timeout tests deterministic.
Never permit `run_to` to spin indefinitely; bound ticks and report observed state.

## Spec coverage

| Design requirement | Owning tasks |
| --- | --- |
| State, dispatch intent, deduplication, crash recovery | 01.1–01.2 |
| Authorisation, revisions, commands, pause/cancel | 01.3, 04.1 |
| Usage, US$5, unknown spend, retry limits | 01.4, 02.2 |
| Docker isolation, persistence, cancellation, cleanup | 02.1–02.3 |
| Backend/frontend fixtures and trusted validation | 03.1–03.3 |
| Git ownership and publication reconciliation | 04.2 |
| Review at exact SHA and one fix cycle | 04.3 |
| Polling, projection, optional signed webhook | 04.1 |
| Live qualification and two demo handoffs | 02.3, 04.4 |
| Licence check, documentation, local-only work | 01.1 and each plan's completion gate |

## Review and execution

Review the four plans before implementation. Choose native execution or
subagent-driven execution explicitly. No execution method is assumed.
External model calls require a locally configured key; never paste keys into
plans, logs, or evidence. Repository setup must name the destination fork before
creating issues or publishing PRs. A missing key or destination does not block
credential-free tests.
