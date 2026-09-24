# Initial setup brief

This historical setup brief is superseded by the
[Joplin design](2026-09-23-openhands-design.md) and
[implementation plans](plans/README.md).

The initial proposal used Superset as the example codebase. On 23 September 2026,
the user changed the target to [Joplin](https://github.com/laurent22/joplin).
The controller retains SQLite state, bounded OpenHands execution, GitHub human
approval, and controller-owned validation/publication. The target-specific
runtime and test fixtures now cover Joplin shared logic and desktop UI.

The goal remains a functional local demo before decomposition into student
exercises. No controller or live demo has been implemented. Keep work local
during WIP.
