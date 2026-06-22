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
   If you are reading this from a clone in another location, `install.sh` still sets the engine up at
   `~/.claude-code-dialogue` and points its git origin at GitHub, so `git pull` updates always work.
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
- **Updating the tool:** `cd ~/.claude-code-dialogue && git pull`. `install.sh` points the engine's
  git origin at GitHub, so `git pull` fetches the latest engine code and the ALFA Stop-hook (referenced
  by absolute path in each project's `settings.json`, so it updates automatically). The per-project
  `/dialogue-*` commands are **copies** made by `dlg attach` — to pick up command changes in an
  already-attached project, re-run `dlg attach` there. (A future version will symlink them so `git pull`
  covers them too.)
- To enable additional projects later: `cd <other-project> && dlg attach` (no reinstall).
- The venv belongs to the **tool** (it gives Python access to `watchdog`), not to the Claude
  instances. One per installation.
- Troubleshooting: if `import watchdog` fails at runtime, re-run `install.sh` — it repairs the
  venv dependencies.
- Do not invent configuration: this tool needs no network, no database, no API keys.
