"""Tests del portero: se ejecuta el hook igual que lo haría Claude Code (JSON por stdin)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "portero" / "portero.py"


def run(prompt, home):
    env = dict(os.environ, PORTERO_HOME=str(home))
    out = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"prompt": prompt, "session_id": "test"}),
        capture_output=True, text=True, env=env, timeout=10,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout) if out.stdout.strip() else None


def tier_of(result):
    if result is None:
        return "MEDIO"
    ctx = result["hookSpecificOutput"]["additionalContext"]
    return "LIGERO" if "LIGERA" in ctx else "DIFICIL"


class PorteroTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_tarea_ligera_va_a_haiku(self):
        r = run("lista los archivos de src", self.home)
        self.assertEqual(tier_of(r), "LIGERO")
        self.assertIn('model="haiku"', r["hookSpecificOutput"]["additionalContext"])

    def test_tarea_dificil_va_a_opus(self):
        r = run("depura este deadlock y revisa la arquitectura de concurrencia", self.home)
        self.assertEqual(tier_of(r), "DIFICIL")

    def test_tarea_media_no_anade_tokens(self):
        self.assertIsNone(run("añade un botón de guardar al formulario de perfil de usuario", self.home))

    def test_forzar_modelo(self):
        self.assertEqual(tier_of(run("!opus lista archivos", self.home)), "DIFICIL")
        self.assertEqual(tier_of(run("!haiku diseña la arquitectura", self.home)), "LIGERO")

    def test_comandos_no_llegan_al_modelo(self):
        r = run("portero", self.home)
        self.assertEqual(r["decision"], "block")

    def test_cambiar_modo_y_apagar(self):
        self.assertIn("off", run("portero modo off", self.home)["reason"])
        self.assertIsNone(run("depura el deadlock de la arquitectura", self.home))

    def test_stats_cuenta_mensajes(self):
        run("lista los archivos", self.home)
        run("depura la arquitectura de seguridad", self.home)
        reason = run("portero stats", self.home)["reason"]
        self.assertIn("2 mensajes", reason)

    def test_el_log_no_guarda_el_texto_del_prompt(self):
        run("lista mi contraseña secreta", self.home)
        log = (self.home / "log.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("contraseña", log)

    def test_entrada_invalida_no_rompe_claude(self):
        env = dict(os.environ, PORTERO_HOME=str(self.home))
        out = subprocess.run([sys.executable, str(HOOK)], input="no es json",
                             capture_output=True, text=True, env=env)
        self.assertEqual(out.returncode, 0)


if __name__ == "__main__":
    unittest.main()
