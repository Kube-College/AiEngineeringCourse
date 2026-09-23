# Implementation brief

Historical setup brief. The [design spec](2026-09-23-openhands-design.md)
supersedes the architecture and deployment choices below.

## Goal

Build a local demonstration of a deterministic controller dispatching bounded
coding agents. First prove the workflow with simulated events and agents, then
run an OpenHands conversation against a disposable Superset checkout. Later,
connect a designated GitHub fork and produce a draft PR. Decomposition into
student exercises follows functional validation.

## Architecture

```text
manual events / GitHub polling / optional webhook
                       |
                normalise event
                       |
            controller + SQLite store
           policy / deduplication / limits
                       |
                 agent adapter
                       |
              OpenHands conversation
                       |
               Docker workspace
                       |
                validated result
                       |
              next durable state
```

The controller owns event handling, state transitions, approval checks,
workspace allocation, validation, and GitHub projection. OpenHands owns bounded
agent execution. Start the controller as a host Python process managed by uv;
run agent work inside Docker. Package the controller in Compose once the
workspace lifecycle is verified. A UI and OpenHands Automation are deferred.

SQLite is authoritative for the mapping from repository, issue number, source
revision, and role to conversation and workspace identifiers. Record a dispatch
intent before calling the adapter. A crash between remote creation and storing
the returned identifier must enter reconciliation; it must not silently trigger
another execution. Define recovery behaviour against the selected SDK API
before claiming restart-safe dispatch.

## Workflow

The target flow is intake, triage, awaiting approval, implementation, review,
and ready for human review. Failed, cancelled, timed-out, or ambiguous runs
require explicit outcomes. A source revision change invalidates earlier
approval. A bounded review/fix cycle may return to implementation; reaching its
limit hands the issue to a human. No automatic merge is planned.

Polling, webhooks, and simulation will feed the same event handler. Begin with
manual simulation and add polling before public webhook ingress.

## Delivery sequence

1. Build a uv-managed controller with SQLite persistence and a simulated agent
   adapter. Demonstrate intake, triage, approval, implementation, and completion.
   Verify duplicate delivery and restart behaviour with deterministic tests.
2. Select and pin compatible OpenHands SDK, tools, workspace, and Agent Server
   versions. Run one bounded Docker conversation against a disposable checkout.
   Capture its result, conversation identifier, and terminal status.
3. Connect the real adapter to persisted dispatches. Verify timeout,
   cancellation, failure, and recovery behaviour. Keep agent workspaces separate
   from the course source tree.
4. Add polling for one explicitly configured Superset fork. Keep write actions
   disabled until the destination is configured. Let the controller validate
   the patch, run agreed checks, and manage the branch and draft PR.
5. Add review and one bounded fix cycle. Produce a repeatable demo script with
   the observed outputs and known limitations.

## Initial validation

- Simulation requires no model or GitHub credentials.
- Duplicate events do not create duplicate logical runs.
- Pending approval survives a controller restart.
- Implementation requires approval for the current source revision.
- Agent errors and timeouts lead to visible terminal or recovery states.
- Live smoke validation shows that OpenHands executed inside Docker and changed
  only its disposable checkout.
- Live GitHub validation targets the configured fork and produces a draft PR
  with the exact validation result recorded.

## Configuration and boundaries

Keep `.env`, databases, logs, transcripts, and workspaces ignored. Example
configuration contains no secrets. The controller retains GitHub credentials;
the agent should receive only the model access and repository access needed for
its task. Treat issue text and repository content as untrusted inputs.

The live model, endpoint, Superset fork, and validation command remain deployment
choices. They do not block the simulated first slice. SDK method names, result
schemas, version pins, and restart semantics require verification during adapter
implementation. The attached architecture analysis is a proposal, not an API
contract.
