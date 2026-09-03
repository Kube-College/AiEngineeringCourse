# Project 1: Event Booking and Waitlist

**Level:** Core

**Best fit:** product workflows, state transitions, and familiar web interfaces

## Product brief

Build a small application for a workshop venue. Organisers publish sessions. Attendees browse the
programme, register, cancel, and join a waitlist when a session is full. The product shows availability
and each attendee's current registration status.

The requirements describe the product outcome. You will choose the stack and refine the engineering
contract during later labs.

## Intended users

- **Attendee:** finds a suitable session and secures a place.
- **Organiser:** publishes sessions and understands demand and availability.

## End-of-course product requirements

| ID | Requirement |
| --- | --- |
| EB-01 | An organiser can create, publish, update, and cancel a session. |
| EB-02 | An attendee can browse upcoming sessions and see the time, location, capacity, and current availability. |
| EB-03 | An attendee can register for an available session and see confirmation. |
| EB-04 | An attendee can cancel a registration. |
| EB-05 | A full session can accept waitlist entries and promote attendees when places become available. |
| EB-06 | The product distinguishes organiser and attendee actions. |
| EB-07 | The product records important session and registration changes for later inspection. |
| EB-08 | User-facing notifications can be observed locally without requiring a production email or messaging service. |

Later labs will turn these outcomes into a state model, explicit invariants, acceptance tests, and a
delivery plan. Week 1 leaves those implementation decisions open.

## Week 1 decisions

Add these decisions to your README or Week 1 lab notes:

1. What kind of venue or programme does the product serve?
2. What information does an attendee need before registering?
3. What information does an organiser need when publishing a session?
4. What is the smallest useful interaction you want to demonstrate first?
5. Which details will use synthetic sample data?

Use this candidate when you need a starting point:

> Given a published session with one place remaining, when an attendee registers, then the product
> confirms the registration and shows zero places remaining.

## Required Week 1 foundation

Follow the [shared Week 1 guide](../README.md). The repository must contain the common foundation,
project decision, decision log, reproducible commands, lab notes, and a pull request with a completed
review gate.

For this project, the README should also include:

- the attendee and organiser journeys in one paragraph each;
- the fields shown for a session;
- the smallest useful interaction; and
- three example sessions and two example attendees using synthetic data.

## Spike

Build one thin local path in acceleration posture, following stage 2 of the [shared Week 1 guide](../README.md). A suitable slice contains:

1. a list of pre-seeded sessions;
2. session availability;
3. one attendee registration action; and
4. an observable `confirmed` or `waitlisted` result.

The interface may be a web page or CLI. In-memory data is sufficient. Keep the generated source in the
GitHub repository and document the start command.

### Spike evidence

- Show the initial session and availability.
- Perform one registration.
- Show the resulting status and changed availability.
- Record the initial prompt and one revised prompt in the prompt log.
- List any behaviour the generator assumed without asking you.

## Week 1 constraints

- Use local execution and synthetic data.
- Keep a single venue and single-seat registrations.
- Keep payments, recurring events, assigned seating, real notifications, and third-party calendar
  integrations outside the Week 1 scope.
- Authentication can remain a stated future boundary. The spike may use a simple role switch or
  labelled views.
- Persistence is optional for the spike. State the behaviour after a restart.

## Questions to carry forward

Carry these questions into later labs. Stage 3 of the shared guide asks the agent which of them the spike answered silently. Record those answers in the assumptions register and keep the questions on the deferred-behaviour list.

- What happens when two attendees compete for the last place?
- Can the same request create two registrations?
- What order governs waitlist promotion?
- What should happen if cancellation and promotion cannot both complete?
- Which time zone defines the session time?
- Which changes require an audit record or notification?
- What happens when an organiser reduces capacity below the confirmed count?

These questions provide material for the coding-agent, specification, and loop-engineering labs.

## Week 1 acceptance evidence

### Core

- Repository URL, issue, baseline commit, and draft pull request.
- README with the product decision, example data, and reproducible commands.
- Successful fresh-checkout result, completed by a peer or reviewed by one.
- Lab notes with the component-to-mode table, deferred-behaviour list, gaps, and the chosen next slice.
- `docs/decisions.md` with structural decisions only.
- A pull request with a completed review gate.

### Spike and interrogation

- One complete local registration path.
- Screenshot or terminal transcript showing the before and after state.
- Prompt log with the initial and revised prompts.
- The `spike` branch tagged `week-01-spike`, never merged into `main`.
- Predicted and demonstrated understanding estimates and the assumptions register.
