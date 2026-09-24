# Rules

These rules come from the project owner. They override any other document, reminder or summary.

## Worlds

- Development and verification rounds run on mini worlds only.
- Vanilla worlds are inefficient to develop on. Do not run them to find or fix failures.
- If data from any vanilla round reaches the snapshot database, wipe the entire snapshot database immediately: every run, not only the vanilla ones.
- If mini worlds are not representative of vanilla, fix the mini-world generator until they are. A situation that only vanilla produces is a generator gap to close, never a reason to run vanilla.

## Out of scope

- Actions that change every building of a type across the whole country.
- All auto-expand actions, including the per-state ones.
