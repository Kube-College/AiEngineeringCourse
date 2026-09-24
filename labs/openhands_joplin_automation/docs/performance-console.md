# Agent performance console

The local console shows what happened during each controller dispatch. It reads
the controller's SQLite state and, while a workspace is running, requests
redacted event metadata from its Agent Server. The browser receives no Agent
Server token, message text, command arguments or tool results.

## Start and inspect

Start the controller from the lab directory:

```sh
make run
```

In a second terminal in the same directory, start the console:

```sh
make dashboard
```

Open <http://127.0.0.1:8765>. The server binds to loopback and refreshes the
page every 15 seconds. Select an issue to see its dispatches, controller state
transitions, validation results and agent event labels. The run ID appears below
each role in the dispatch table. Set `STATE_DIR` in both terminals if you want
to use a non-default state directory. `controller dashboard --port 8766` selects
another loopback port.

The cost column sums settled model charges assigned to each dispatch. “Cost
uncertain” means the provider did not report a cost for at least one request.
“No charge recorded” means the controller has no attributed model request for
that run.
Elapsed time runs from the first recorded `running` transition to the terminal
dispatch transition. Older runs can have missing model, profile, history or cost
attribution because those facts were not recorded when they ran. The profile
hash changes when the role's model, tools, skills or instruction content
changes. It identifies a configuration; it does not describe the result.

The console records event kind, source, tool label and timestamp. It reads live
metadata from the Agent Server when available. When a completed workspace is
cleaned up, the controller archives those labels in SQLite. Raw workspace
events are removed with the workspace during cleanup.

## Rate a run

Use the run ID shown in the dispatch table:

```sh
rtk proxy uv run controller rate RUN_ID --rating useful --note "Correct triage and clear evidence"
```

Allowed ratings are `useful`, `partly-useful` and `incorrect`. Running the
command again replaces that run's rating and note. Rating does not change the
workflow state or authorise an agent action. The browser is read only.
