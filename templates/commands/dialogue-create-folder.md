Create a new board (folder) in the `<project>` dialogue system: given name + timestamp to the second, inside `boards/<project>/`, with the presence sub-folder. No analysis, no preamble: create it and report the path.

Base board name = `$ARGUMENTS`. If it's empty, ask for the name and stop.

Run EXACTLY this single bash command:

```bash
# (<dlg> = absolute path to dlg, substituted at attach -- no PATH needed, no cd)
NAME="$ARGUMENTS"
[ -z "$NAME" ] && { echo "ERROR: pass the name, e.g. /dialogue-create-folder task-reorganization"; exit 1; }
TS=$(date +%Y%m%d_%H%M%S)
SLUG=$(printf '%s' "$NAME" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9_-]+/_/g; s/_+/_/g; s/^[_-]+//; s/[_-]+$//')
DIR="boards/<project>/${SLUG}-${TS}"
mkdir -p "$DIR/_presence"
echo "Board created: $DIR  (with _presence/ inside)"
```

Then report to the user the exact path created (the printed line).

Correctness notes (do NOT change them):
- The presence folder is named `_presence` (with underscore): it's the dialogue convention (`boards.py` -> `bd / "_presence"`). A `presence` without underscore would NOT be recognized by `<dlg> join/say/present`.
- The name is normalized with the SAME rule as `boards.slug()` (lowercase, only `[a-z0-9_-]`, no double `_`), so when someone does `<dlg> say <project> <board> ...` it resolves to the same folder and doesn't create a duplicate.
- Timestamp `YYYYMMDD_HHMMSS` to the second, always inside `boards/<project>/`.
