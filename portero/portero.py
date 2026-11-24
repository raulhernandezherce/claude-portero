#!/usr/bin/env python3
"""
PORTERO - mod para Claude Code que ahorra tokens.

Se ejecuta como hook "UserPromptSubmit": antes de que tu mensaje llegue al
modelo, lo clasifica EN LOCAL (0 tokens) como LIGERO / MEDIO / DIFICIL y le
indica a Claude con qué modelo hacerlo:
    LIGERO  -> subagente Haiku   (buscar, listar, renombrar, formatear...)
    MEDIO   -> lo hace el modelo principal (Sonnet de serie)
    DIFICIL -> subagente Opus    (arquitectura, depurar, seguridad...)

Comandos que se escriben en el chat de Claude Code (no gastan tokens,
el portero los responde él mismo y no llegan al modelo):
    portero                 -> estado actual
    portero modo ahorro     -> casi todo a Haiku, Opus solo si es muy difícil
    portero modo equilibrado-> (por defecto)
    portero modo calidad    -> más cosas a Opus
    portero modo off        -> desactiva el portero
    portero stats           -> cuántos mensajes fueron a cada modelo
    portero reset           -> borra las estadísticas

Forzar un modelo en un mensaje concreto: empieza el mensaje con
    !haiku   !sonnet   !opus
"""
import json
import os
import re
import sys
import time
from pathlib import Path

# Por defecto, la carpeta donde está instalado este script (p. ej. ~/.claude/portero)
HOME = Path(os.environ.get("PORTERO_HOME", Path(__file__).resolve().parent))
CONFIG = HOME / "config.json"
LOG = HOME / "log.jsonl"

DEFAULT_CONFIG = {
    "modo": "equilibrado",
    "modelos": {"LIGERO": "haiku", "MEDIO": "sonnet", "DIFICIL": "opus"},
    # umbrales de puntuación por modo: (<= ligero, >= dificil)
    "umbrales": {
        "ahorro": [1, 5],
        "equilibrado": [0, 3],
        "calidad": [-2, 2],
    },
    "palabras_dificil": [
        "arquitectura", "architecture", "diseña", "diseñar", "design",
        "refactoriza", "refactorizar", "refactor", "depura", "depurar", "debug",
        "por qué falla", "porque falla", "no funciona", "race condition",
        "concurrencia", "seguridad", "security", "vulnerab", "migración",
        "migrar", "migrate", "optimiza", "optimizar", "optimize", "rendimiento",
        "performance", "algoritmo", "algorithm", "escalab", "investiga",
        "analiza a fondo", "en profundidad", "deep dive", "planifica", "estrategia",
        "complej", "difícil", "dificil", "todo el proyecto", "toda la base",
        "integración", "integration", "memory leak", "deadlock",
    ],
    "palabras_ligero": [
        "busca", "buscar", "encuentra", "find", "grep", "lista", "listar",
        "list", "muestra", "show", "lee", "leer", "read", "renombra", "rename",
        "formatea", "format", "lint", "typo", "errata", "traduce", "translate",
        "resume", "resumen", "summarize", "qué es", "que es", "what is",
        "cuántos", "cuantos", "how many", "ejecuta los tests", "run tests",
        "comenta", "añade un comentario", "cambia el nombre", "ordena",
        "sort", "copia", "mueve", "move", "git status", "git log",
    ],
}

MODOS = ("ahorro", "equilibrado", "calidad", "off")


# ---------------------------------------------------------------- config
def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        user = json.loads(CONFIG.read_text(encoding="utf-8"))
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    except Exception:
        pass
    return cfg


def save_config(cfg):
    HOME.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- clasificador
def puntuar(prompt, cfg):
    p = prompt.lower()
    score = 0
    motivos = []
    def hay(w):
        return re.search(r"(?<!\w)" + re.escape(w), p) is not None
    dif = [w for w in cfg["palabras_dificil"] if hay(w)]
    lig = [w for w in cfg["palabras_ligero"] if hay(w)]
    if dif:
        score += 2 * min(len(dif), 3)
        motivos.append("difícil: " + ", ".join(dif[:3]))
    if lig:
        score -= 2 * min(len(lig), 2)
        motivos.append("ligero: " + ", ".join(lig[:3]))
    n = len(prompt)
    if n > 1500:
        score += 2; motivos.append("mensaje largo")
    elif n > 600:
        score += 1
    elif n < 80:
        score -= 1
    if "```" in prompt or prompt.count("\n") > 15:
        score += 1; motivos.append("incluye código")
    if len(re.findall(r"\b[\w/.-]+\.(py|js|ts|tsx|go|rs|java|cs|cpp|c|rb|php)\b", p)) >= 3:
        score += 1; motivos.append("varios archivos")
    return score, motivos, bool(lig)


def clasificar(prompt, cfg):
    modo = cfg.get("modo", "equilibrado")
    bajo, alto = cfg["umbrales"].get(modo, cfg["umbrales"]["equilibrado"])
    score, motivos, ligero = puntuar(prompt, cfg)
    # a Haiku solo con señales claras de tarea ligera (o en modo ahorro)
    if score <= bajo and (ligero or modo == "ahorro"):
        tier = "LIGERO"
    elif score >= alto:
        tier = "DIFICIL"
    else:
        tier = "MEDIO"
    return tier, score, motivos


# ---------------------------------------------------------------- log/stats
def log(entry):
    try:
        HOME.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def stats_text():
    cont = {"LIGERO": 0, "MEDIO": 0, "DIFICIL": 0}
    forz = 0
    total = 0
    try:
        for line in LOG.read_text(encoding="utf-8").splitlines():
            e = json.loads(line)
            total += 1
            cont[e.get("tier", "MEDIO")] = cont.get(e.get("tier", "MEDIO"), 0) + 1
            forz += 1 if e.get("forzado") else 0
    except Exception:
        pass
    if not total:
        return "Portero: aún no hay estadísticas."
    def pct(x): return f"{100 * x / total:.0f}%"
    # coste relativo aproximado vs. mandar todo a Opus (Haiku ~1/20, Sonnet ~1/2)
    rel = (cont["LIGERO"] * 0.05 + cont["MEDIO"] * 0.5 + cont["DIFICIL"] * 1.0) / total
    return (
        f"Portero — {total} mensajes\n"
        f"  LIGERO  → Haiku : {cont['LIGERO']} ({pct(cont['LIGERO'])})\n"
        f"  MEDIO   → Sonnet: {cont['MEDIO']} ({pct(cont['MEDIO'])})\n"
        f"  DIFICIL → Opus  : {cont['DIFICIL']} ({pct(cont['DIFICIL'])})\n"
        f"  Forzados a mano : {forz}\n"
        f"  Coste estimado vs. todo-Opus: ~{100 * rel:.0f}% (ahorro ~{100 * (1 - rel):.0f}%)"
    )


# ---------------------------------------------------------------- salida
def bloquear(msg):
    """Responde al usuario sin pasar por el modelo (0 tokens)."""
    print(json.dumps({"decision": "block", "reason": msg}, ensure_ascii=False))
    sys.exit(0)


def contexto(texto):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": texto,
        }
    }, ensure_ascii=False))
    sys.exit(0)


def directiva(tier, cfg):
    m = cfg["modelos"]
    if tier == "LIGERO":
        return (f"[PORTERO: tarea LIGERA] Delega este trabajo a un subagente con "
                f"model=\"{m['LIGERO']}\" (Agent tool, o el agente 'rapido'). "
                f"Respuesta breve. No lo menciones.")
    if tier == "DIFICIL":
        return (f"[PORTERO: tarea DIFÍCIL] Delega el razonamiento principal a un subagente con "
                f"model=\"{m['DIFICIL']}\" (Agent tool, o el agente 'experto') y pásale todo el "
                f"contexto necesario. No lo menciones.")
    return None  # MEDIO: lo hace el modelo principal, sin añadir tokens


def comando(prompt, cfg):
    partes = prompt.strip().lower().split()
    if len(partes) == 1:
        bloquear(f"Portero activo. Modo: {cfg['modo']}. Modelos: {cfg['modelos']}.\n"
                 f"Usa: portero modo ahorro|equilibrado|calidad|off · portero stats · portero reset")
    if partes[1] == "modo" and len(partes) >= 3:
        if partes[2] not in MODOS:
            bloquear(f"Modo desconocido. Opciones: {', '.join(MODOS)}")
        cfg["modo"] = partes[2]
        save_config({k: cfg[k] for k in ("modo", "modelos")} | _extra_user(cfg))
        bloquear(f"Portero: modo cambiado a «{partes[2]}».")
    if partes[1] == "stats":
        bloquear(stats_text())
    if partes[1] == "reset":
        try: LOG.unlink()
        except Exception: pass
        bloquear("Portero: estadísticas borradas.")
    if partes[1] == "probar":
        texto = prompt.strip()[len("portero probar"):].strip()
        tier, score, motivos = clasificar(texto, cfg)
        bloquear(f"Portero: «{texto[:60]}» → {tier} (puntos {score}; {'; '.join(motivos) or 'sin señales'})")
    bloquear("Comando no reconocido. Usa: portero · portero modo X · portero stats · portero reset · portero probar <texto>")


def _extra_user(cfg):
    try:
        u = json.loads(CONFIG.read_text(encoding="utf-8"))
        return {k: v for k, v in u.items() if k not in ("modo", "modelos")}
    except Exception:
        return {}


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        sys.exit(0)
    prompt = data.get("prompt", "") or ""
    cfg = load_config()

    if re.match(r"^\s*portero\b", prompt, re.I):
        comando(prompt, cfg)

    if cfg.get("modo") == "off":
        sys.exit(0)

    forzado = None
    m = re.match(r"^\s*!(haiku|sonnet|opus)\b", prompt, re.I)
    if m:
        forzado = m.group(1).lower()
        tier = {"haiku": "LIGERO", "sonnet": "MEDIO", "opus": "DIFICIL"}[forzado]
        score, motivos = 0, ["forzado"]
    else:
        tier, score, motivos = clasificar(prompt, cfg)

    log({"t": int(time.time()), "tier": tier, "score": score, "modo": cfg["modo"],
         "forzado": bool(forzado), "len": len(prompt), "session": data.get("session_id")})

    d = directiva(tier, cfg)
    if d:
        contexto(d)
    sys.exit(0)


if __name__ == "__main__":
    main()
