# OpenHands Joplin Automation

Work in progress. This directory will hold a functional demonstration of an
always-on agent controller. Exercise instructions will be developed after the
demonstration works.

The controller receives events, records durable state, applies policy, and
dispatches bounded OpenHands conversations. Joplin is the target
codebase. Human approval gates implementation, and a human merges the resulting
pull request.

## Current state

The local branch has a credential-free SQLite lifecycle simulation, a qualified
OpenHands runtime, and a pinned Joplin image and validation fixtures. A live
triage runner can now watch new issues in a configured fork. It stops at the
approval gate. GitHub command intake, implementation, draft PR delivery, and
review remain later Plan 4 work. Keep this course work local while it is WIP.

See [the design spec](docs/2026-09-23-openhands-design.md) for the agreed
architecture, deployment choices, and acceptance criteria. The
[initial brief](docs/implementation-brief.md) records the earlier setup scope.

The [implementation plans](docs/plans/README.md) split delivery into controller
simulation, OpenHands runtime, Joplin validation, and GitHub delivery. They
include dependencies, shared interfaces, test cases, and completion gates.

## Local preparation

Prerequisites for the planned demo are Git, uv, Docker with Compose, a disposable
Joplin checkout or fork, and OpenRouter access to GPT-5.6 Terra. The target
checkout uses Yarn/TypeScript; the controller remains Python/uv.

From this directory, prepare local configuration:

```sh
cp .env.example .env
```

The controller loads these keys through `Settings` in
`src/openhands_controller/config.py`; unknown keys are rejected. The simulation
uses no GitHub or model credentials.

## Agent roles

Declare each role's tool names, prompt file and selected skills in
`src/openhands_controller/runtime/agents.py`. Role instructions live under
`runtime/agent_content/`; shared instructions are in `common.md`. Skills are
short Markdown files under `runtime/agent_content/skills/`. The factory loads
only the files named in the role declaration and adds them to OpenHands
`AgentContext`. It does not load user, public or target-checkout skills.

Each declaration can also set `model=ModelRoute(...)`. An omitted model uses
`openai/gpt-5.6-terra`, the current `LLM_MODEL` default. For example, a review
declaration can use `model=ModelRoute("provider/model-id", Decimal("3"),
Decimal("15"))` while the other roles keep Terra. The two Decimal values are
conservative input and output budget rates in USD per million tokens. Choose
rates that cover the selected model's current OpenRouter pricing. The gateway
reserves against those rates before each call and settles custom models from
OpenRouter's reported `usage.cost`. A response without a reported cost blocks
further requests for that issue. Keep `LLM_MODEL` at its default when only some
roles override it; a different global value requires priced routes for every
role.

The issue title, body, candidate SHA and result schema remain per-dispatch task
data in `runtime/prompts.py`. OpenHands keeps its built-in system prompt, with
the shared and role instructions added as system context. The typed result
schemas stay in `domain/results.py`, where the controller validates them.

Tool selection limits what the agent sees, but a terminal can still write files.
The triage and review prompts request no edits; source-level read-only access
needs a separate workspace permission boundary before relying on it as an
enforced guarantee.

## Run triage and label-approved implementation

From this lab directory, set `AGENT_BACKEND=openhands`, `GH_REPO` to your fork
(`lspinheiro/joplin` or its GitHub URL), `GH_TOKEN`, and `LLM_API_KEY` in the
ignored `.env`. Set `GITHUB_WRITES_ENABLED=true` to let the controller reconcile
one `agent:state:*` label, maintain its status comment, and post one outcome
comment for each completed agent run. The token needs **Issues: Read and write**
on the selected fork. With writes disabled, progress is visible in the terminal
and the controller still reads approval-label events.

The pinned Joplin image identified by `docker/versions.json` must be present in
Docker. Run:

```sh
make run
```

Once the terminal says it is watching your fork, manually create a new issue in
that fork. The controller polls every 20 seconds by default. It logs `queued`,
`triaging`, then `awaiting-approval` after a successful OpenHands result. A
state label and status comment show the same progression when GitHub writes are
enabled. Creating the issue triggers triage without an approval command.

After triage reaches `awaiting-approval`, add **`agent:implement`** to the issue.
The controller checks the label-addition event and the actor's repository
permission, then starts the implementer once. A label that was already present
does not authorise implementation. The controller removes the approval label
after consuming it. The `agent:state:*` labels show state; editing one does not
trigger an agent. Agent outcome comments are posted by the token owner and name
the contributing agent role.

This live slice stops at `needs-human` after the implementer finishes. It
preserves the workspace for inspection. Candidate validation and draft PR
publication still require the remaining delivery work.

The first start records a durable watch start time and skips older issues. On
restart it replays known issues and approval events since that time, using stable
event IDs to avoid repeating agent runs. State and runtime authentication files remain under
the ignored `STATE_DIR`; the workspace remains under `WORKSPACE_DIR`.
Use Ctrl-C to stop the controller.

To inspect run history, cost, validation and redacted agent activity while the
controller runs, start `make dashboard` in another terminal and open
<http://127.0.0.1:8765>. The [performance console guide](docs/performance-console.md)
explains its measurements and the `controller rate` command for human feedback.

Run the persisted storage example from this lab directory:

```sh
rtk proxy uv run controller simulate --state-dir /tmp/openhands-demo-01
rtk proxy uv run pytest tests/test_store.py -q
```

The first command records a queued demo issue in SQLite and prints its state.
Repeating the command reopens the same state without creating another event.
The lab uses its own `pyproject.toml` and `uv.lock`; it does not modify the
parent Python project.

Run each complete scenario with a separate state directory:

```sh
rtk proxy uv run controller simulate --state-dir .data/happy --scenario happy
rtk proxy uv run controller simulate --state-dir .data/duplicate --scenario duplicate
rtk proxy uv run controller simulate --state-dir .data/restart --scenario restart
rtk proxy uv run controller simulate --state-dir .data/budget --scenario budget
rtk proxy uv run controller simulate --state-dir .data/cancel --scenario cancel
rtk proxy uv run pytest tests/test_store.py tests/test_dispatch.py tests/test_commands.py tests/test_budget.py tests/test_simulation.py -q
```

The command prints the persisted workflow and budget snapshot. `happy`,
`duplicate`, and `restart` reach `ready-for-human` with a fake draft URL.
`budget` reaches `needs-human`; `cancel` reaches `cancelled`. The fake delivery
does not call GitHub, Git, OpenHands, or a model provider. The US$5 issue cap
and run limits follow the [approved design](docs/2026-09-23-openhands-design.md).
Existing simulation databases receive the additive iteration-accounting
column when reopened.

## Target repository

The demo targets [Joplin](https://github.com/laurent22/joplin) at the pinned
`dev` snapshot `1d6beb0443e6d958b2c241f45978bd5de069f309`.
Candidate fixtures cover shared note-title logic (#16638) and desktop tag input
(#16261). Both require reproduction before live demo execution. This replaces
the previous Superset target.

## Sources

- [Original Devin controller](https://github.com/lspinheiro/devin_superset_automation),
  inspected at revision `c434fc053a320d20111c8e46904c62ea42f43570`.
- [OpenHands Software Agent SDK](https://github.com/OpenHands/software-agent-sdk),
  consulted on 21 September 2026. The SDK exposes agents, conversations, tools,
  and workspaces; Agent Server provides remote execution.

The original controller is an architectural reference. Its source has not been
copied into this lab. Review its licence before reusing implementation code.
