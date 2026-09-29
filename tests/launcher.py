#!/usr/bin/env python3
"""Check the real QML launcher without starting or changing a desktop session."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def run():
    with tempfile.TemporaryDirectory(prefix="equal-tiling-launcher-") as temporary:
        root = Path(temporary)
        result = root / "environment.json"
        shutil.copyfile(ROOT / "Service.qml", root / "Service.qml")
        (root / "shell.qml").write_text("import Quickshell\nShellRoot { Service {} }\n")
        (root / "service.py").write_text('''import json, os, sys
from pathlib import Path
result = Path(__file__).with_name("environment.json")
temporary = result.with_suffix(".tmp")
temporary.write_text(json.dumps({
    "environment": dict(os.environ), "no_site": sys.flags.no_site,
    "ignore_environment": sys.flags.ignore_environment,
    "executable": sys.executable,
}))
temporary.replace(result)
''')
        (root / "python3").write_text("#!/bin/sh\nexit 99\n")
        (root / "python3").chmod(0o755)
        (root / "sitecustomize.py").write_text("raise RuntimeError('Unexpected Python startup hook')\n")
        env = dict(os.environ, HOME=str(root), QT_QPA_PLATFORM="offscreen",
                   PATH=f"{root}:/usr/bin", PYTHONPATH=str(root),
                   CC="/missing/cc", CMAKE_TOOLCHAIN_FILE="/missing/toolchain",
                   XDG_CACHE_HOME=str(root / "cache"), XDG_STATE_HOME=str(root / "state"))
        with (root / "shell.log").open("w+") as log:
            process = subprocess.Popen(["/usr/bin/qs", "-p", str(root)], env=env,
                                       stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 10
                while not result.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(.05)
                if not result.exists():
                    log.seek(0)
                    raise AssertionError(f"QML launcher did not start the worker:\n{log.read()}")
                data = json.loads(result.read_text())
                allowed = {"HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR",
                           "HYPRLAND_INSTANCE_SIGNATURE", "DBUS_SESSION_BUS_ADDRESS"}
                expected = {name: env[name] for name in allowed if env.get(name)}
                expected.update(PATH="/usr/bin", LC_ALL="C.UTF-8")
                assert data["environment"] == expected, "Worker inherited unexpected environment settings"
                assert data["no_site"] and data["ignore_environment"]
                assert data["executable"] == "/usr/bin/python3"
                print("PASS: real QML launcher uses system Python and only the permitted session environment")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    run()
