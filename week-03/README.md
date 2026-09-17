# Week 3 lab: Explore, Specify, Implement, Explain

Use one spec-driven development (SDD) framework from the seminar to deliver a feature in your course project. First, explore how the framework works with your coding agent. Map its artefacts to the design questions covered in the Week 3 playbook. Then use its workflow to specify, implement, and verify the feature.

The stretch goal is to generate an OpenWiki for your project, check its explanations against the implementation, and use an AI-led quiz to test your understanding.

Continue with the repository you used in [Week 1](../week-01/README.md) and [Week 2](../week-02/README.md). The lab is ungraded. Your pull request and notes give you, a peer, and the instructor something concrete to discuss.

## Outcomes

By the end of the core lab, you should be able to:

- explain your chosen framework's workflow, artefacts, review points, and maintenance process;
- locate its coverage of product requirements, high-level design, low-level design, and technical specifications;
- identify missing decisions and decide how much additional documentation your feature needs;
- use the framework to produce a reviewed specification and implement a bounded feature;
- connect acceptance criteria to tests and observed behaviour; and
- explain the resulting change and the decisions you made yourself.

## Materials

- Your project repository and an authenticated coding agent. Keep the useful instructions, skills, and review practices from Week 2.
- A runnable project and its test command. If the project is still a skeleton, choose a small first user journey and include the minimum setup it needs.
- The **Spec-Driven Development Playbook**, downloaded from **Moodle**. Give the agent the local file path or attach the document. Ask it to confirm which sections it can read. Keep the downloaded teaching material out of your public repository.
- The official documentation for your chosen framework. Installation and commands vary by version and coding client; follow the current instructions for your setup.

Useful playbook sections are **Design methods and representations**, **Specification contents and writing**, **Verification and acceptance evidence**, **Maintaining specifications and decisions**, and **Knowledge maintenance and code wikis**. Use the worked booking-cancellation example if you need help judging the level of detail.

Create a short `docs/labs/week-03.md` in your own project for your findings and evidence. Keep framework-generated documents in the locations the framework expects. Link to those documents from your notes.

## Lab flow

These are suggested planning allowances. Finish implementation and review as take-home work if needed.

| Stage | Suggested time | Result |
| --- | --- | --- |
| 1. Select and explore a framework | 25 minutes | Workflow explanation with source references |
| 2. Map its artefacts and identify gaps | 25 minutes | Design-artefact map and decisions about missing coverage |
| 3. Specify one feature | 35 minutes | Reviewed specification and implementation plan |
| 4. Implement and verify | 50 minutes, then take home if needed | Working feature and acceptance evidence |
| 5. Review and explain | 15 minutes | Pull request and reflection |
| Stretch. Generate, inspect, and quiz a wiki | Optional take-home work | Reviewed wiki and comprehension notes |

## 1. Select and explore a framework

Choose **one** of the frameworks or skill systems discussed in class. These links are starting points for your investigation:

- [Superpowers](https://github.com/obra/superpowers), used in the seminar walkthrough.
- [Spec Kit](https://github.com/github/spec-kit).
- [OpenSpec](https://github.com/Fission-AI/OpenSpec).
- [Kiro specs](https://kiro.dev/docs/specs/).
- [BMAD](https://docs.bmad-method.org/).
- [Addy Osmani's Agent Skills](https://github.com/addyosmani/agent-skills/tree/main).
- [Matt Pocock's skills](https://github.com/mattpocock/skills).

For a skill system, identify the specific skills you will use, their sequence, and how they cover specification through implementation. Apply the same exploration and artefact-mapping exercise to that workflow. If you choose another workflow shown in class, identify its components in the same way. Choose a route supported by your coding client. Record the framework or skill-system version or source revision, documentation URL and access date, coding client, and model.

### Use exploration mode

Exploration is a working posture: you ask questions, inspect evidence, and build your own understanding. Use your client's read-only or planning mode where available. Mode names differ across clients. Tell the agent to explain before acting and to wait for your answers. During this stage, it should read the framework documentation and your repository without installing tools or changing project files. Write your findings in your notes yourself.

Start with a prompt like this. Replace the bracketed inputs.

```text
We are exploring [framework] before using it in this project.
Read its official documentation at [URL] and inspect the relevant
workflow definitions, templates, or skills. Use [local Moodle SDD
playbook path] as the reference for design terminology.

Do not install anything, edit files, or implement a feature yet.
Explain the workflow in small steps. For each step, identify:
- what starts it and what context it reads;
- what the human and the agent each decide;
- what artefact it creates or updates, and where it lives;
- what review or executable check happens before the next step;
- what happens when requirements change after implementation.

Cite the documentation or source for each claim. Separate documented
behaviour from your inference and from anything we have tested locally.
Ask me one question at a time to check my understanding. Wait for my answer.
```

Follow the sources for at least one workflow step yourself. Inspect an actual template, skill, or example artefact. If the README and detailed workflow disagree, record the difference and establish which applies to your selected version.

In your own words, write the workflow as a short sequence. Mark where you review decisions. Identify whether each apparent gate is a written instruction, an agent review, or an executable check that can block progress. Include what survives after the feature is delivered: a one-off specification, maintained capability documentation, a change archive, or another arrangement.

## 2. Map its artefacts and identify gaps

Ask the agent how the framework captures **PRDs, HLDs, LLDs, and technical specifications**, then challenge its answer using the Moodle playbook. These labels describe overlapping views. A framework may combine several views in one document or spread one view across several files.

Use the following questions to inspect the content of its artefacts. Complete the last two columns with evidence from the selected workflow.

| Design view | Questions it should help answer | Framework artefact and section, with source | Coverage and missing decisions |
| --- | --- | --- | --- |
| PRD: product requirements document | Who needs the feature? What outcome matters? What is in scope? What counts as acceptance? | | |
| HLD: high-level design | Which components own the work and data? How do they interact? What external dependencies and system constraints matter? | | |
| LLD: low-level design | What interfaces, state transitions, data structures, and algorithms implement the behaviour? How are failures and competing actions handled? | | |
| Technical specification | What precise contracts, rules, invariants, limits, and compatibility obligations must the implementation satisfy? How will they be verified? | | |

Classify coverage as **explicit**, **partial**, or **absent**. A heading in an empty template demonstrates a place to record a decision; it does not demonstrate that the decision has been made. A task list describes delivery work and may leave design questions unanswered.

Use a follow-up prompt:

```text
Compare the framework's actual artefacts with the PRD, HLD, LLD, and
technical-specification views in the Moodle SDD playbook.
Show the source section supporting each mapping. Do not infer coverage
from file names alone. Which decisions does the workflow ask us to make?
Which does it leave implicit, omit, or delegate to implementation?

For our proposed feature, identify consequential gaps. Ask me to resolve
them one at a time. Suggest where each answer belongs in the framework's
existing artefacts. If extra documentation is needed, explain its purpose.
```

Record the gaps relevant to your feature, the decisions they require, and where you will capture the answers. If a view needs no further detail for this change, explain why. Revisit this map after generating your own specification in stage 3.

## 3. Specify one feature

Choose a small feature from your project brief, an unresolved Week 1 decision, or behaviour deferred in Week 2. It should produce an observable user outcome and involve a design decision you can explain. Keep it small enough to implement and exercise through a complete journey.

Possible starting points:

| Project | Candidate feature | Decision to settle before implementation |
| --- | --- | --- |
| Event Booking and Waitlist | Cancel a booking and make the place available | Who can cancel, and what happens to the next waiting attendee? |
| Support Ticket SLA and Escalation | Escalate a ticket after its response deadline | Which clock determines the deadline, and what prevents repeat escalation? |
| Inventory Reservation and Fulfilment | Expire a reservation and release its stock | What happens if fulfilment and expiry compete? |
| Multimodal AI Companion | Delete a conversation and its associated stored content | Which records and files are deleted, and what happens after partial failure? |

Choose an unfinished behaviour. If the example already exists in your project, select a different feature or a clearly scoped extension.

1. **Establish the starting state.** Create a feature branch. Record the starting commit, run the existing tests, and try the affected journey. Separate current behaviour, intended behaviour, and the proposed change.
2. **Set up the selected framework.** Follow its official instructions for your client and existing repository. Inspect the configuration diff and retain the project rules you still need. Confirm the expected workflow is available.
3. **Enter its specification workflow.** Give it the feature, relevant project documents, current behaviour, and the gaps from stage 2. Ask it to pause for your decisions before implementing. Use the framework's own commands, skills, or interface.
4. **Review the generated specification.** Correct assumptions and contradictions. Record consequential decisions and their reasons. Resolve questions that affect acceptance before approving implementation.
5. **Review the delivery plan.** Check that tasks refer to the specification and include the tests needed to demonstrate the outcome.

Use the playbook's specification contents as your review checklist:

- **Outcomes:** the user and observable result.
- **Scope:** included behaviour and explicit exclusions.
- **Constraints:** existing contracts, data handling, operational limits, and relevant project rules.
- **Settled decisions:** ownership, state changes, failure behaviour, and the reasons for consequential choices.
- **Linked delivery plan:** a route from the specification to implementation tasks.
- **Verification:** acceptance scenarios with concrete starting conditions, actions, and expected results.

Include the normal journey, a relevant edge or failure case, and a repeat or competing-action case where the feature has that risk. Give acceptance criteria stable labels such as `AC-01` so you can follow them through implementation and review.

Update the stage 2 map with paths and sections from **your generated artefacts**. Add missing detail where it is needed. Save the specification and your review decisions before starting implementation. If the framework keeps a small design only in chat, preserve a concise approved record in your project and link it from the plan.

## 4. Implement and verify

Switch deliberately from exploration to implementation. Tell the agent which reviewed specification to use and start the framework's implementation workflow.

```text
Implement [feature] using [framework workflow] and the reviewed
specification at [path]. First identify the applicable acceptance criteria
and project constraints. Follow our test-first and review practices.

If implementation exposes a missing product rule or changes an agreed
contract, pause and bring me the decision. Record agreed changes in the
specification before continuing the affected work.

For each completed acceptance criterion, report the implementation path,
test or manual check, command, and observed result. Distinguish passed,
failed, and unverified work.
```

Review the failing test for the new behaviour before the implementation makes it pass. Check that it fails for the expected reason. Then inspect the implementation diff and run the relevant tests, including existing tests that protect affected behaviour.

Add a journey-level acceptance test that exercises the feature through its application boundary, such as an API, CLI, or UI. Use realistic starting state and check the resulting state. A unit test for one helper may leave the user journey untested. Exercise the journey yourself as well.

Keep a short evidence table:

| Acceptance criterion | Implementation location | Test or manual check | Command and observed result |
| --- | --- | --- | --- |
| AC-01 | | | |

When something fails, identify the cause: an incorrect requirement, an incomplete specification, an implementation defect, or an incorrect test. Fix the relevant source of the problem. Preserve the reason for any changed requirement.

Finish with the framework's review and completion steps. Record whether the feature is on a branch, merged, or deployed. If the framework maintains or archives specifications, follow its lifecycle at the appropriate point and record any step still pending. Keep the maintained description consistent with the baseline it claims to describe.

## 5. Review and explain

Open a pull request in your project containing the feature, tests, framework artefacts, and lab notes. Link the acceptance evidence in its description. Include a short reflection:

- Which design decision did you make that the agent could not infer from the code?
- What did the framework capture well, and what did you have to add?
- Where did the actual workflow differ from your stage 1 explanation?
- What can you now explain about the implementation, and what remains unclear?

Ask a peer to choose one acceptance criterion and follow it from specification to code to test. Explain the feature's data flow and one failure case without asking the agent to answer for you. Record unresolved findings in the pull request.

## Stretch: Generate, inspect, and quiz a wiki

### Generate an OpenWiki

Use [LangChain's OpenWiki](https://github.com/langchain-ai/openwiki) for your project. Choose either its CLI or a supported [coding-agent integration](https://github.com/langchain-ai/openwiki/blob/main/openwiki/integrations/coding-agents.md). Follow the current setup instructions and record the version and generation route.

For the CLI route, the documented first-generation command is `openwiki --init`, run in your project after installation and provider setup. It writes the repository wiki to `openwiki/`. Use `openwiki --update` for subsequent updates. Re-running `--init` can replace an existing wiki; inspect the current instructions before doing so. Confirm successful completion before reviewing the output. See the [OpenWiki README](https://github.com/langchain-ai/openwiki).

Generate from a known project commit after the feature work. Record that revision. Review the generated-file and agent-instruction diffs before committing them. Keep credentials out of version control. Use the Markdown pages or the [local visualiser](https://github.com/langchain-ai/openwiki/blob/main/openwiki/integrations/visualizer.md) to explore the result.

### Check the explanations

Read pages about the architecture, data or state model, and the feature you implemented. Return your coding agent to exploration mode. Ask it to help you trace a request through the actual source and compare the wiki with the specification.

Check at least three concrete claims yourself. Include an architectural claim and a claim about failure behaviour. Record the wiki page, supporting code or test, and your verdict: supported, contradicted, or not established. An evidence link is a starting point for inspection. It does not establish that the explanation is correct.

Look for undocumented rationale presented as fact and intended behaviour presented as already implemented. Correct the wiki's mistakes. If the implementation conflicts with an agreed requirement, record a code or design issue and describe the discrepancy accurately in the wiki.

### Test your understanding

Use the [quiz-me skill by jellydn](https://github.com/jellydn/my-ai-tools/blob/main/skills/quiz-me/SKILL.md), or adapt its conversational approach. It asks questions about completed work and gives feedback with code references. Read it before installing it. A prompt is sufficient for this exercise; installation is optional.

The following lab variation focuses on your project's current architecture and the wiki claims you inspected:

```text
Stay in exploration mode. Use our wiki, source code, tests, and reviewed
feature specification to quiz me about this project's current state.
Do not change files.

Ask one question at a time and wait for my answer. Begin with component
responsibilities, then cover a request's data flow, state ownership, a
failure case, and the effect of a possible requirement change.
Do not reveal the answer or give it away in multiple-choice options.

After I answer, check it against specific code and tests. Explain any gap
with references I can inspect. If the wiki conflicts with the code, flag
the conflict. If a design rationale is undocumented, say it is unknown.

Finish by listing what I explained well, what I need to revisit, and a
follow-up question for each gap. Let me answer again after reading.
```

Save a brief record of one answer you corrected, the evidence that changed your understanding, and your answer to the follow-up. If the quiz exposes a documentation error, include the correction in your documentation diff. An agent's favourable assessment is one feedback signal; being able to trace and explain the code is the exercise.

## Completion checklist

### Core

- [ ] I selected one framework and recorded its version, sources, client, and model.
- [ ] I explored its workflow with my agent and wrote my own explanation.
- [ ] I mapped PRD, HLD, LLD, and technical-specification coverage using the Moodle playbook.
- [ ] I identified gaps and resolved the decisions needed for my feature.
- [ ] I used the framework to create a specification and plan, and reviewed them before implementation.
- [ ] I implemented the feature through the framework and recorded acceptance evidence, including a journey-level test.
- [ ] I checked the running behaviour and can explain a design decision and a failure case.
- [ ] My pull request links the artefacts, evidence, reflection, and any pending lifecycle steps.

### Optional stretch

- [ ] I generated an OpenWiki for a recorded project revision and reviewed its changes.
- [ ] I checked wiki claims against code and tests and recorded corrections or unknowns.
- [ ] I answered an exploration-mode quiz and revisited a gap in my understanding.

Framework and OpenWiki links were checked on 17 September 2026. Consult the current documentation when running the lab.
