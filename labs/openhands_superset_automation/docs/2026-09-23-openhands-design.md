# OpenHands Superset automation design

Date: 23 September 2026. Status: approved for implementation planning;
implementation has not started. See the [implementation plans](plans/README.md).

## Purpose and scope

Build a functional local demonstration of a durable controller dispatching
bounded OpenHands agents against Apache Superset. Develop student exercises
after the demo works. Keep the course branch local during WIP.

The accepted deployment is a local Python controller, Docker agent workspaces,
and GPT-5.6 Terra through OpenRouter. GitHub labels and comments provide the
human interface. The controller owns Git operations, validation, and draft PR
publication. A human owns merging.

Support backend and frontend work with one active agent execution. Start with
the two upstream issues selected below. Multi-host operation, automatic merging,
Agent Canvas, OpenHands Automation, local inference, and a full Superset browser
test suite are outside the initial scope.

## Architecture

```text
GitHub polling / optional webhook / local simulation
                         |
              normalisation + actor checks
                         |
             controller + SQLite transactions
          revisions / approvals / dispatches / budgets
                         |
                OpenHands adapter
                         |
              Docker Agent Server
           conversations + issue workspace
                         |
                 candidate result
                         |
           controller validation + Git publication
                         |
             draft PR + review conversation
                         |
              bounded fix / human handoff
```

The controller runs as a uv-managed host process. Its scheduler polls GitHub
and agent execution state. Agent runs must not block polling or command handling.
Run one controller instance using an exclusive local process lock. SQLite
transactions protect state changes; a database constraint prevents multiple
active dispatches for the same issue revision and role.

All event sources call the same application handler. Polling is sufficient for
the demo. Webhook ingress is optional and requires signature validation when
enabled. Manual simulation uses the same contracts with fake external clients.

## Components and migration from Devin

The existing controller was inspected at
`c434fc053a320d20111c8e46904c62ea42f43570`. Its architecture is a reference;
reuse of source requires a licence check.

| Component | Change for OpenHands |
| --- | --- |
| `devin.py` | Replace with an adapter for conversation creation, observation, continuation, suspension, cancellation, and result extraction |
| `handler.py` | Remove session-tag registry assumptions; dispatch through durable records; enforce approval and budget checks |
| `store.py` | Add dispatch, workspace, review, approval, usage, and publication records; replace ACU fields |
| `reconcile.py` | Replace Devin status, structured-output, message, and review polling with normalised adapter observations |
| `policy.py` | Replace playbook IDs and ACU limits with role configuration, scope restrictions, and run limits |
| `prompts.py` | Define role prompts and typed result contracts; remove instructions giving agents GitHub publication ownership |
| `gh.py` | Retain useful HTTP contracts; add permission checks and controller-owned draft PR operations |
| `projection.py` | Preserve one status comment; show conversation state, cost, checks, and human-action reasons |
| `revision.py` | Preserve deterministic issue revision hashing; record approval revision explicitly |
| `main.py` | Wire local configuration, startup recovery, scheduler, and orderly shutdown |
| New workspace/publication modules | Provision Docker, preserve checkouts, run trusted validation profiles, and publish exact commits |

This is more than renaming the provider client. Workspace management and Git
publication were previously delegated to the hosted agent environment.

## State and dispatch contracts

The main flow is:

`queued → triaging → awaiting-approval → implementing → validating → reviewing → ready-for-human`

Create or update the draft PR after successful validation and before review.
Review findings may send the issue through one fix, validation, and review cycle.
The draft remains a draft until a human takes over.

Additional states are `paused`, `needs-human`, `cancelled`, and `completed`.
Record a reason and resumable stage for human handoffs. Invalid results, exhausted
limits, failed checks after the permitted correction, and uncertain remote state
cannot advance to ready-for-human. Completion requires observing the intended
PR merged. A closed, unmerged PR requires human attention.

Persist these records:

- Workflow: repository, issue, issue revision, pinned base SHA, state, state
  version, approval, review-cycle count, branch, PR URL, and published head SHA.
- Dispatch: unique ID, issue revision, role, attempt, request hash, status,
  conversation ID, workspace ID, timestamps, deadline, and result reference.
- Workspace: container identity, image digest, persistent storage identity,
  checkout/base SHA, and lifecycle status.
- Event: stable source identity, payload hash, processing outcome, and timestamp.
- Usage: dispatch and provider request identities, tokens, reported or estimated
  cost, and accounting status.
- Validation/publication: candidate SHA, check profile and results, operation
  intent, remote branch/PR identity, and reconciliation status.

Store dispatch intent before creating a conversation. Use deterministic external
identity where the selected SDK supports it. Record the returned identifiers
before starting execution. After a crash, reconcile the recorded identity with
the Agent Server and container inventory. If creation may have succeeded but
cannot be resolved, require human recovery. Do not claim exactly-once remote
execution or blindly retry an ambiguous create request.

Polling cursors advance only after events are durably recorded. Reprocess an
overlapping lookback window and deduplicate by event identity. Repeated status
observations and cumulative usage reports must not add cost twice. Stale results
cannot advance a newer issue revision.

## Human approval and control

Triage posts the scope, proposed checks, source revision, and estimated work in
one controller-owned status comment. Authorise commands only when GitHub reports
the actor has write, maintain, or admin permission on the configured fork. An
unavailable permission check fails closed.

Supported commands:

| Input | Effect |
| --- | --- |
| Add `agent:implement` or comment `/agent implement` | Approve the current triaged revision |
| `/agent pause` | Prevent further dispatch and request active execution suspension |
| `/agent resume` | Resume a confirmed paused run if approval and limits remain valid |
| `/agent cancel` | Request cancellation and prevent later dispatch/publication |
| `/agent budget <USD-total>` | Explicitly increase the issue's total allowance; does not itself resume execution |

Approval before triage completes is rejected with a status explanation. Parse
commands as exact standalone commands outside quoted text and code blocks. Record
the command's immutable event identity and actor. Comment edits do not execute
new commands; a fresh comment is required.

For labels, inspect the actual label event and its actor. Current label presence
alone is insufficient evidence of authorisation. Remove the consumed approval
label so a later approval requires a new event. Ignore the controller's own
projection events.

Issue title or description changes invalidate approval and suspend active work.
Ordinary discussion comments do not change the revision. Require new triage and
approval for the updated revision. Resume never restores obsolete approval.

Do not report a run as paused or cancelled until execution is confirmed stopped.
An unresponsive runtime is terminated; recovery may require a new conversation
against the preserved workspace. Shutdown stops dispatch and records pending
runtime state for reconciliation.

## Workspace and Git ownership

Use one persistent Docker workspace per issue, with separate conversations for
triage and implementation. Persist conversation state and checkout data outside
the container's writable layer. Reattach or recreate the container using its
pinned image and storage. Check compatibility before resuming saved state.

Review runs in a separate clean checkout at the exact candidate SHA. It receives
the issue, diff, and validation evidence. Review output contains findings and a
verdict; any edits in the review checkout are discarded.

The controller creates the branch, prepares the checkout, captures the candidate
diff, creates the commit, and performs publication. Agent terminal access is not
a technical prohibition on local Git commands. Verify the expected base and Git
state, and reconstruct the candidate in a controller-owned checkout before
committing. Refuse unexpected history or out-of-scope changes.

Validate candidates in an isolated environment without publication credentials.
Keep the publication checkout separate from agent access. Disable repository
hooks for controller Git operations and do not execute candidate code in the
credentialled publication process. GitHub credentials stay outside agent and
validation containers. Containers receive no host Docker socket or course source
mount. Agent Server authentication and host binding restrict access to the local
controller.

Push only to an explicitly configured demo fork, using a deterministic branch.
Persist publication intent first. After an uncertain push or PR creation, inspect
the remote branch and existing PR before retrying. Unexpected remote head changes
require human attention. Never publish to `apache/superset` automatically.

## Deployment configuration

These are application configuration contracts to implement, not working commands.

| Setting | Value or rule |
| --- | --- |
| Runtime | Local uv-managed Python controller; Docker Agent Server |
| Provider | OpenRouter |
| Model for all roles | OpenRouter identifier `openai/gpt-5.6-terra` |
| Endpoint | `https://openrouter.ai/api/v1` |
| Credentials | Local ignored environment file or process environment |
| Poll interval | 20 seconds |
| Active agent executions | One, across all roles |
| Timeout | 20 minutes per run |
| Iteration cap | 50 per run |
| Issue budget | US$5 across roles, retries, and the fix cycle |
| Automatic fix cycles | One per issue revision |
| Completed workspace retention | 24 hours after workflow completion |
| Failed workspace retention | Until explicit cleanup |
| GitHub writes | Disabled until a demo fork is configured |

Keep model settings separate for each role even though all initially select the
same model. Do not silently switch models. Record the actual model and provider
metadata when available. Map the OpenRouter identifier and credentials to the
selected OpenHands SDK's routing configuration during adapter qualification;
the OpenRouter ID is not assumed to be the SDK's full routing string.

Pin compatible SDK, tools, workspace, and Agent Server releases and the built
container digest. Derive Superset Python, Node, package-manager versions, and
dependency installation from the pinned source revision. Build an image with
both toolchains. Host-managed controller execution is the initial supported
deployment; containerising the controller is a later packaging change.

Track cost before and after each model request. Reserve estimated input/output
allowance where supported, cap response size, and reconcile provider usage.
US$5 is a stopping threshold; in-flight requests may exceed it. Unknown spend
after an interrupted request blocks further calls until accounting is resolved.
Provider-side key limits provide an additional spending control. Automatic
retries consume the same issue budget. A budget increase must be explicit and
audited. Restarting a conversation or changing an issue revision does not reset
the issue's accrued spend.

Before live runs, adapter qualification must demonstrate the per-call budget
gate, iteration and timeout enforcement, usage accounting, and cancellation.
If the selected SDK cannot expose a required gate, adapt its execution boundary
or mark the live profile unsupported. Do not quietly weaken the contract.

## Superset baseline and selected issues

Use the accepted master snapshot
[`c9fd9bf94f45163afd24f39f5ed9eec23a999150`](https://github.com/apache/superset/commit/c9fd9bf94f45163afd24f39f5ed9eec23a999150),
resolved on 21 September 2026. It is a fixed baseline, not a moving `master`
reference. The latest stable application release found during that investigation
was [6.1.0](https://github.com/apache/superset/releases/tag/6.1.0).

| Scope | Source issue | Required reproduction |
| --- | --- | --- |
| Backend | [#44385: stale contextual cache mappings after DELETE](https://github.com/apache/superset/issues/44385) | Create state with a tab context, delete it, create again, and verify a fresh key for dashboard filter state and Explore form data |
| Frontend | [#44466: overlapping stacked-bar value labels](https://github.com/apache/superset/issues/44466) | Render small non-zero segments beside a large outlier; verify the agreed label-legibility behaviour for manual positions |

Both issues were open when checked on 21 September. The frontend issue already
had [PR #44469](https://github.com/apache/superset/pull/44469), and the backend
discussion included contributor interest. These are educational cases against
a fixed snapshot. Do not claim they remain unclaimed or open indefinitely.

Before accepting the fixtures, reproduce both failures and establish focused
regression tests. Source issue claims and suggested patches remain unverified
until this happens. Snapshot the relevant problem descriptions with attribution
for local replay. Avoid supplying upstream solution patches to the implementation
agent; use them separately for comparison. Fork-side issue creation is an
explicit demo setup action after the destination is configured.

## Validation and acceptance

Use controller-owned validation profiles whose commands cannot be replaced by
issue text or agent output. Backend work runs focused Python tests and applicable
lint. Frontend work runs focused tests, applicable lint, and type checks. Changes
spanning both run both profiles. Record baseline failures separately and compare
the exact candidate revision. Unsupported change scopes require human review.

Capture commands, exit codes, logs, source SHA, and image digest. Test additions
must fail on the pinned baseline and pass with the candidate fix. Preserve trusted
regression checks outside agent-writable paths. Existing tests cannot be removed
or weakened to obtain a pass. Frontend label behaviour also needs rendered chart
evidence; a transformer assertion alone does not establish visual legibility.

Accept the controller when deterministic tests demonstrate duplicate delivery,
actor checks, revision invalidation, crash recovery, stale-result rejection,
budget accounting, pause/cancel handling, and publication reconciliation.

Accept the live adapter when a bounded Docker conversation uses the configured
OpenRouter model, produces a validated result, and survives a tested pause/restart
path without duplicate dispatch. Validate failure and unknown-state handling too.

Accept the demo when both issue fixtures produce candidate commits, required
checks, draft PRs in the configured fork, review evidence tied to each head SHA,
and a human handoff. If a run exhausts US$5, show the budget handoff honestly;
that demonstrates controller behaviour but does not count as a completed fix.

## Qualification dependencies

The design fixes responsibility and failure behaviour. Implementation must
resolve release-specific details before enabling the live profile:

- Select compatible pinned OpenHands versions and verify result schemas,
  conversation persistence, workspace reattachment, and cancellation APIs.
- Verify OpenRouter model routing, tool calls, cost reporting, and SDK budget hooks.
- Derive the dual-toolchain image and trusted test commands from the Superset SHA.
- Reproduce the two selected issues and measure whether their scope fits the budget.
- Configure the destination fork and credentials locally. Missing destination
  configuration blocks publication while simulation remains available.

## References

- [Original controller](https://github.com/lspinheiro/devin_superset_automation).
- [OpenHands SDK](https://github.com/OpenHands/software-agent-sdk).
- [Docker workspace example](https://github.com/OpenHands/software-agent-sdk/blob/main/examples/02_remote_agent_server/02_convo_with_docker_sandboxed_server.py).
- [GPT-5.6 Terra on OpenRouter](https://openrouter.ai/openai/gpt-5.6-terra), consulted
  during model selection on 21 September 2026. Availability and pricing must be
  refreshed before live execution.
