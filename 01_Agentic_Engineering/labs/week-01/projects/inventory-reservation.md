# Project 3: Inventory Reservation and Fulfilment

**Level:** Core

**Best fit:** domain invariants, stock movement, concurrency, and operational recovery

## Product brief

Build a small inventory application for one warehouse. Customers place orders. The product reserves
available stock, releases it when an order is cancelled, and records fulfilment. Staff can view stock
and restock products.

The requirements describe the product outcome. You will choose the stack and refine the engineering
contract during later labs.

## Intended users

- **Customer:** places an order and sees whether stock has been reserved.
- **Warehouse staff:** views stock, fulfils or cancels orders, and records restocking.
- **Operations lead:** investigates discrepancies between expected and physical stock.

## End-of-course product requirements

| ID | Requirement |
| --- | --- |
| IR-01 | Staff can create products and record the quantity held in one warehouse. |
| IR-02 | A customer can create an order containing one or more products and quantities. |
| IR-03 | The product reserves available stock for an accepted order and reports unavailable items. |
| IR-04 | Staff can fulfil or cancel an order. |
| IR-05 | Cancellation releases stock that was reserved and has not been fulfilled. |
| IR-06 | Staff can restock a product and see the updated available quantity. |
| IR-07 | The product distinguishes physical, reserved, available, and fulfilled quantities. |
| IR-08 | The product records important order and stock changes for later inspection. |

Later labs will define the order lifecycle, stock invariants, authorisation boundaries, acceptance
tests, and delivery plan. Week 1 leaves those implementation decisions open.

## Week 1 decisions

Add these decisions to your README or Week 1 lab notes:

1. What type of products does the warehouse hold?
2. What information does a customer see before ordering?
3. What stock quantities should the first interface display?
4. What is the smallest useful interaction you want to demonstrate first?
5. Which details will use synthetic sample data?

Use this candidate when you need a starting point:

> Given a product with five available units, when a customer orders two, then the product records the
> reservation and shows three units available.

## Required Week 1 foundation

Follow the [shared Week 1 guide](../README.md). The repository must contain the common foundation,
project decision, decision log, reproducible commands, lab notes, and a pull request with a completed
review gate.

For this project, the README should also include:

- the customer and warehouse-staff journeys;
- the stock quantities and order fields shown to each user;
- the smallest useful interaction; and
- three example products and two example orders using synthetic data.

## Spike

Build one thin local path in acceleration posture, following stage 2 of the [shared Week 1 guide](../README.md). A suitable slice contains:

1. a list of pre-seeded products and available quantities;
2. one order action for a selected quantity;
3. an observable reservation result; and
4. the changed available quantity.

The interface may be a web page or CLI. In-memory data is sufficient. Keep the generated source in the
GitHub repository and document the start command.

### Spike evidence

- Show the initial stock quantity.
- Place one order.
- Show the reservation and resulting available quantity.
- Record the initial prompt and one revised prompt in the prompt log.
- List any stock or order rule the generator assumed without asking you.

## Week 1 constraints

- Use local execution and synthetic data.
- Keep one warehouse and one currency-free product catalogue.
- Keep payments, pricing, shipping providers, promotions, supplier management, and multiple warehouses
  outside the Week 1 scope.
- The spike may use fixed customer and staff views.
- Reservation expiry, partial fulfilment, returns, and damaged stock can remain future questions.
- Persistence is optional for the spike. State the behaviour after a restart.

## Questions to carry forward

Carry these questions into later labs. Stage 3 of the shared guide asks the agent which of them the spike answered silently. Record those answers in the assumptions register and keep the questions on the deferred-behaviour list.

- What happens when two orders compete for the final unit?
- Can a retried request reserve the same stock twice?
- When does a reservation expire?
- How does partial fulfilment affect reserved and available quantities?
- What happens when a fulfilled order is returned or stock is damaged?
- How should the product recover when recorded stock violates an invariant?
- Which changes require an audit record or notification?

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

- One complete local order-reservation path.
- Screenshot or terminal transcript showing the before and after quantities.
- Prompt log with the initial and revised prompts.
- The `spike` branch tagged `week-01-spike`, never merged into `main`.
- Predicted and demonstrated understanding estimates and the assumptions register.
