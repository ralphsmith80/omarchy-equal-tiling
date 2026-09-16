"""Check service cancellation and restart without changing a desktop session."""

from contextlib import ExitStack, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
with patch.dict(sys.modules):
    spec = importlib.util.spec_from_file_location("install", ROOT / "install.py")
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    sys.modules["install"] = installer
    spec = importlib.util.spec_from_file_location("equal_tiling_service", ROOT / "service.py")
    service = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(service)


class ServiceLifecycleTest(unittest.TestCase):
    def test_enable_during_cleanup_restarts_after_releasing_session_lock(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary)
            desired = {"enabled": True}
            native = {"plugin": None}
            restarts = []
            reloads = []

            def activate(_build, _load_native):
                native["plugin"] = {"name": "hy3", "handle": "owned"}
                # Disable as soon as activation finishes, before the event loop.
                desired["enabled"] = False

            def ctl(*args):
                if args == ("version", "-j"):
                    return json.dumps({"commit": "testcommit"})
                if args == ("plugin", "list", "-j"):
                    return json.dumps([])
                if args == ("reload",):
                    reloads.append(args)
                    if len(reloads) == 1:
                        desired["enabled"] = True
                        # A newly mounted service loses the old worker's lock.
                        self.assertFalse(service.run())
                    return "ok"
                if args[:2] == ("plugin", "unload"):
                    native["plugin"] = None
                    return "ok"
                self.fail(f"Unexpected IPC call: {args}")

            def restart(executable, arguments):
                # The old worker must release ownership before starting again.
                lock_path = root / "omarchy-equal-tiling/testcommit_session/service.lock"
                with lock_path.open("w") as lock:
                    service.fcntl.flock(lock, service.fcntl.LOCK_EX | service.fcntl.LOCK_NB)
                self.assertIsNone(native["plugin"])
                restarts.append((executable, arguments))

            stack.enter_context(patch.dict(os.environ, {
                "HYPRLAND_INSTANCE_SIGNATURE": "testcommit_session",
                "XDG_RUNTIME_DIR": str(root),
            }))
            stack.enter_context(patch.object(service, "STOP", False))
            stack.enter_context(patch.object(service, "enabled", side_effect=lambda: desired["enabled"]))
            stack.enter_context(patch.object(service, "source_revision", return_value="revision"))
            stack.enter_context(patch.object(service, "native_build_dir", return_value=root / "build"))
            stack.enter_context(patch.object(service, "build_while_enabled", return_value=True))
            stack.enter_context(patch.object(service, "apply_layout", side_effect=activate))
            stack.enter_context(patch.object(service, "loaded_hy3", side_effect=lambda: native["plugin"]))
            stack.enter_context(patch.object(service, "ctl", side_effect=ctl))
            stack.enter_context(patch.object(service, "xdg", return_value=root / "state"))
            stack.enter_context(patch.object(Path, "read_text", return_value='"testcommit"'))
            stack.enter_context(patch.object(service.socket, "socket"))
            stack.enter_context(patch.object(service.select, "select", return_value=([], [], [])))
            stack.enter_context(patch.object(service.os, "dup2"))
            stack.enter_context(patch.object(service.os, "execv", side_effect=restart))
            stack.enter_context(patch.object(service.signal, "signal"))
            stack.enter_context(patch.object(sys, "argv", ["service.py"]))
            stack.enter_context(redirect_stdout(io.StringIO()))
            service.main()
            self.assertEqual(len(restarts), 1)
            self.assertEqual(len(reloads), 2)

    def test_sigterm_releases_native_build_lock(self):
        script = """
from pathlib import Path
import signal
import sys
import install
install.BUILD = Path(sys.argv[1])
with install.build_lock():
    print("locked", flush=True)
    signal.pause()
"""
        with tempfile.TemporaryDirectory() as temporary:
            build = Path(temporary)
            process = subprocess.Popen(
                [sys.executable, "-B", "-c", script, str(build)],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                self.assertTrue(select.select([process.stdout], [], [], 5)[0], "Build did not acquire its lock")
                self.assertEqual(process.stdout.readline().strip(), "locked")
                with patch.object(installer, "BUILD", build):
                    with self.assertRaisesRegex(ValueError, "Another native build"):
                        with installer.build_lock():
                            self.fail("Concurrent build acquired the lock")
                    process.terminate()
                    process.wait(timeout=5)
                    # The marker still exists, but kernel ownership is gone.
                    with installer.build_lock():
                        self.assertTrue((build / ".build.lock").is_file())
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
