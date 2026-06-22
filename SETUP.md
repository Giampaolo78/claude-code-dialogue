# Setup — for Claude Code to execute

You are Claude Code, asked to set up the **claude-code-dialogue** system on this machine for the current
project. Do it now, in order. This is a single-machine, file-based coordination tool for parallel
Claude Code instances working on the same project.

## Prerequisites (check first)
- **Python 3** and **git** must be available. If `python3` is missing, tell the user to install it
  (don't guess their package manager) and stop.

## Steps
1. **Get the engine** at the fixed home `~/.claude-code-dialogue`. If it is not there yet, clone it
   from the public GitHub repo (no auth needed — the repo is public):
   ```bash
   git clone https://github.com/Giampaolo78/claude-code-dialogue.git ~/.claude-code-dialogue
   ```
   If it was already cloned elsewhere — e.g. via GitHub Desktop, which clones to its own folder — do
   NOT re-clone here: run `install.sh` from that clone and it SYMLINKS `~/.claude-code-dialogue` to it
   (ONE physical copy — **your clone IS the engine**, managed where it was cloned; no hidden duplicate).
   `install.sh` also repoints that clone's git `origin` to the canonical GitHub repo (overwriting any
   fork/custom remote), so `git pull` always fetches our updates.
2. **Run the installer from inside the project** the user wants to enable:
   ```bash
   cd <the project directory>
   <engine-home>/install.sh
   ```
   It is idempotent: it creates the venv (Python 3 + `watchdog`) and puts `dlg` on
   `~/.local/bin` **only if missing**, then **attaches** the current project.
3. **Verify:**
   - `dlg status` runs without error (shows the project roster + boards).
   - `~/.local/bin/dlg` exists and resolves to the engine's `dialogue/dlg`.
   - The project now has `.dialogue/` (data) and `.claude/commands/dialogue-*.md` (slash commands).
4. If `~/.local/bin` is **not on the user's PATH**, tell them to add it.
5. **Report** to the user in 2-3 lines: engine ready (or already present), this project attached,
   and that they can now register an instance with `/dialogue-onboard <name> <domain>`.

## Notes
- **Updating the tool:** `cd ~/.claude-code-dialogue && git pull` (if it is a SYMLINK to your clone,
  this resolves through the link and pulls the clone — or pull the clone directly, CLI or in your GUI
  git client). `install.sh` points the git origin at GitHub, so `git pull` fetches the latest engine
  code and the ALFA hooks (Stop + PreToolUse, referenced by absolute path in each project's
  `settings.json`, so they update automatically). The per-project `/dialogue-*` commands are **copies**
  made by `dlg attach` — to pick up command changes in an already-attached project, re-run `dlg attach`
  there. (A future version will symlink them so `git pull` covers them too.)
- **Don't move or delete the clone** the engine is symlinked to: it would break `~/.claude-code-dialogue`
  (a broken symlink → `dlg` fails with a clear error). If you must move it, re-run `install.sh` from the
  new location.
- To enable additional projects later: `cd <other-project> && dlg attach` (no reinstall).
- The venv belongs to the **tool** (it gives Python access to `watchdog`), not to the Claude
  instances. One per installation.
- Troubleshooting: if `import watchdog` fails at runtime, re-run `install.sh` — it repairs the
  venv dependencies.
- Do not invent configuration: this tool needs no network, no database, no API keys.
