# Contributing

Thanks for your interest in claude-code-dialogue.

## Scope
This is a deliberately small, single-machine, file-based coordination tool. Changes that keep it
simple and dependency-light are most welcome. Large architectural additions (networking,
databases, cross-machine sync, a server/daemon) are **out of scope by design** — that simplicity
is the point.

## Dev setup
```bash
git clone <repo> ~/.claude-code-dialogue
cd ~/.claude-code-dialogue
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

## Before opening a PR
- Run the self-check and keep it all green:
  ```bash
  DIALOGUE_TEAM_ROOT=/tmp/dlg/team DIALOGUE_BOARDS_ROOT=/tmp/dlg/boards \
    .venv/bin/python -m dialogue.selfcheck
  ```
- Keep the engine **dependency-light**: the only external dependency is `watchdog`.
- **No emoji in code** (they break on some Windows terminals).
- Keep code, comments and user-facing strings in **English**.
- Match the existing style; prefer a small robust change over a clever abstraction.

## Tests
`dialogue/selfcheck.py` is the regression suite. When you add or change behavior, add a
`record(...)` case for it and make sure the whole suite stays green. Always run tests in an
**isolated temp store** (the `DIALOGUE_*_ROOT` env vars above) — never against a real project's
`.dialogue/`.
