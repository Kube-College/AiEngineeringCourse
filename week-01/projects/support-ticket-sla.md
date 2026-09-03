# Project 2: Support Ticket SLA and Escalation

**Level:** Core

**Best fit:** operational software, time-based rules, queues, and dashboards

## Product brief

Build a helpdesk for customers and support staff. Customers submit requests. Staff triage, assign,
prioritise, discuss, and resolve them. The product makes response commitments visible and identifies
tickets that need attention.

The requirements describe the product outcome. You will choose the stack and refine the engineering
contract during later labs.

## Intended users

- **Customer:** reports a problem and follows its progress.
- **Support agent:** owns work, communicates with the customer, and resolves tickets.
- **Support lead:** sees workload and tickets approaching or exceeding their response commitments.

## End-of-course product requirements

| ID | Requirement |
| --- | --- |
| ST-01 | A customer can submit a ticket with a subject, description, and severity. |
| ST-02 | A customer can view the ticket's status and conversation history. |
| ST-03 | Support staff can view, filter, assign, prioritise, and update tickets. |
| ST-04 | Support staff and customers can add comments with a visible author and timestamp. |
| ST-05 | A ticket moves through a defined lifecycle from submission to resolution and possible reopening. |
| ST-06 | The product calculates response commitments and makes approaching or missed targets visible. |
| ST-07 | The product escalates qualifying tickets through an observable local mechanism. |
| ST-08 | The product keeps a history of important ticket, assignment, and SLA changes. |

Later labs will define the lifecycle, timing rules, authorisation boundaries, acceptance tests, and
delivery plan. Week 1 leaves those implementation decisions open.

## Week 1 decisions

Add these decisions to your README or Week 1 lab notes:

1. What organisation or product does the helpdesk support?
2. What information must a customer provide in the first request?
3. Which staff action should the first slice demonstrate?
4. Which ticket states are needed for the first visible journey?
5. Which details will use synthetic sample data?

Use this candidate when you need a starting point:

> Given an empty support queue, when a customer submits a high-severity ticket, then the product shows
> the ticket in the staff queue with its initial status and response target.

## Required Week 1 foundation

Follow the [shared Week 1 guide](../README.md). The repository must contain the common foundation,
project decision, decision log, reproducible commands, lab notes, and a pull request with a completed
review gate.

For this project, the README should also include:

- the customer, support agent, and support lead journeys;
- the fields captured for a ticket;
- the smallest useful interaction; and
- three example tickets with different severities and states using synthetic data.

## Spike

Build one thin local path in acceleration posture, following stage 2 of the [shared Week 1 guide](../README.md). A suitable slice contains:

1. a customer ticket form or CLI command;
2. a staff queue containing the new ticket;
3. one staff action, such as assignment or status change; and
4. an observable ticket history or updated state.

An SLA indicator may use a fixed example target. Precise business-time behaviour belongs to later
requirements work.

### Spike evidence

- Submit one ticket.
- Show it in the staff queue.
- Apply one staff action and show the result.
- Record the initial prompt and one revised prompt in the prompt log.
- List any workflow or timing rule the generator invented.

## Week 1 constraints

- Use local execution and synthetic customer data.
- Keep one support team and one product or service.
- Keep real email ingestion, paging services, CRM integrations, billing, and customer identity systems
  outside the Week 1 scope.
- The spike may use fixed role views or a role switch.
- Use an explicit sample time when displaying an SLA result. State whether the clock is real or fixed.
- Persistence is optional for the spike. State the behaviour after a restart.

## Questions to carry forward

Carry these questions into later labs. Stage 3 of the shared guide asks the agent which of them the spike answered silently. Record those answers in the assumptions register and keep the questions on the deferred-behaviour list.

- Which events start, pause, resume, and stop each SLA clock?
- How do business hours, weekends, and holidays affect deadlines?
- Do severity and customer tier select different commitments?
- What happens when a closed ticket is reopened?
- How should duplicate inbound events behave?
- Which staff roles can assign, escalate, or close a ticket?
- What history and notifications are required for each transition?

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

- One complete local ticket-submission and staff-action path.
- Screenshot or terminal transcript showing the state change.
- Prompt log with the initial and revised prompts.
- The `spike` branch tagged `week-01-spike`, never merged into `main`.
- Predicted and demonstrated understanding estimates and the assumptions register.
