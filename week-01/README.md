# Week 1 lab: Spike, Interrogate, Decide, Establish

Week 1 establishes the project you will develop throughout the course. You will choose a product, vibe-code a spike of it to see what a solution could look like, interrogate that spike until you can explain it and know where it fails, turn what you learned into recorded project decisions, and set up a repository on GitHub whose README describes the project and those decisions.

The lab applies two ideas from the Week 1 seminar. The first is the difference between the **acceleration** and **exploration** orientations towards an AI tool. The goal is to run the spike in acceleration posture and then study the same output in exploration posture, so that you can observe the comprehension gap on your own code. The second is the set of **working modes**: sketch from an outcome, pair inside a repo, and delegate a bounded issue. The spike is a sketch. The interrogation and the foundation are done by pairing inside the repo to define the initial project design. Delegation of bounded issues can happen once you have explored what you are building and have validated well enough to explain it and to check the result. Students who already work with specifications may use them. Weeks 3 and 4 formalise these practices as specification-driven development and loop engineering.

## Outcomes

By the end of Week 1, including any take-home part, you should have:

- selected one project and described the user problem in your own words;
- vibe-coded one spike of the product and preserved it on its own branch;
- interrogated the spike in exploration posture, tested its user journeys, and recorded what failed and what that means for the design;
- recorded the project's structural decisions in a decision log and deferred the behavioural questions you chose not to settle;
- a repository on GitHub with a README that describes the project, its main design decisions, and reproducible setup, start, and validation commands;
- proved the setup from a fresh checkout with a peer as runner or reviewer; and
- opened a pull request that passes a review gate you can defend.

The lab is ungraded. The pull request gives you and the instructor a concrete surface for feedback.

## Materials

### Choose one project

| Project | Best fit | Smallest useful interaction for the spike |
| --- | --- | --- |
| [Event Booking and Waitlist](projects/event-booking.md) | Product flows, state transitions, and familiar web interfaces | Browse a session and register or join its waitlist |
| [Support Ticket SLA and Escalation](projects/support-ticket-sla.md) | Operational software, time-based rules, and dashboards | Submit a ticket and move it through one staff action |
| [Inventory Reservation and Fulfilment](projects/inventory-reservation.md) | Domain invariants, stock movement, and concurrency | Reserve stock for one order and show the remaining quantity |
| [Multimodal AI Companion](projects/multimodal-ai-companion.md) | Advanced students moving towards AI engineering | Send one local text message and receive one model or stub response |

Choose a project that you can keep working on for five weeks. Interest in the problem matters more than prior knowledge of a particular framework. The AI companion adds API, evaluation, privacy, and cost decisions. It suits students who already feel comfortable building software.

### Week 1 playbooks

- Prompt Engineering Playbook: use it when drafting and revising the spike prompts.
- Software Design and Production Playbook: use the planning, design, and code-boundary sections when you make structural decisions.
- LLM Playbook: recommended background on the model concepts used in class.


## Lab flow

| Stage | Where | Posture | Result |
| --- | --- | --- | --- |
| 1. Select | In class | | One project, a written reason, a local project folder with a coding agent started inside it |
| 2. Spike | In class | Acceleration, sketch from an outcome | A runnable prototype on the `spike` branch with a prompt log |
| 3. Interrogate and decide | In class | Exploration, pair inside a repo | Journey test results, an assumptions register, a comprehension gap, a decision log, and a README draft |
| 4. Discuss | In class | | Small-group comparison of what the exploration changed |
| 5. Establish, prove, hand off | In class or take home | Exploration, pair inside a repo | A GitHub repository with the foundation, a peer-verified README, and a pull request that passes the review gate |
| 6. Extend | Take home, optional | Exploration, pair inside a repo or delegate a bounded issue | A second slice built design-first, measured the same way as the spike |

Setup support takes precedence. Stage 5 is the deliverable that Week 2 depends on. Everything else is preserved on disk and can be completed at home.

## 1. Select the project

Use the comparison table to shortlist a project. Read the product brief, intended users, and end-of-course requirements for each option. During the selection stage, choose one, read its full document, and write down the project choice:

```md
## Project choice

- Project:
- Intended user:
- Problem:
- Why I chose it:
- Main uncertainty:
```

Then set up the working space:

1. Create a local project folder named for the project, such as `agentic-engineering-event-booking`.
2. Initialise a Git repository in it and commit a README containing the project choice.
3. Start your coding agent inside the folder, or open the browser builder you will use for the spike. The GitHub repository comes in stage 5.

## 2. Spike in acceleration posture

Vibe-code a prototype of the product to see what a solution could look like. There is no framing step before this. The product brief and the **Spike** section of the selected project document are the whole input. The spike gives you the context you need to make design decisions in the next stage.

1. Write an initial prompt from the product brief that states the user outcome, relevant context, constraints, and the observable result.
2. Ask a source-exportable builder or coding agent to implement it.
3. Run it and capture the result.
4. Revise the prompt using a technique from the Prompt Engineering Playbook, and repeat.
5. Stop when the instructor calls time. List unfinished behaviour.

Work in acceleration posture on purpose: prompt, generate, run, prompt again. Accept and iterate on the generated implementation without a design pass and without reading the code closely. This is the control condition for the next stage. Do not add tests, refactor, or write a specification.


When time is called, export the source into the project folder on a branch named `spike`, commit it, and tag the commit `week-01-spike`. The spike is evidence. It is never merged into `main` and the foundation does not build on its code.

If the spike does not run when time is called, keep it anyway. A spike that fails is still material for the next stage.

## 3. Interrogate the spike and decide

Switch orientation. The output is the same. The goal is now understanding, and then decisions.

**Before you ask the agent anything**, write down the percentage of the spike you believe you understand well enough to change safely. Record it in the lab notes as the predicted estimate.

### Interrogate the structure

Run the exploration prompt pack against the spike, using a repository agent pointed at the `spike` branch. Ask each question and record the answer in your own words.

1. "Describe the structure of this code: where data enters, where state lives, where it changes, and where output is rendered."
2. "List every assumption you made that the prompt did not state. Include data shapes, ordering, error handling, and anything you left unimplemented but made look complete."
3. "Explain why the main state change lives where it does and what else depends on it."
4. "What breaks if the data shape changes? What breaks if the same request arrives twice?"
5. "Which of these questions does the code answer, and how?" Paste the **Questions to carry forward** list from the selected project document.

Record the assumptions in an assumptions register:

```md
| # | Assumption the spike made | Stated in a prompt? | Matters for the product? | Deferred to Week 3? |
| --- | --- | --- | --- | --- |
| 1 | | yes / no | yes / no | yes / no |
```

### Test the user journeys

Ask the agent to enumerate the user journeys the product should support, using the intended users and end-of-course requirements from the project document. Then test each journey against the running spike yourself. For each one, record whether it worked, where it failed, and what the failure tells you about the design.

```md
| Journey | User | Steps taken | Result | Failure observed | Design implication |
| --- | --- | --- | --- | --- | --- |
| Register for a session with one place left | Attendee | | pass / fail / not implemented | | |
```

A journey that the spike presents as working but that fails on a second attempt, on an edge case, or for a different user is the most useful finding. It shows where the product needs an explicit rule, a boundary, or a piece of state that the spike did not have.

### Measure the gap

Complete one unaided task **without the agent**: locate the code that performs the smallest useful interaction's state change and explain, in writing, what happens when the action is repeated with the same input. Afterwards, write down the percentage you now believe you understand. Record it as the demonstrated estimate. The difference between the two estimates is your comprehension gap for this spike.

### Decide

Turn what you learned into recorded decisions. Discuss the options with the agent in exploration posture: ask it to propose options and trade-offs for each decision, then choose yourself and record the reason. The Software Design and Production Playbook's planning, design, and code-boundary sections are the reference.

Create `docs/decisions.md` with one entry per decision:

```md
# Decision log

## 0001 · Runtime and package manager
- Decision:
- Reason:
- Alternatives considered:

## 0002 · Repository layout
- Decision:
- Reason:
- Alternatives considered:
```

Structural decisions belong in the log:

- runtime, language version, and package manager;
- repository layout and where domain logic lives relative to the interface;
- build, start, and validation commands;
- which components the product has, and which working mode you expect to use for each;
- which parts of the spike's shape are worth keeping as ideas and which are discarded; and
- what the foundation includes and what it leaves out.

Behavioural questions the spike forced you to guess, such as what happens when capacity is reached or when a request repeats, go to a **deferred-behaviour list** in the lab notes unless you decide them deliberately now. Writing them down as open questions is a valid deliverable. If you already work with specifications and want to settle a behaviour, write it as a short spec entry with an acceptance check, record it in the log, and note that Week 3 will revisit it.

Finish this stage by drafting the README on `main`: the project choice, a paragraph on how the product works as you now understand it, the main design decisions with a link to the decision log, and the deferred-behaviour list. If time allows, start the initial project setup from the decisions. Stage 5 completes it.

## 4. Group discussion

In groups of three, discuss:

1. What did the spike assume that you only noticed when you interrogated it?
2. Which user journey failed in the most instructive way, and what did it change in your design?
3. How far apart were your predicted and demonstrated estimates? What explains the gap?
4. Which decision in your log will matter most when you configure the agent in Week 2?
5. What did you deliberately leave on the deferred-behaviour list, and why does it belong there?

## 5. Establish the foundation, prove the setup, hand off

This stage can be completed in class or at home. Complete it before the Week 2 session. The goal is a repository on GitHub with a README that describes the project and all the main design decisions from the first pass, and that a stranger can set up from the README alone.

### Establish the foundation

Create a branch named `week-01-foundation` from `main`. Build the clean foundation with a repository-capable coding agent, working in exploration posture:

1. Ask the agent to propose a repository layout and toolchain that satisfies your decision log.
2. Challenge the proposal against the log. Ask why each file or dependency is there.
3. Decide. Update the decision log if the discussion changed a decision.
4. Let the agent scaffold the foundation.
5. Read the diff before committing. Anything you cannot explain does not get committed until you can.

The spike code is reference material for the discussion. Do not copy it into the foundation.

```text
README.md                 # project choice, how the product works, design decisions, setup, start, and validation instructions
.gitignore                # excludes dependencies, generated output, local secrets, and editor files
.env.example              # include when current or future work may use credentials
docs/decisions.md         # the decision log from stage 3
docs/week-01-lab-notes.md # evidence, assumptions, journey tests, comprehension gap, deferred behaviour
<package manifest>        # include when the project uses dependencies
<lockfile>                # include where the selected ecosystem provides one
<runtime version file>    # where the ecosystem provides one
<source directory>        # application code or a minimal placeholder entry point
<test or check location>  # an initial smoke check or documented validation command
```

The exact filenames depend on the chosen language. Keep one authoritative toolchain. The README must state:

- what the product is and who it is for;
- the main design decisions, with a link to the decision log;
- required runtime and version;
- dependency installation command, or a statement that no installation is required;
- local start command;
- validation or smoke-check command;
- environment variables and where to obtain them, using placeholders only; and
- the current state of the product.

### Publish to GitHub

1. Create the GitHub repository. Choose public or private visibility. Give the instructor access when you want pull-request feedback.
2. Push `main`, `week-01-foundation`, the `spike` branch, and the `week-01-spike` tag.
3. Create the `Week 1: repository foundation` issue. Add the project decision and the Week 1 acceptance-evidence section from the selected project document.
4. Record the baseline commit identifier in the lab notes.

### Prove the setup

Pair with another student. Ask them to clone the repository into a fresh directory, check out `week-01-foundation`, and use only the README to:

1. install dependencies, if any;
2. run the validation command; and
3. start the current application or placeholder entry point.

Give the peer read access when the repository is private. If sharing access is unsuitable, perform the same check yourself in a fresh directory and ask a peer to review the commands and recorded output. When this stage is done at home, the peer check can happen asynchronously through the pull request.

Record the commands, outcome, and any README correction in `docs/week-01-lab-notes.md`. A missing optional credential should produce a useful message when the current baseline reads credentials. It should never expose a secret or a raw provider error containing one.

### Write the lab notes

Use this structure in `docs/week-01-lab-notes.md`:

```md
# Week 1 lab notes

## Project decision
- Selected project:
- Intended user and problem:
- Reason for choosing it:

## Spike
- Tool used:
- Branch and tag:
- Prompt log: (the table from stage 2)
- Observable result:
- Screenshot or terminal evidence:
- Unfinished behaviour:

## Interrogation
- Predicted understanding before interrogation: ___%
- Assumptions register: (the table from stage 3)
- Journey tests: (the table from stage 3)
- Questions to carry forward that the spike answered silently:
- Unaided task and written explanation:
- Demonstrated understanding after the unaided task: ___%
- Comprehension gap (predicted minus demonstrated): ___ percentage points
- What the exploration posture surfaced that the acceleration posture hid:

## Deferred behaviour
- (one line per open behavioural question, carried to Week 3)

## Repository evidence
- Repository URL:
- Baseline commit:
- Runtime and package manager:
- Install command and result:
- Start command and result:
- Validation command and result:
- Verification mode: peer run / self-check with peer review
- Peer runner or reviewer:

## Decisions and gaps
- Decisions recorded in docs/decisions.md:
- Known gaps:
- First condition that would make this project higher risk:
- Question to carry into Week 2:
- Candidate next slice:
```

### Open the pull request and pass the review gate

Commit any corrections from the setup check, push the latest `week-01-foundation`, and open a **draft** pull request linked to the Week 1 issue. Include:

- the selected project and how the product works;
- exact setup, start, and validation commands;
- the clean-checkout result;
- a link to the `week-01-spike` tag and the comprehension gap you measured;
- the journey that failed most instructively and the design change it caused;
- the deferred-behaviour list; and
- the areas where instructor feedback would help.

Add the review gate to the pull request description and complete it honestly:

```md
## Review gate

- Files generated by an agent or builder:
- Files I can explain line by line:
- One thing I checked by hand, and how:
- What I would not merge yet, and why:
```

Mark the pull request **ready for review** only when you can answer every line. The gate applies the seminar's definition of done: a named person can explain, change, and verify the code before it merges.

Ask your peer to review the pull request. The reviewer asks the partner questions from the seminar: why is the logic there, what depends on it, what happens if the data shape changes, and how did you verify the answer. If sharing access is unsuitable, answer the four questions in the pull request description and ask the peer to review those answers.

Keep the pull request small enough for another person to review. You can merge it after incorporating the feedback you want to carry into Week 2.

## 6. Optional extension: a second slice in exploration posture (take home)

If you want a direct comparison on your own project, build one more narrow interaction inside the foundation. This time work design-first, pairing inside the repo or delegating a bounded issue:

1. Ask the agent to propose a design for the slice and list its assumptions before it writes code.
2. Challenge at least one assumption. Record the decision in the decision log if it is structural, or on the deferred-behaviour list if it is behavioural.
3. Let the agent implement the slice.
4. Apply the acceptance gate from the seminar before accepting the change: ask the agent to explain the logic, rewrite one function in your own terms, then verify it against the smoke check and by running it.
5. Record the same measurements as the spike: prompt log, predicted and demonstrated estimates, assumptions surfaced before building versus discovered afterwards.

If you choose to delegate rather than pair, the exploration conversation comes first: agree the task, its acceptance check, and its boundary with the agent, write them into a GitHub issue or a short spec file, and confirm the agent refers back to that text while it works. The result still goes through the review gate before it is accepted.

Commit the slice separately on `week-01-foundation` and add a short comparison to the lab notes. A smaller comprehension gap on the second slice is the expected result. A larger one is worth discussing in Week 2.

## Completion checklist

### Core

- [ ] I selected one project and explained the decision.
- [ ] The spike is on the `spike` branch, tagged `week-01-spike`, with a prompt log.
- [ ] I recorded predicted and demonstrated understanding and the assumptions register.
- [ ] I tested the user journeys against the spike and recorded each failure's design implication.
- [ ] `docs/decisions.md` records the structural decisions, each with a reason.
- [ ] The deferred-behaviour list names the behavioural questions I did not answer.
- [ ] The repository is on GitHub with the issue, both branches, and the spike tag.
- [ ] The README describes the product, the main design decisions, and the install, start, and validation commands.
- [ ] The repository contains the minimum foundation files for its ecosystem.
- [ ] I completed a fresh-checkout verification and recorded the peer runner or reviewer.
- [ ] The repository contains no real credentials or sensitive data.
- [ ] My pull request contains a completed review gate and I marked it ready for review only after passing it.

### Optional extension

- [ ] A second slice built design-first, with the same measurements as the spike.
- [ ] A short comparison between the two slices in the lab notes.

## What Week 2 builds on

Week 2 configures a coding agent for this repository. The README and decision log become the first sections of your agent instruction file. The deferred-behaviour list and the failed journeys become the pool of candidate bounded tasks for calibrating the configured agent. The smoke check becomes the validation the agent must run before claiming a task is done. The spike branch stays as the "before" artefact for the course.
