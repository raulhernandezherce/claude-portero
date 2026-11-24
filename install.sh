#!/usr/bin/env bash
# Instala el portero, la skill enrutador y los agentes rapido/experto en ~/.claude
# y registra el hook UserPromptSubmit en ~/.claude/settings.json (con copia de seguridad).
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${CLAUDE_HOME:-$HOME/.claude}"
PY="$(command -v python3)"

mkdir -p "$DEST/portero" "$DEST/skills/enrutador" "$DEST/agents"
cp "$SRC/portero/portero.py" "$DEST/portero/portero.py"
cp "$SRC/skills/enrutador/SKILL.md" "$DEST/skills/enrutador/SKILL.md"
cp "$SRC/agents/experto.md" "$SRC/agents/rapido.md" "$DEST/agents/"

"$PY" - "$DEST" "$PY" <<'PYEOF'
import json, shutil, sys, time
from pathlib import Path

dest, py = Path(sys.argv[1]), sys.argv[2]
settings = dest / "settings.json"
data = {}
if settings.exists():
    shutil.copy(settings, settings.with_name(f"settings.json.bak-{int(time.time())}"))
    data = json.loads(settings.read_text(encoding="utf-8") or "{}")

cmd = f'"{py}" "{dest / "portero" / "portero.py"}"'
groups = data.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
already = any("portero.py" in h.get("command", "") for g in groups for h in g.get("hooks", []))
if not already:
    groups.append({"hooks": [{"type": "command", "command": cmd, "timeout": 5}]})
settings.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("Hook ya registrado." if already else "Hook registrado en", settings)
PYEOF

echo "Listo. Abre Claude Code y escribe: portero"
