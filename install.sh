#!/usr/bin/env bash
# install.sh - self-bootstrap. Run from INSIDE a project.
#
#   1) is the ENGINE on the Mac (~/.claude-code-dialogue + dlg on the PATH)?  no -> install it
#      (once only, idempotent: skips if already there).
#   2) ATTACH the current project (always).
#
# So machine-setup and project-init are ONE gesture. On a new project:
# re-run the same line, it skips the install and attaches that project.
#
# Usage (setup + 1st project):  git clone <repo> ~/.claude-code-dialogue && cd <project> && ~/.claude-code-dialogue/install.sh
# Usage (later projects):       cd <other-project> && dlg attach
# NB: the repo is PUBLIC -> `git clone` needs no GitHub auth, and a curl|bash bootstrap from raw works.
set -euo pipefail

ENGINE_HOME="$HOME/.claude-code-dialogue"
GITHUB_URL="https://github.com/Giampaolo78/claude-code-dialogue.git"   # canonical public repo: the engine MUST track this so `git pull` gets updates (fix S1)
THIS_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # where this script runs from (the clone)
TARGET_PROJECT="$PWD"

# --- 1) ENGINE (once per Mac; every step is idempotent: does only what's missing) ---
# The engine MUST live at $ENGINE_HOME: `dlg` and the ALFA hooks reference it by that absolute path.
# We do NOT clone a SECOND physical copy of the user's clone here: a separate copy silently diverges
# from the clone the user manages in a GUI git client (they pull their clone, but the hidden engine
# copy never updates). Instead, when this installer runs from a clone OUTSIDE $ENGINE_HOME, we SYMLINK
# $ENGINE_HOME -> that clone: ONE physical repo, managed where the user cloned it; a `git pull` there
# (CLI or GUI) updates the engine through the link.
if [ "$THIS_REPO" != "$ENGINE_HOME" ]; then
  if [ -L "$ENGINE_HOME" ]; then
    cur="$(readlink "$ENGINE_HOME")"
    if [ ! -e "$ENGINE_HOME" ]; then
      # broken symlink (the clone it pointed to was moved/deleted) -> nothing live to lose, relink here
      echo "[install] $ENGINE_HOME was a BROKEN symlink (-> $cur, gone) -> relinking to $THIS_REPO"
      rm -f "$ENGINE_HOME" && ln -s "$THIS_REPO" "$ENGINE_HOME"
    elif [ "$cur" != "$THIS_REPO" ]; then
      echo "[install] WARNING: $ENGINE_HOME already links to a different clone:"
      echo "                   $cur  (not relinking; rm it and re-run to switch clones)"
    fi
  elif [ -e "$ENGINE_HOME" ]; then
    echo "[install] note: $ENGINE_HOME already exists (a real dir, not a symlink) -> using it as the engine."
  elif [ -d "$THIS_REPO/.git" ]; then
    echo "[install] linking engine: $ENGINE_HOME -> $THIS_REPO (single copy, managed at your clone)"
    ln -s "$THIS_REPO" "$ENGINE_HOME"
  else
    echo "[install] no local clone here -> cloning the engine from GitHub into $ENGINE_HOME"
    git clone -q "$GITHUB_URL" "$ENGINE_HOME"
  fi
fi
# the engine MUST track GitHub (not a local clone) so `git pull` always pulls our updates (fix S1).
# idempotent: repoint whatever origin to the canonical URL, or add it if the engine has no remote yet.
if [ -d "$ENGINE_HOME/.git" ]; then
  if git -C "$ENGINE_HOME" remote get-url origin >/dev/null 2>&1; then
    git -C "$ENGINE_HOME" remote set-url origin "$GITHUB_URL"
  else
    git -C "$ENGINE_HOME" remote add origin "$GITHUB_URL"
  fi
fi
# create the venv if the python is missing (also applies if ~/.claude-code-dialogue is cloned by hand from GitHub)
if [ ! -x "$ENGINE_HOME/.venv/bin/python" ]; then
  echo "[install] creating the venv"
  python3 -m venv "$ENGINE_HOME/.venv"
fi
# install/repair the dependencies if watchdog is not importable (e.g. install interrupted halfway:
# before, the check was on python only -> a venv without watchdog passed and crashed at runtime)
if ! "$ENGINE_HOME/.venv/bin/python" -c "import watchdog" 2>/dev/null; then
  echo "[install] installing the dependencies (watchdog)"
  "$ENGINE_HOME/.venv/bin/pip" install -q --disable-pip-version-check -r "$ENGINE_HOME/requirements.txt"
fi
# dlg on the PATH (idempotent)
mkdir -p "$HOME/.local/bin"
ln -sf "$ENGINE_HOME/dialogue/dlg" "$HOME/.local/bin/dlg"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "[install] NB: add ~/.local/bin to your PATH";; esac
echo "[install] engine ready: dlg -> ~/.local/bin/dlg"

# --- 2) ATTACH the current project (always) ---
"$ENGINE_HOME/attach.sh" "$TARGET_PROJECT"
