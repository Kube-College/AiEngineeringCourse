# Week 2 lab: Configure, Calibrate, Review, Deliver

Week 2 configures a coding agent for your project. Whatever you did in Week 1, from a vibe-coded prototype you explored in detail to a chosen idea and some research, the agent has had no project instructions so far. This week you configure it: an instruction file, a skill, a reviewer subagent with a gate, and one MCP connection. Then you implement one small behaviour test-first with the configured agent and open a pull request.

The seminar covered five configuration mechanisms: **instructions**, project rules in AGENTS.md or CLAUDE.md; **hooks**, actions that run at particular moments, such as after a file edit; **subagents**, helpers with a clear job and the tools they can use; **MCP**, tools and information from other systems; and **skills**, packaged instructions and procedures for recurring tasks. Each stage below covers what you configure, where you put it, and how it changes the agent's behaviour. The lab's task focus is test-first development: on one bounded ticket, the agent writes a failing test, makes it pass, and reports the evidence. Week 3 replaces the ticket with a specification, and Week 4 uses the gate as one feedback channel in a delivery loop.

## Outcomes

By the end of Week 2, including any take-home part, you should have:

- a short list of the project decisions and known failure modes the agent should be told about, each assigned to the mechanism that implements it;
- an instruction file under 60 lines that states commands, the test-first rule, two or three design constraints, and boundaries;
- evidence that the instruction file loaded and that the agent follows it, from three adherence probes;
- a skill that formalises one workflow, by default `tdd-slice`, with a recorded trigger test;
- a read-only reviewer subagent and a gate that requires passing tests and a reviewer verdict before a turn that changed code can end;
- one MCP server connected because the project lacked a capability, with the choice justified against a CLI alternative;
- one deferred behaviour implemented through the configured agent, with an annotated trace; and
- a pull request containing the configuration, the implementation, your notes, and a review gate you can defend.

The lab is ungraded. The pull request gives you and the instructor a concrete surface for feedback.

## Materials

### Prerequisites

Complete these before the session. Setup problems in class take time away from the lab.

- Your project has a GitHub repository, even if it only holds a README.
- Your coding agent is installed and authenticated inside the project folder.
- The GitHub CLI is installed and `gh auth status` reports a logged-in account.
- A running prototype of your project, or 30 minutes reserved in stage 1 to vibe code one.
- Whatever else Week 1 produced is to hand: notes, a decision list, journey test results, or the research you did on the idea. Stage 1 starts from it.
- Optional pre-work: if you already have a prototype and know which user story or design aspect you want to validate, write the calibration ticket before class. See the calibration ticket section below.

### Reference client

The instructions use Claude Code file names and commands because the seminar used them. Other clients support the same mechanisms with different files. Hooks and subagents have no cross-tool standard, so those two stages need the most adaptation.

| Mechanism | Claude Code | Codex CLI | Cursor | Gemini CLI |
| --- | --- | --- | --- | --- |
| Instruction file | `CLAUDE.md`, which can import `AGENTS.md` with `@AGENTS.md` | `AGENTS.md` | `AGENTS.md` or `.cursor/rules/` | `GEMINI.md`, or add `AGENTS.md` to `context.fileName` |
| Skill | `.claude/skills/<name>/SKILL.md` | `.agents/skills/<name>/SKILL.md` | `.cursor/skills/`; also reads `.claude/skills/` | `.gemini/skills/` or `.agents/skills/` |
| Subagent | `.claude/agents/<name>.md` | `.codex/agents/<name>.toml` | `.cursor/agents/`; also reads `.claude/agents/` | `.gemini/agents/<name>.md` |
| Hook | `hooks` in `.claude/settings.json` | Check the client documentation | Check the client documentation | Check the client documentation |
| MCP | `.mcp.json` | `.codex/config.toml` | `.cursor/mcp.json` | `.gemini/settings.json` |

If your client has no hook mechanism, make the reviewer call the last step of the skill in stage 3 and skip the gate script in stage 4. Note the substitution in your notes.

### Playbooks and documentation

- Software Design and Production Playbook, available on the course Moodle: the source for the design constraints in stage 2.
- Prompt Engineering Playbook, available on the course Moodle: use it when writing the skill body and the reviewer criteria.
- Client documentation for each mechanism. Claude Code: [instruction files](https://code.claude.com/docs/en/memory), [best practices](https://code.claude.com/docs/en/best-practices), [skills](https://code.claude.com/docs/en/skills), [subagents](https://code.claude.com/docs/en/sub-agents), [hooks](https://code.claude.com/docs/en/hooks), [MCP](https://code.claude.com/docs/en/mcp), [permissions](https://code.claude.com/docs/en/permissions).
- The [AGENTS.md format](https://agents.md/) and the [Agent Skills specification](https://agentskills.io/specification).

Each stage lists references in three groups. **Read** is the documentation for the mechanism. **Imitate** is a real repository whose file has the right shape for a small single-repo application; copy the shape, never the content. **Critique** is a file with a visible weakness; name the weakness before you write your own.

### The calibration ticket

The ticket is the one behaviour the configured agent implements in stage 6, and the target every stage is calibrated against. It comes from a product or design question, not from a to-do list. Stage 1 walks through the four steps; they are stated here so that students who already have a prototype can do them before class.

1. **Have a prototype.** If Week 1 did not produce one, vibe code one in acceleration posture for 20 to 30 minutes, following stage 2 of the Week 1 guide. It only needs to run well enough that a journey can be attempted. Week 1 used the vibe-coded spike as the control condition to be studied afterwards. Here it is the quickest way to get something to experiment on.
2. **Choose what to validate.** A user story or journey from your project brief's intended users and end-of-course requirements, or a system-design aspect from the Software Design and Production Playbook: where state lives, what a repeated request does, the boundary between domain logic and the interface, an invariant the product must hold. The brief's "Questions to carry forward" are candidates.
3. **Experiment around it** against the running prototype: the expected path, the repeat, the edge case, the competing action. Note where it fails, where the behaviour is undefined, and where it works by accident.
4. **Write the ticket** as a GitHub issue titled `Week 2: calibration ticket`:

   - Story or design aspect it validates:
   - What the prototype did when I tried it:
   - Acceptance statement (one line a unit test can encode):

   Keep it testable below the HTTP layer in under thirty minutes. The journey-level acceptance test comes in Week 3.

Examples:

| Project | Story or design aspect | Calibration ticket |
| --- | --- | --- |
| Event Booking and Waitlist | Design aspect: a repeated request must not create two registrations | Registering twice for the same session is rejected and capacity is unchanged |
| Support Ticket SLA and Escalation | Story: a support lead sees which tickets are approaching their response commitment | The first-response deadline is computed from severity at submission |
| Inventory Reservation and Fulfilment | Design aspect: reserved stock never exceeds stock on hand | Reserving more than the available quantity is rejected and stock is unchanged |
| Multimodal AI Companion | Design aspect: the context sent to the model is bounded | The conversation history sent to the model is truncated to the last N turns |

The instruction file describes the repository the ticket lives in, the skill implements it, the reviewer checks its diff, the docs server answers a question it raises, and the GitHub route opens its pull request.

### The test-first evidence checklist

The checklist is used three times: as the reviewer's criteria in stage 4, to score the delivery run in stage 6, and in the pull request review gate.

1. A failing test that names the behaviour exists before the implementation, visible in the transcript or as a separate commit.
2. The project's test command was run and its output reported, before and after the change.
3. The change lives in the layer your instruction file names for that behaviour.
4. The implementation is the smallest that passes, and no unrelated files changed.
5. A refactor step, if any, left the tests passing.

## Lab flow

| Stage | Where | Time | Result |
| --- | --- | --- | --- |
| 1. Prototype, choose, experiment | In class | 30 min | The calibration ticket, and a list of decisions and failure modes, each assigned to a mechanism |
| 2. Instruction file | In class | 30 min | `AGENTS.md` and a `CLAUDE.md` shim; three adherence probes recorded |
| 3. Skill | In class | 35 min | One skill, by default `tdd-slice`; a trigger test recorded; one revision from an analysis of the tests it wrote |
| 4. Reviewer and gate | In class | 30 min | A read-only `tdd-reviewer` subagent; a gate that blocks once and passes once |
| 5. MCP | In class | 20 min | One server connected for a missing capability; one route comparison (GitHub or Playwright) measured and decided |
| 6. Deliver | In class or take home | | The calibration ticket implemented through the skill; a pull request with the configuration, notes, and trace |
| 7. Discuss | In class | 15 min | Which mechanism changed behaviour, and which changed cost |

Stages 1 to 5 are the in-class core. Stage 6 is the deliverable that Week 3 depends on. Each stage gives one suggested implementation and one open question. The suggestion demonstrates the mechanism. The question is yours to decide and test.

## 1. Prototype, choose, experiment

Until now the agent has worked on your project with no general project instructions. This stage produces the two inputs for the rest of the lab: the calibration ticket, and the list of decisions and failure modes that the instruction file and the other mechanisms will carry. Both come from the same activity, experimenting with a running prototype around one user story or design aspect.

Follow the four steps in the calibration ticket section. If you did them before class, go straight to the experiment and extend it. Where you start depends on how far Week 1 went, and both starting points are fine.

**If you have a prototype**, from Week 1 or from step 1 just now, experiment around the story or design aspect you chose, then run three prompts against the prototype with your agent:

1. "List every library and framework this code uses, with the version it assumes. For each, say whether the API it calls matches the current documentation or an older version."
2. "List the behaviours this code implements that have no test, and the behaviours that a test would have caught as wrong. Start with <the story or design aspect>."
3. "Compare the structure of this code with the decisions I have written down. List every place where the code deviates: runtime, layout, where domain logic lives, or how state is stored." If nothing is written down yet, ask instead: "List the structural decisions this code makes that nobody told you to make."

What the prototype did when you tried the journey, and what these prompts return, are the failure modes. If Week 1 already produced an assumptions register and journey test results, they belong on the list too.

**If you chose an idea and did some research** and would rather not prototype, you have decisions rather than failures. Write down the ones you consider important: the runtime and framework, where domain logic will live, how state is stored, how tests run, and anything you have decided not to do. Then ask the agent one question: "Given these decisions, what would you still have to guess to add a feature to this project?" The answers go into the instruction file. Your calibration ticket is then the first rule inside your chosen story or design aspect that the product cannot work without.

Either way, write a short list. It does not have to be complete, and the format is up to you. Stages 2 to 5 use the last column: which mechanism implements each item.

```md
| # | Decision or failure mode | Where it came from | Mechanism |
| --- | --- | --- | --- |
| 1 | No tests for any behaviour | prototype has no test directory | Instruction file (rule) + skill (procedure) |
| 2 | Uses a deprecated API of <library> | prompt 1 answer | MCP (docs server) or the library's CLI |
| 3 | Domain logic lives in src/domain, not in request handlers | my decision | Instruction file, with the reason |
| 4 | Never write a real credential into a config file | it happened in the prototype | Permission deny rule + boundaries line |
```

Use this rule to fill the mechanism column:

- A fact the agent could not know, such as the test command, the layout, or a stack choice: **instruction file**.
- A procedure that repeats across tasks, such as how to implement a slice test-first: **skill**.
- Something that must always or never happen, such as running tests before finishing or editing a secrets file: **hook** or **permission rule**. An instruction is guidance the model interprets; a hook or permission rule is applied by the client.
- A capability the agent lacked, such as current documentation or the issue tracker: **MCP server** or **CLI**.

Open question for this stage: did the experiment validate what you set out to validate, or did it change the question? And which item on your list would have changed the most in Week 1 if the agent had known it?

## 2. Write the instruction file

The instruction file sets the project rules. Start from your README and the stage 1 list. Write down the decisions you consider important, then check in the agent's output whether it followed them.

**Read.** The [Claude Code best practices](https://code.claude.com/docs/en/best-practices) include-and-exclude table and its test for each line: would removing it cause the agent to make mistakes? The [AGENTS.md format](https://agents.md/). HumanLayer, [Writing a good CLAUDE.md](https://www.humanlayer.dev/blog/writing-a-good-claude-md), 25 November 2025: under 300 lines and shorter is better, leave style to linters, point at files rather than pasting code.

**Imitate.** [documenso `AGENTS.md`](https://github.com/documenso/documenso/blob/main/AGENTS.md), 59 lines: one line per command with its purpose and a cost warning about the slow build. [twenty `CLAUDE.md`](https://github.com/twentyhq/twenty/blob/main/CLAUDE.md), 52 lines: only what differs from defaults, each with a reason. [cal.diy `AGENTS.md`](https://github.com/calcom/cal.diy/blob/main/AGENTS.md): the Always / Ask first / Never block is the part to copy; the rest is too long. [cloudflare/workers-sdk `AGENTS.md`](https://github.com/cloudflare/workers-sdk/blob/main/AGENTS.md): the preamble that prefers pointing at authoritative configuration over copying it, and the five-line `CLAUDE.md` that imports it.

**Critique.** [temporalio/temporal `AGENTS.md`](https://github.com/temporalio/temporal/blob/main/AGENTS.md): mark which lines are repository knowledge and which are generic coaching copied from a system prompt. The first 60 lines of [withastro/astro `AGENTS.md`](https://github.com/withastro/astro/blob/main/AGENTS.md): the same exercise, then notice the one-line style section that delegates to the linter.

Two 2026 studies measured instruction files on real repositories and found no general gain in task success and a cost increase of over 20 % ([Gloaguen et al., arXiv 2602.11988](https://arxiv.org/abs/2602.11988), revised June 2026; [Khatri, arXiv 2607.27250](https://arxiv.org/abs/2607.27250), July 2026). Both found that the files help when they state non-standard practices. Overviews the agent can derive from the code cost tokens and change nothing. Those studies used larger files and more complex tasks. The lab does not ask for a measurement. Note what changed in the agent's output after you wrote the file.

### Suggested implementation

Write `AGENTS.md` at the repository root, under 60 lines, and a `CLAUDE.md` containing the single line `@AGENTS.md`. Adapt the skeleton; every line must be true of your repository.

```md
# <Project name>

<One paragraph: what the product is, the runtime and framework, and where domain logic lives.
If you keep a decision log, link it rather than repeating it.>

## Commands

- Install: `<command>`
- Test: `<command>` (<how long it takes; whether a filtered form exists>)
- Smoke check: `<command>`
- Start: `<command>`

## Test-first rule

A behaviour change starts with a failing test that names the behaviour. Run the test command
before and after the change and report its output.

## Constraints

- <A structural decision you made, with its reason.>
- <A constraint from the Software Design and Production Playbook, with its reason.>
- <One gotcha the prototype revealed, or a mistake you want to rule out, with its reason.>

## Boundaries

- Always: run the test command before saying a task is done.
- Ask first: adding a dependency; changing the schema; touching <directory>.
- Never: edit `.env` or commit credentials; run <destructive command>.

## Further reading

- <docs/decisions.md or wherever you keep decisions and their reasons, if anywhere>
```

Add a permission deny rule in `.claude/settings.json` for the Never lines the client can apply, such as reads and edits of `.env`. The Boundaries line is guidance the model interprets; the permission rule is applied by the client.

### Verify

Confirm the file loaded, then inspect what the agent did. Loading proves availability, not adherence. In Claude Code, run `/context` and check that `AGENTS.md` appears through the import. Then run three adherence probes in a fresh session and note the answers. Each probe targets one rule:

1. "Where should a new validation rule for <the calibration behaviour> live, and which command checks it?" (targets the layout constraint and the test command)
2. "I want to add <a library you have decided against, or one the prototype used wrongly>. What do you do first?" (targets the Ask first boundary)
3. "Implement <a trivial one-line change> and tell me when it is done." (targets the test-first rule and the Always line: did it run the tests?)

An answer that names the wrong layer or skips the test is a finding. Rewrite the line it should have followed, then rerun the probe.

Open question for this stage: which constraint from the playbook matters most for this project, and how would you know from a transcript that the agent followed it?

## 3. Package the procedure as a skill

A skill packages a task-specific procedure that is loaded when the task calls for it. Here the procedure is implementing a ticket test-first and reporting the evidence. The instruction file keeps the one-line rule; the skill holds the steps.

**Read.** The Agent Skills [specification](https://agentskills.io/specification) and its [best practices for skill creators](https://agentskills.io/skill-creation/best-practices): add what the agent lacks, omit what it knows; provide defaults, not menus; favour procedures over declarations. The [Claude Code skills page](https://code.claude.com/docs/en/skills) has a table on when to use a skill, the instruction file, MCP, or a hook. Keep the frontmatter to the specification's fields unless you need a client-only feature. Dan Luu, [How well do agents use test/verification techniques?](https://danluu.com/agentic-testing/) (2026): across 26 prompt conditions on one implementation task, naming a technique such as TDD, property-based testing, or formal verification did not improve correctness; agents wrote the tests they would have written anyway inside the named framework. The tuning step below uses its list of failure modes.

**Imitate.** [getsentry/sentry `generate-migration`](https://github.com/getsentry/sentry/tree/master/.agents/skills): a short description that says when to use it, a numbered procedure with verification commands, and project gotchas. [anthropics/skills `webapp-testing`](https://github.com/anthropics/skills/tree/main/skills/webapp-testing): a skill that runs a script and uses only its output. [cloudflare/skills `wrangler`](https://github.com/cloudflare/skills/blob/main/skills/wrangler/SKILL.md): a single file with an explicit Validate section. [openai/codex `test-tui`](https://github.com/openai/codex/tree/main/.codex/skills): about 15 lines, which shows how small a useful skill can be.

**Critique.** [stripe/ai `upgrade-stripe`](https://github.com/stripe/ai/blob/main/skills/upgrade-stripe/SKILL.md): a good eight-step body under a one-line description. Rewrite the description so a model could pick it over a neighbouring skill.

### Suggested implementation

The suggested skill is `tdd-slice`. It takes one issue number or one-line behaviour statement and implements it as a **test-first slice**: a failing unit test that names the behaviour, the smallest change that makes it pass, a refactor only if the change made the code worse, the smoke check, and a report of the test outputs and the changed files. It then hands the diff to the reviewer from stage 4. That is the part of test-driven development this lab recommends: red, green, refactor at the unit level on one bounded ticket. Acceptance tests and specifications come in Week 3, and the delivery loop in Week 4.

Write the skill yourself. The Read references give the format and the Imitate examples give the structure. Decide what the description says so the skill is invoked for the right requests, and what the body asks the agent to report back.

A different workflow may fit how you work better. Any repeated procedure with a checkable result is a candidate: adding a database migration, writing an acceptance test for a user journey, running the smoke check and reporting the result, or preparing a pull request description. If you choose one of these, keep the test-first rule in the instruction file, and use the skill you wrote to deliver the calibration ticket in stage 6.

### Verify

The description routes a task to the skill. Check the routing before checking the procedure: write three prompts the skill should handle and three near misses it should not respond to, run each in a fresh session, and record which invoked the skill. The prompts below are for a test-first slice; write your own for a different workflow.

```md
| Prompt | Should trigger? | Did it? |
| --- | --- | --- |
| Implement issue #12 | yes | |
| Add a check that a session cannot be over-booked | yes | |
| Fix the deadline calculation for severity 1 tickets | yes | |
| Rename the sessions table to events | no | |
| Update the README setup section | no | |
| Explain how registration works | no | |
```

Then invoke the skill on a small change and check that the report it returns contains what you asked for. A missing item is a finding about the skill body.

### Tune the skill against the tests it writes

The first version of a skill states the procedure. The second version states what a good result looks like, because the agent's default output has predictable defects. Dan Luu's article lists the defects he measured in agent-written tests. The ones that apply to a unit test for your calibration ticket:

- the test asserts what the implementation returns rather than what the behaviour requires, so it passes whatever the code does;
- the inputs are symmetric or identical, so an ordering or reversal bug produces the same output and the test passes;
- many small trivial tests and no test for the case most likely to be wrong;
- random inputs that are mostly invalid and exercise one rejection path;
- the expected result is copied from the code under test rather than derived independently; and
- the risky area is named in the agent's reasoning and then not tested.

Run this loop once:

1. Run the skill on the calibration ticket, or on a small change, and keep the test file it wrote.
2. In a fresh session, ask the agent to analyse that test file against the list above and the article: for each item, does the test have the defect, and what input or assertion would fix it? The reviewer subagent from stage 4 is suited to this, because it does not carry the context in which the test was written.
3. Revise the skill body with the findings as concrete instructions. Two that the article's own instructions used: before writing the test, name the part of the change most likely to be wrong and the plausible alternative interpretations, then write a check whose result differs between them; and derive the expected value without reading the implementation.
4. Run the revised skill on the same change and compare the two test files.

Record both test files and the analysis in your notes. The article found that the same instruction has a different effect depending on when the agent reads it and how much else is in context, so the second run may not improve on every item. Note what improved, what did not, and what you would change next.

Open question for this stage: what moved out of the instruction file into the skill, and what had to stay?

## 4. Add a reviewer and a gate

The subagent definition fixes a reusable role: a reviewer with read and search tools and no editing. The assignment supplies the task-specific evidence, the issue and the changed files, because the subagent does not receive the conversation. The gate is a Stop hook that blocks the turn while code changed and no verdict was reported.

**Read.** [Claude Code subagents](https://code.claude.com/docs/en/sub-agents): the frontmatter fields, and the subagent's starting context: its own prompt, the delegation message, and the instruction files. The [adversarial review section of best practices](https://code.claude.com/docs/en/best-practices): a reviewer asked to find gaps will find some in sound work, so restrict it to correctness and test-discipline gaps and say that a clean result is valid. [Hooks](https://code.claude.com/docs/en/hooks): a command hook receives event JSON on stdin and blocks with exit code 2; it can return a message but cannot itself spawn a subagent.

**Imitate.** [woocommerce-paypal-payments `.claude/agents/`](https://github.com/woocommerce/woocommerce-paypal-payments/tree/trunk/.claude/agents): `ci.md` is a 30-line verifier with `Bash(ddev npm run *)` and a one-line pass/fail format; `php-review.md` is a reviewer with `Bash(git diff *)`, a description that states how to invoke it, and a `CLEAN` or `REVIEW` verdict. [claude-plugins-official `feature-dev/agents/code-reviewer.md`](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/feature-dev/agents): a read-only tool set and a confidence threshold.

**Critique.** [VoltAgent/awesome-claude-code-subagents `code-reviewer.md`](https://github.com/VoltAgent/awesome-claude-code-subagents): a reviewer granted `Write`, `Edit`, and `Bash`, about 900 words, no output format. Name the three problems before writing yours.

### Suggested implementation: the reviewer

Create `.claude/agents/tdd-reviewer.md`.

```md
---
name: tdd-reviewer
description: Reviews a diff for test-first evidence and this repository's design constraints. Invoke with the issue number and the list of changed files. Returns CLEAN or REVIEW with file:line findings. Never edits.
tools: Read, Grep, Glob, Bash(git diff *), Bash(git log *)
model: inherit
maxTurns: 15
---

You review one change against the test-first evidence checklist and the constraints in AGENTS.md.
You cannot see the conversation. The assignment gives you the issue number and the changed files.
Run `git diff` yourself for the content.

Check, in order:
1. A test that names the behaviour exists and would fail without the implementation.
2. The change lives in the layer AGENTS.md names for it.
3. No files changed outside the slice.
4. No constraint in AGENTS.md is violated.

Report correctness and test-discipline gaps only. Style is the linter's job.
CLEAN is a valid result; do not invent findings.

Output format:
Verdict: CLEAN | REVIEW
Findings (REVIEW only), one per line: file:line - what is wrong - why it matters - the smallest fix
```

The reviewer has no `Edit` or `Write` tool and only two shell commands. It cannot run the tests; the gate does that. Tool restrictions limit what the reviewer can do inside the client and do not isolate it from the operating system.

### Suggested implementation: the gate

The [examples/review-gate](examples/review-gate/) folder contains a settings fragment and three short scripts:

- `mark-changed.sh` runs after every `Edit`, `Write`, or `MultiEdit` and records that code changed this turn.
- `clear-on-review.sh` runs after every subagent call and clears the record when the subagent was `tdd-reviewer`.
- `stop-gate.sh` runs when the turn is about to end. If code changed, it runs the test command and blocks on failure. If the tests pass but no reviewer verdict was recorded, it blocks with a message asking for the reviewer. After three blocks in one turn it lets the turn end with a warning, so the gate cannot block without end.

Copy the scripts into `.claude/hooks/`, set the test command at the top of `stop-gate.sh`, merge the fragment into `.claude/settings.json`, and add `.claude/state/` to `.gitignore`. Read every line before you install it. The scripts run with your permissions.

### Verify

Trigger one block and one pass, and keep the transcript lines for the annotated trace in stage 6:

1. Ask the agent to make a small code change and say when it is done. The gate should block the turn and the agent should invoke the reviewer. Record the block message and the reviewer's verdict.
2. Ask a question that changes no code. The turn should end without the gate firing.
3. Break a test deliberately and ask for a change. The gate should block on the failing test before asking for the reviewer.

Run `/hooks` to confirm the three hooks are registered, and read the reviewer's returned message rather than the agent's summary of it.

Open questions for this stage: what evidence does the parent have to pass to the reviewer, given that the reviewer cannot see the conversation? When should the gate not fire? What should happen when the reviewer and the tests disagree?

## 5. Connect a missing capability

Stage 1 may have identified capabilities the agent lacked. Two are common: current documentation for a library you use, and the issue tracker where the calibration ticket lives. This stage connects one server for the first and compares two routes for the second.

**Read.** [Claude Code MCP](https://code.claude.com/docs/en/mcp): the three scopes, the `.mcp.json` format, `${VAR}` expansion, and the approval prompt for project servers. The [Local MCP Server Compromise section of the MCP security best practices](https://modelcontextprotocol.io/specification/draft/basic/security_best_practices): why the client asks before running a server from a repository. [Managing costs](https://code.claude.com/docs/en/costs): a CLI such as `gh` adds no per-tool listing and costs less context than a server.

**Imitate.** [getsentry/sentry-mcp](https://github.com/getsentry/sentry-mcp): the same server committed in `.mcp.json`, `.cursor/mcp.json`, `.vscode/mcp.json`, and `.codex/config.toml`, with a `sentry-dev` entry pointing at a local port. No secrets in any of them.

**Critique.** The [archived reference servers](https://github.com/modelcontextprotocol/servers-archived): `server-postgres`, `server-github`, `server-sqlite`, and `server-puppeteer` were archived in May 2025 with no security guarantees and still appear in tutorials. Check the date on any server a search result recommends.

### Suggested implementation: a documentation server

Add [Context7](https://github.com/upstash/context7) at project scope:

```json
{
  "mcpServers": {
    "context7": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp"]
    }
  }
}
```

Pick a library from your stage 1 list, or your test framework. Ask the same question twice in fresh sessions: once with the server disabled, once with it enabled. A question with a checkable answer works best, such as "What is the current way to stub an environment variable in <framework> <version>, and which call resets it?" In the second transcript, find the two tool calls the server made (one to resolve the library, one to query its documentation) and note what came back. Run `/context` and record what the server adds to the context before any tool is called.

### Suggested implementation: the GitHub route

This comparison is the default. Students whose calibration ticket has a user-interface journey can run the Playwright comparison below instead, and use the `gh` CLI for the pull request without measuring it.

The calibration ticket is a GitHub issue and stage 6 ends with a pull request. There are two routes: the `gh` CLI, or the [GitHub MCP server](https://github.com/github/github-mcp-server) over HTTP with OAuth. Predict first, then measure.

1. Write down which route you expect to use fewer tool calls, fewer permission prompts, and fewer tokens for the task "read the calibration issue and summarise its acceptance statement".
2. Run the task with `gh` available and the server absent. Count tool calls and prompts; read `/usage` for the session.
3. Add the server (`claude mcp add --transport http --scope project github https://api.githubcopilot.com/mcp/` then `/mcp` to log in), start a fresh session, and repeat.
4. Choose one route for the rest of the course and note the decision and the numbers, in your decision log if you keep one or in your Week 2 notes.

### Alternative comparison: Playwright MCP versus the Playwright CLI

If your ticket has a journey a browser can exercise, compare two ways of verifying it against the running application. With [Playwright MCP](https://github.com/microsoft/playwright-mcp) (`claude mcp add --scope project playwright npx @playwright/mcp@latest`), the agent drives the browser during the session through the accessibility tree. With the Playwright CLI, the agent writes a test file and runs `npx playwright test`. Give both routes the same task: "Verify that <the journey> works against the application running on localhost, and report what you observed." Predict first, then record tool calls, permission prompts, tokens from `/usage`, and what remains after the session: a transcript, or a test file that can run again in CI. Record which route you keep and why.

An issue read through either route is untrusted text entering the session. If you keep the server, run it read-only where the client supports it, and do not combine it with a server that can send data out of the session. Simon Willison calls the combination of private data, untrusted input, and an outbound channel [the lethal trifecta](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/) (16 June 2025).

Open question for this stage: which capability did the project lack, and did the server supply it more cheaply than a CLI or a skill would have?

## 6. Deliver the calibration ticket

Implement the calibration ticket through the configured agent. This stage can finish at home. Complete it before the Week 3 session.

1. Create a branch `week-02-<slug>` from `main`.
2. Start a fresh session. Invoke your skill with the issue number.
3. Let the gate and the reviewer run. Read the reviewer's returned message yourself.
4. Score the run against the test-first evidence checklist. Record the turn count and the session figures from `/usage`.
5. Read the diff before committing. Anything you cannot explain does not get committed until you can.
6. Commit the configuration files and the implementation separately.

### Write the annotated trace

Copy ten to twenty lines of the transcript that show the configuration working, and annotate each in one sentence: the skill loading, the failing test run, the gate blocking, the reviewer call and its verdict, and any MCP tool call. The trace is the evidence that the mechanisms ran, and it is the part of the pull request the instructor reads first.

### Write your notes

Keep them short and informal. Put them in `docs/week-02-notes.md` or wherever your project keeps notes. A structure that covers everything:

```md
# Week 2 notes

## What I started from
- Week 1 state: prototype explored / prototype only / idea and research / prototyped in class
- Story or design aspect chosen, and what the prototype did when I tried it
- The list from stage 1

## Instruction file
- Lines: ___
- Loaded (how verified):
- Adherence probes: (three prompts, three answers, what changed as a result)
- Design constraints chosen and why:
- Did the instruction file change the outcome? What you observed, in your own words:

## Skill
- Trigger test: (the table from stage 3)
- What the first run left out of its report, and the fix:
- Test-quality analysis: the defects found in the first test file, the instructions added to the skill, and what changed in the second test file

## Reviewer and gate
- Reviewer tools and why each is there:
- One observed block (message and what the agent did next):
- One observed pass:
- Substitution used, if the client has no hooks:

## MCP
- Documentation server: question, answer without, answer with, tool calls observed, context cost
- Comparison run (GitHub or Playwright): prediction, measured tool calls / prompts / tokens for each route, what each route left behind, decision

## Delivery run
- Branch and issue:
- Story or design aspect the ticket validates:
- Checklist score: ___ / 5, with the failing item explained
- Turns and session figures:
- Annotated trace: (ten to twenty lines)

## Justification
- One line per configuration file: what it changes and how I checked it
- The configuration change I would remove first, and why
- Question to carry into Week 3:
```

### Open the pull request and pass the review gate

Push the branch and open a draft pull request linked to the calibration issue. Include:

- the configuration files: `AGENTS.md`, `CLAUDE.md`, `.claude/settings.json`, `.claude/hooks/`, `.claude/skills/<your skill>/`, `.claude/agents/tdd-reviewer.md`, and `.mcp.json` with no secrets;
- the implementation and its test;
- your Week 2 notes with the annotated trace; and
- the reviewer's verdict, pasted verbatim.

Add the review gate to the description and complete it honestly:

```md
## Review gate

- Files generated by the agent:
- Files I can explain line by line:
- One thing I checked by hand, and how:
- What I would not merge yet, and why:
- The configuration change I would remove first, and why:
```

Mark the pull request ready for review only when you can answer every line. Ask a peer to review it. The reviewer asks the questions from the seminar: why is each configuration file there, what would change if it were removed, and how did you verify it took effect.

## 7. Group discussion

In groups of three, discuss:

1. Did the ticket validate what you set out to validate, or did the experiment change the question?
2. Which item from your stage 1 list did the configuration change, and what in the agent's output shows it?
3. Which adherence probe failed first, and what did you change in the file?
4. What did the reviewer find that you would have missed, and what did it report that was not a real problem?
5. When did the gate fire when it should not have, and what would you change?
6. In the route comparison, which route used fewer tool calls and tokens, and did the numbers match your prediction?
7. Which defect in the first test file did the revised skill remove, and which did it not?
8. Which mechanism changed the agent's behaviour, and which only changed the cost?

## Completion checklist

### Core

- [ ] The calibration ticket names the story or design aspect it validates and what the prototype did.
- [ ] The stage 1 list assigns each decision or failure mode to a mechanism.
- [ ] `AGENTS.md` is under 60 lines, `CLAUDE.md` imports it, and the load was verified.
- [ ] Three adherence probes were run and recorded, with at least one rewrite.
- [ ] A permission rule enforces at least one Never line.
- [ ] One skill exists and its trigger test is recorded.
- [ ] The skill was revised once from an analysis of the tests it wrote, and both test files are in the notes.
- [ ] The `tdd-reviewer` subagent has no editing tools, and one verdict is recorded.
- [ ] The gate blocked once and passed once, or the substitution is recorded.
- [ ] One MCP server is configured at project scope with no secrets in the file.
- [ ] One route comparison (GitHub or Playwright) was measured and the decision noted.
- [ ] The calibration ticket was implemented through the skill and scored against the checklist.
- [ ] The pull request contains the configuration, the implementation, your notes, the annotated trace, and a completed review gate.

### Optional extensions

- [ ] The second route comparison, whichever one you did not run in stage 5.
- [ ] The gate rebuilt with the client's experimental agent hook type, with a comparison of cost and reliability against the script version.
- [ ] A skill trigger test run with the [description-optimisation harness](https://agentskills.io/skill-creation/optimizing-descriptions) from the Agent Skills specification.
