# OpenHands Joplin Automation

Work in progress. This directory will hold a functional demonstration of an
always-on agent controller. Exercise instructions will be developed after the
demonstration works.

The controller receives events, records durable state, applies policy, and
dispatches bounded OpenHands conversations. Joplin is the target
codebase. Human approval gates implementation, and a human merges the resulting
pull request.

## Current state

The local development branch, design, and implementation plans are established.
The controller has a credential-free SQLite simulation of issue intake,
triage, approval, implementation, validation, review, cancellation, restart,
and budget handoff. The OpenHands adapter, container image, and live demo are
planned work. Keep this work local while it is WIP.

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

The template records proposed settings for later live integration. Plan 01
simulations do not read it. Leave credentials empty until the live adapter is
ready. The simulation uses no GitHub or model credentials. OpenHands packages
will be pinned after SDK qualification.

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
