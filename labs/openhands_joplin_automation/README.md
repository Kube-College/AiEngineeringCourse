# OpenHands Joplin Automation

This lab runs a local controller that watches issues in your Joplin fork. A new
issue starts an OpenHands triage agent. After triage, you can add a GitHub label
to approve an implementation agent. The controller records each run in SQLite
and shows its progress in a local performance dashboard.

The current live flow ends at `needs-human` after implementation. It keeps the
agent workspace for inspection. Candidate validation, pull request publication,
and automated review are not connected to this live flow yet.

## Set up your fork and credentials

You need Git, [uv](https://docs.astral.sh/uv/getting-started/installation/),
Docker, a GitHub account, and an [OpenRouter](https://openrouter.ai/) account.
The image recipe builds for `linux/arm64` and needs enough Docker disk space for
the Joplin toolchain. Model requests use your OpenRouter account and can incur
charges. The default controller limit is US$5 per issue.

1. [Fork `laurent22/joplin`](https://docs.github.com/en/pull-requests/how-tos/work-with-forks/fork-a-repo)
   into your GitHub account. If your fork has no **Issues** tab, enable Issues
   under **Settings → General → Features**. Your fork is where you will create
   test issues and watch the controller's labels and comments.
2. Create a [fine-grained GitHub personal access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token).
   Select your account as the resource owner, restrict repository access to
   **only your Joplin fork**, and grant **Issues: Read and write**. Set an
   expiration. This live flow uses the token to read issues and label events,
   check approval permissions, and write labels and comments. It does not
   create pull requests.
3. Create a standard [OpenRouter API key](https://openrouter.ai/settings/keys)
   for model calls. The configured default is
   [`openai/gpt-5.6-terra`](https://openrouter.ai/openai/gpt-5.6-terra).
4. Clone this course repository and enter the lab directory:

   ```sh
   git clone https://github.com/Kube-College/AiEngineeringCourse.git
   cd AiEngineeringCourse/labs/openhands_joplin_automation
   uv sync --extra runtime --group dev
   cp .env.example .env
   ```

5. Edit the ignored `.env` file with your own values:

   ```dotenv
   AGENT_BACKEND=openhands
   GH_REPO=YOUR_GITHUB_USERNAME/joplin
   GH_TOKEN=YOUR_FINE_GRAINED_GITHUB_TOKEN
   LLM_API_KEY=YOUR_OPENROUTER_API_KEY
   GITHUB_WRITES_ENABLED=true
   ```

   Keep the other values from `.env.example`, including `LLM_MODEL` and
   `LLM_BASE_URL`. Do not commit `.env` or paste either token into an issue.
   `GITHUB_WRITES_ENABLED=true` lets the controller maintain `agent:state:*`
   labels and post status and agent outcome comments. The dashboard works with
   the same local `STATE_DIR` whether GitHub writes are enabled or not.

## Prepare the pinned Joplin image

Pull the pinned Agent Server base image, then run the lab's build script:

```sh
docker pull ghcr.io/openhands/agent-server@sha256:44426bffabffa704b54a79cfeae71d0af5e702e80ef1b7276861307ecc9d598c
bash scripts/build_joplin_image.sh
```

The script checks out the Joplin commit in `docker/versions.json`, builds the
agent image, verifies its toolchain, and records the local image ID in that
manifest. It currently fetches the pinned source from the course maintainer's
Joplin fork. Your own fork supplies the GitHub issues; the agent inspects the
pinned source inside the image.

## Run one issue through the agents

Start the controller from the lab directory:

```sh
make run
```

Wait for `Watching YOUR_GITHUB_USERNAME/joplin ...` in the terminal. Then create
a **new** issue in your fork with a concrete Joplin problem and steps to
reproduce it. The first start records a watch start time, so older unknown
issues are skipped. The controller polls every 20 seconds by default. Watch
the terminal, issue labels, and comments for `queued`, `triaging`, and
`awaiting-approval`.

For a repeatable first issue, use the case in
[`fixtures/issues/16638.json`](fixtures/issues/16638.json):

```text
Title: Preserve underscores in generated note titles

When a note's first body line is YYYY_MM_, the generated title is YYYYMM.
Expected: the generated title preserves YYYY_MM_.
```

Once the issue reaches `awaiting-approval`, add the `agent:implement` label to
that issue. If the label does not exist, create it in your fork's **Issues →
Labels** page first. The controller accepts a **new label-addition event** from
a user with write access to the fork. It removes the approval label after
consuming it and starts the implementation agent once. A label already present
before the approval state does not trigger implementation. The controller's
`agent:state:*` labels display state; changing them does not start an agent.

The implementation run ends at `needs-human`. Inspect the outcome comment and
saved workspace before deciding what to do with the proposed changes. Stop
the controller with Ctrl-C. Restarting it replays known issues and events
without starting duplicate runs. SQLite and runtime authentication files live
under the ignored `STATE_DIR`; agent workspaces live under `WORKSPACE_DIR`.

## Open the local control plane

Keep the controller running. In a second terminal in the same lab directory,
start the read-only dashboard:

```sh
make dashboard
```

Open <http://127.0.0.1:8765>. If that port is in use, run
`uv run controller dashboard --port 8767` and open
<http://127.0.0.1:8767>. Both processes read `STATE_DIR` from `.env`.
Select an issue to see workflow transitions, agent runs, elapsed time, model
cost, configuration hashes, validation records, and redacted agent activity.
The browser receives no Agent Server token or raw agent messages. The
[performance console guide](docs/performance-console.md) explains each field
and the `controller rate` command for recording your assessment of a run.

## Configure agents in the registry

[`src/openhands_controller/runtime/agents.py`](src/openhands_controller/runtime/agents.py)
is the declaration point for each role's tools, prompt, skills, and optional
model. The `AGENTS` registry declares `triage`, `implementation`, `fix`, and
`review`. The live issue flow currently dispatches triage and implementation.

To change a role, edit its `AgentProfile` entry. Its `tools` tuple names
OpenHands tools, `prompt` names a file under
[`runtime/agent_content/`](src/openhands_controller/runtime/agent_content/),
and `skills` names Markdown files under `runtime/agent_content/skills/`.
[`common.md`](src/openhands_controller/runtime/agent_content/common.md) applies
to every role. The role prompt and common instructions are added to the
OpenHands system context. Issue details and result requirements remain in
[`runtime/prompts.py`](src/openhands_controller/runtime/prompts.py).

For example, a role can select a different OpenRouter model:

```python
Role.REVIEW: AgentProfile(
    "review.md",
    ("terminal",),
    ("joplin-repository.md",),
    model=ModelRoute("provider/model-id", Decimal("3"), Decimal("15")),
),
```

The Decimal values are conservative input and output rates in USD per million
tokens for budget reservation. Check the chosen model's current OpenRouter
pricing before setting them. Roles without a model override use
`openai/gpt-5.6-terra`. Restart the controller after editing a declaration or
instruction file. The dashboard's profile hash helps identify which
configuration ran. Tool selection controls what the agent sees; terminal
access can still change files.

## Test the controller without credentials

The SQLite simulation runs without GitHub, Docker, or an OpenRouter key:

```sh
uv run controller simulate --state-dir .data/simulation --scenario happy
uv run pytest -q
```

The simulation uses fake delivery and model results. The test suite covers
the controller, GitHub projection, agent registry, and dashboard. The lab has
its own `pyproject.toml` and `uv.lock`.
