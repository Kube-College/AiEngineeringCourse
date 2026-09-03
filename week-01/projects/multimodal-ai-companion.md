# Project 4: Multimodal AI Companion

**Level:** Advanced

**Best fit:** students moving towards AI engineering who already feel comfortable building software

## Product brief

Build an AI companion that holds a coherent conversation and can grow to support text, images, audio,
memory, and useful actions. You choose its audience and purpose. Suitable concepts include a study
companion, creative collaborator, language-practice partner, or original fictional persona that does
not impersonate a real person.

The product must identify itself as AI. Its purpose, memory boundaries, and safety limits should be
clear to the user.

This option takes product-level inspiration from the
[Ava WhatsApp Agent course](https://github.com/neural-maze/ava-whatsapp-agent-course/tree/338fd6870df9097165fceb3bbfc3cb0c95e584cd).
Create your own repository from these requirements. Frameworks, model providers, state management, and
delivery channels remain student decisions.

## Intended users

Define one primary user group and one job the companion performs. Avoid a general assistant that tries
to handle every task. The chosen purpose should make it possible to judge whether a response helped.

## End-of-course product requirements

| ID | Requirement |
| --- | --- |
| AI-01 | A user can hold a model-backed, multi-turn text conversation through a local interface. |
| AI-02 | The companion communicates its purpose, capabilities, and AI identity. |
| AI-03 | The product classifies requests and routes them to the relevant response or capability path. |
| AI-04 | The product preserves the context needed during a conversation. |
| AI-05 | The product retains information across conversations only after an explicit user choice. Users can inspect, correct, and delete it, with a visible deletion result. |
| AI-06 | The product accepts text and at least one non-text input modality, such as an image or audio clip. |
| AI-07 | The product handles unsupported input, unavailable providers, unsafe requests, and uncertain answers through visible fallback behaviour. |
| AI-08 | The product records enough execution evidence to diagnose a failed interaction while protecting user data. |
| AI-09 | A small evaluation set checks routing, context use, memory controls, fallback behaviour, and the companion's core job. |

These requirements express the intended product. Later labs will refine the scope and turn the selected
capabilities into an architecture, executable specification, tests, and delivery loops.

### Stretch capabilities

- Support a second non-text input modality.
- Produce a non-text response, such as generated audio or an image.
- Use a contextual tool or approved external data source.
- Expose the product through a deployed chat surface or messaging-channel adapter.

## Week 1 decisions

Add these decisions to your README or Week 1 lab notes:

1. What is the companion's purpose and working name?
2. Who is the primary user, and what job do they need help with?
3. How should the companion communicate?
4. What is the smallest useful text interaction?
5. What image and audio interactions may become useful later?
6. What information may the product retain, and what information should it avoid retaining?
7. What should the user see when the model or provider is unavailable?
8. What deliberate product or safety decision makes your companion different from the Ava reference?

Use this candidate when you need a starting point:

> Given a user with one clearly stated goal, when they send a text message through a local interface,
> then the companion returns a relevant response in its declared style and preserves the conversation
> identifier for the next turn.

## Required Week 1 foundation

Follow the [shared Week 1 guide](../README.md). The repository must contain the common foundation,
project decision, decision log, reproducible commands, lab notes, and a pull request with a completed
review gate.

For this project, the README should also include:

- the companion's purpose, user, and AI identity;
- three representative text scenarios and one fallback scenario;
- candidate image and audio interactions for later weeks;
- the types of information the product may and must not retain;
- a short component sketch or written system boundary; and
- an estimate of which providers, credentials, and costs the current idea may introduce; and
- a provenance note for any code, media, prompt, or design adapted from another source.

### Interaction record

Describe a framework-neutral interaction record. Prose, a type definition, or example JSON is
acceptable. Account for:

- conversation or session identifier;
- input type;
- text content or a media reference;
- relevant metadata;
- requested or selected response type;
- response content or a media reference; and
- success, fallback, or error status.

A prose version satisfies the Week 1 requirement. Later labs can turn it into an executable contract.

## Spike

Build one thin local text path in acceleration posture, following stage 2 of the [shared Week 1 guide](../README.md). A suitable slice contains:

1. a CLI or small web interface that accepts one text message;
2. one model call or deterministic stub;
3. a visible response;
4. a conversation identifier retained for the session; and
5. a useful fallback when optional configuration is absent.

Keep image, audio, persistent memory, tools, and external messaging as documented extension points.
They are outside the spike success criteria.

### Spike evidence

- Show one complete local text interaction.
- Show the missing-configuration fallback.
- Record the initial prompt and one revised prompt in the prompt log.
- Identify the system instruction or equivalent product context supplied to the model.
- List generated changes that required manual intervention.
- Record the provider or stub used and any observed request cost or limit.

## Week 1 constraints

- Keep the project framework-neutral at the requirements level.
- Keep provider-specific behaviour behind a small boundary that can change later.
- Read credentials from environment variables or an equivalent local secret store.
- Commit placeholder names in `.env.example` and keep real values outside Git.
- Permit a deterministic stub so the repository can run without paid or unavailable providers.
- Use synthetic conversations. Keep personal and customer conversations out of fixtures and logs.
- Make the companion's AI identity visible.
- Keep autonomous external actions, production messaging channels, and high-stakes medical, legal, or
  crisis guidance outside the Week 1 scope.
- State a request, token, or spending limit before using a paid model API.

## Week 1 exclusions

The Week 1 submission does not require:

- image understanding or generation;
- speech recognition or synthesis;
- workflow or graph orchestration;
- a vector database;
- persistent user memory;
- WhatsApp or another external messaging service;
- cloud deployment;
- authentication, billing, or multi-user isolation; or
- a polished interface.

## Questions to carry forward

Carry these questions into later labs. Stage 3 of the shared guide asks the agent which of them the spike answered silently. Record those answers in the assumptions register and keep the questions on the deferred-behaviour list.

- Which requests need distinct capability paths, and how will routing be evaluated?
- What context must remain in the current conversation?
- Which information merits long-term memory, and who can inspect or delete it?
- How should the product cite or qualify information from an external source?
- What permissions does each tool need?
- How should the experience degrade when one media provider fails?
- Which traces help diagnose failures without retaining sensitive content?
- Which examples belong in the evaluation set?

These questions provide material for the coding-agent, specification, and loop-engineering labs.

## Week 1 acceptance evidence

### Core

- Repository URL, issue, baseline commit, and draft pull request.
- README with the companion concept, scenarios, boundaries, interaction record, and reproducible
  commands.
- Successful fresh-checkout result, completed by a peer or reviewed by one.
- Confirmation that the repository contains no real credentials or personal conversations.
- Lab notes with the component-to-mode table, deferred-behaviour list, gaps, cost considerations, and the chosen next slice.
- `docs/decisions.md` with structural decisions only.
- A pull request with a completed review gate.

### Spike and interrogation

- One complete local text interaction using a model or deterministic stub.
- Screenshot or terminal transcript of the interaction and missing-configuration fallback.
- Prompt log with the initial and revised prompts.
- The `spike` branch tagged `week-01-spike`, never merged into `main`.
- Predicted and demonstrated understanding estimates and the assumptions register.

## Reference boundary

The Ava repository is a worked reference implementation of conversation routing, media capabilities,
memory, a local chat interface, and messaging-channel delivery. Use it to understand one possible end
state. Its
[reference prompts](https://github.com/neural-maze/ava-whatsapp-agent-course/blob/338fd6870df9097165fceb3bbfc3cb0c95e584cd/src/ai_companion/core/prompts.py#L58-L168)
conceal the product's AI identity and automatically extract personal facts. This brief requires visible
AI identity and user-controlled memory. Keep those behaviours out of your implementation.
