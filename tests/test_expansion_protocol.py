"""Exercise effort and social controls through the public service transports."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

from theater.render import ROOT
from theater.service import Theater, UnixServer, request


class ExpansionProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.theater = Theater(self.temp.name, seed=5)
        self.sock = Path(self.temp.name) / "control.sock"
        self.server = UnixServer(self.sock, self.theater)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def test_layout_baseline_then_real_effort_change(self):
        layout = {"op": "layout", "layout_key": "test", "width_px": 400,
                  "height_px": 80, "phase": "idle", "effort": "max"}
        self.assertTrue(request(self.sock, layout)["visible"])
        baseline = request(self.sock, {"op": "status"})["state"]
        self.assertEqual(baseline["effort"], "max")
        self.assertIsNone(baseline["spectacle"])
        request(self.sock, dict(layout, effort="ultra"))
        first = request(self.sock, {"op": "status"})["state"]
        self.assertEqual(first["spectacle"]["kind"], "ultra")
        self.assertEqual(len(first["cast"]), 17)
        with self.theater.lock:
            self.theater.world.tick(.4)
        request(self.sock, dict(layout, effort="ultra"))
        repeated = request(self.sock, {"op": "status"})["state"]
        self.assertGreater(repeated["spectacle"]["age"], .3)

    def test_cli_effort_reaches_local_world(self):
        result = subprocess.run(
            [sys.executable, "-m", "theater.cli", "--socket", str(self.sock),
             "effort", "max"], cwd=ROOT, text=True, capture_output=True, check=True)
        state = json.loads(result.stdout)["state"]
        self.assertEqual(state["spectacle"]["kind"], "max")
        self.assertEqual(len(state["cast"]), 4)

    def test_resumed_session_baseline_does_not_start_an_ensemble(self):
        layout = {"op": "layout", "layout_key": "test", "width_px": 400,
                  "height_px": 80, "phase": "idle", "effort": "high"}
        request(self.sock, layout)
        request(self.sock, dict(layout, effort="ultra", effort_baseline=True))
        state = request(self.sock, {"op": "status"})["state"]
        self.assertEqual(state["effort"], "ultra")
        self.assertIsNone(state["spectacle"])
        self.assertEqual(len(state["cast"]), 4)

    def test_steady_native_layout_does_not_cancel_manual_effort_demo(self):
        layout = {"op": "layout", "layout_key": "test", "width_px": 400,
                  "height_px": 80, "phase": "idle", "effort": "high",
                  "effort_baseline": True}
        request(self.sock, layout)
        request(self.sock, {"op": "effort", "value": "max"})
        request(self.sock, layout)
        state = request(self.sock, {"op": "status"})["state"]
        self.assertEqual(state["effort"], "max")
        self.assertEqual(state["spectacle"]["kind"], "max")
        request(self.sock, dict(layout, effort="ultra", effort_baseline=False))
        state = request(self.sock, {"op": "status"})["state"]
        self.assertEqual(state["effort"], "ultra")
        self.assertEqual(state["spectacle"]["kind"], "ultra")

    def test_manual_density_and_scene_interrupt_all_cast_without_losing_pool(self):
        original_pool = request(self.sock, {"op": "status"})["state"]["pool"]
        request(self.sock, {"op": "effort", "value": "ultra"})
        changed = request(self.sock, {"op": "density", "value": 2})["state"]
        self.assertIsNone(changed["spectacle"])
        self.assertEqual(len(changed["cast"]), 2)
        self.assertEqual(changed["pool"], original_pool)
        request(self.sock, {"op": "effort", "value": "high"})
        request(self.sock, {"op": "effort", "value": "ultra"})
        scene = request(self.sock, {"op": "scene", "name": "office"})["state"]
        self.assertIsNone(scene["spectacle"])
        self.assertEqual(scene["environment"], "office")
        self.assertEqual(len(scene["cast"]), 2)

    def test_catalog_describes_personalities_and_new_scenes(self):
        reply = request(self.sock, {"op": "catalog"})
        self.assertEqual(len(reply["catalog"]), 17)
        for character in reply["catalog"]:
            self.assertTrue(character["temperament"])
            self.assertTrue(character["inspiration"])
            self.assertTrue(character["accent"].startswith("#"))
        self.assertTrue({"home", "office", "dinner", "outing"}.issubset(reply["scenes"]))

    def test_mcp_new_scene_controls_real_world(self):
        message = {"jsonrpc": "2.0", "id": 17, "method": "tools/call", "params": {
            "name": "theater_scene", "arguments": {"name": "outing"}}}
        result = subprocess.run(
            [sys.executable, str(ROOT / "plugin/scripts/mcp_server.py")],
            input=json.dumps(message) + "\n", text=True, capture_output=True,
            check=True, env=dict(os.environ, HOME=self.temp.name,
                                 CODEX_THEATER_SOCKET=str(self.sock)))
        response = json.loads(result.stdout)["result"]
        self.assertFalse(response["isError"])
        self.assertEqual(self.theater.world.snapshot()["environment"], "outing")
