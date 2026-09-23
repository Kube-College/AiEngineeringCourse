# OpenHands Superset Automation

Work in progress. This directory will hold a functional demonstration of an
always-on agent controller. Exercise instructions will be developed after the
demonstration works.

The controller receives events, records durable state, applies policy, and
dispatches bounded OpenHands conversations. Apache Superset is the target
codebase. Human approval gates implementation, and a human merges the resulting
pull request.

## Current state

The local development branch and project brief are established. No controller,
OpenHands adapter, container image, or runnable demo has been implemented yet.
Keep this work local while it is WIP.

See [the design spec](docs/2026-09-23-openhands-design.md) for the agreed
architecture, deployment choices, and acceptance criteria. The
[initial brief](docs/implementation-brief.md) records the earlier setup scope.

The [implementation plans](docs/plans/README.md) split delivery into controller
simulation, OpenHands runtime, Superset validation, and GitHub delivery. They
include dependencies, shared interfaces, test cases, and completion gates.

## Local preparation

Prerequisites for the planned demo are Git, uv, Docker with Compose, a disposable
Superset checkout or fork, and access to a supported language model.

From this directory, prepare local configuration:

```sh
cp .env.example .env
```

The template records proposed controller settings. It is not consumed by an
application yet. Leave credentials empty until the live adapter is ready.
The first implementation slice will run a deterministic simulation without
GitHub or model credentials. Python dependencies and OpenHands packages will be
pinned after checking the selected SDK release and Docker workspace example.

## Sources

- [Original Devin controller](https://github.com/lspinheiro/devin_superset_automation),
  inspected at revision `c434fc053a320d20111c8e46904c62ea42f43570`.
- [OpenHands Software Agent SDK](https://github.com/OpenHands/software-agent-sdk),
  consulted on 21 September 2026. The SDK exposes agents, conversations, tools,
  and workspaces; Agent Server provides remote execution.

The original controller is an architectural reference. Its source has not been
copied into this lab. Review its licence before reusing implementation code.
