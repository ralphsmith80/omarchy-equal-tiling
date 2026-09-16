#!/usr/bin/env python3
"""Own a temporary tiling layout while the Omarchy service is enabled."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import sys
import time

import install

PLUGIN_ID = "ralphsmith80.equal-tiling"
ROOT = Path(__file__).resolve().parent
STOP = False


def xdg(name, fallback):
    return Path(os.environ.get(name) or Path.home() / fallback)


def config_path():
    return Path.home() / ".config/omarchy/shell.json"


def enabled():
    """Read the same service entry as Omarchy, including during removal."""
    if not (ROOT / "manifest.json").is_file():
        return False
    try:
        config = json.loads(config_path().read_text())
        return any(isinstance(entry, dict) and entry.get("id") == PLUGIN_ID
                   for entry in config.get("plugins", []))
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def source_revision():
    digest = hashlib.sha256()
    for name in ("manifest.json", "Service.qml", "service.py", "install.py", "hy3.patch", "config/hypr/equal-tiling.lua"):
        digest.update((ROOT / name).read_bytes())
    return digest.hexdigest()


def lua_string(value):
    # Three-digit decimal escapes quote every UTF-8 byte, including newlines.
    return '"' + ''.join(f'\\{byte:03d}' for byte in str(value).encode()) + '"'


def ctl(*args):
    result = subprocess.run(["hyprctl", *args], capture_output=True, text=True, timeout=5)
    if result.returncode:
        raise RuntimeError(result.stdout.strip() or result.stderr.strip() or "Hyprland IPC failed")
    return result.stdout.strip()


def native_build_dir():
    signature = json.dumps(install.build_signature(), sort_keys=True).encode()
    key = hashlib.sha256(signature).hexdigest()[:20]
    return xdg("XDG_CACHE_HOME", ".cache") / "omarchy-equal-tiling" / key


def notify(message):
    print(message, flush=True)
    try:
        subprocess.run(["notify-send", "Equal tiling", message], timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass


def build_while_enabled():
    """Keep compiler work outside the watched checkout; stop it on disable."""
    process = subprocess.Popen([sys.executable, "-B", str(ROOT / "service.py"), "--build"], start_new_session=True)
    try:
        while process.poll() is None:
            if STOP or not enabled():
                return False
            time.sleep(.2)
        if process.returncode:
            raise RuntimeError("The native build failed. Check the service log and build requirements, then disable and enable the plugin to retry.")
        return True
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


def loaded_hy3():
    return next((plugin for plugin in json.loads(ctl("plugin", "list", "-j"))
                 if plugin.get("name") == "hy3"), None)


def apply_layout(build, load_native):
    commit = (build / "hyprland-commit").read_text().strip()
    if not commit or not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "").startswith(commit + "_"):
        raise RuntimeError("The native build does not match the running Hyprland session.")
    if load_native:
        result = ctl("plugin", "load", str(build / "libhy3-cosmic.so"))
        if result != "ok":
            raise RuntimeError(result)
    code = ('assert(loadfile(' + lua_string(ROOT / "config/hypr/equal-tiling.lua") + '))({'
            + 'loaded=true,plugin_path=' + lua_string(build / "libhy3-cosmic.so") + ','
            + 'stamp_path=' + lua_string(build / "hyprland-commit") + '})')
    result = ctl("eval", 'assert(' + code + ', "Equal tiling could not load for this Hyprland build")')
    if result != "ok":
        raise RuntimeError(result)
    # Saved hy3 workspaces used dwindle during the normal config reload.
    # Now that the plugin is present, restore their actual saved selection.
    result = ctl("eval", 'package.loaded["default.hypr.workspace-layouts"] = nil; require("default.hypr.workspace-layouts")')
    if result != "ok":
        raise RuntimeError(result)


def run():
    signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if not signature or not runtime or "/" in signature or signature in {".", ".."}:
        raise RuntimeError("Run this service inside an active Hyprland session.")
    state = Path(runtime) / "omarchy-equal-tiling" / signature
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (state / "service.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        # The shell may mount a service just before persisting enabled state.
        for _ in range(30):
            if enabled() or STOP:
                break
            time.sleep(.1)
        if STOP or not enabled():
            return True
        revision = source_revision()
        build = native_build_dir()
        header = Path("/usr/include/hyprland/src/version.h").read_text()
        running_commit = json.loads(ctl("version", "-j"))["commit"]
        if f'"{running_commit}"' not in header:
            raise RuntimeError("Hyprland was updated. Log out and back in before enabling equal tiling.")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as events:
            events.connect(str(Path(runtime) / "hypr" / signature / ".socket2.sock"))
            events.setblocking(False)
            print("Building equal tiling if needed.", flush=True)
            if not build_while_enabled():
                return True
            if not enabled() or STOP:
                return True
            if source_revision() != revision:
                return True
            # Do not apply events from before activation a second time.
            while select.select([events], [], [], 0)[0]:
                if not events.recv(65536):
                    return False
            owned = False
            handle = None
            try:
                # Check for a conflict before taking responsibility for cleanup.
                plugins = json.loads(ctl("plugin", "list", "-j"))
                if any(plugin.get("name") == "hy3" for plugin in plugins):
                    raise RuntimeError("Another hy3 setup is already loaded. Disable its loader before enabling this plugin.")
                owned = True
                apply_layout(build, True)
                handle = loaded_hy3()["handle"]
                print("Equal tiling is active.", flush=True)
                buffer = b""
                while enabled() and not STOP:
                    if source_revision() != revision:
                        return True
                    if select.select([events], [], [], 1)[0]:
                        data = events.recv(65536)
                        if not data:
                            return False
                        buffer += data
                        lines = buffer.split(b"\n")
                        buffer = lines.pop()
                        if any(line.startswith(b"configreloaded>>") for line in lines):
                            if not enabled() or STOP:
                                break
                            plugin = loaded_hy3()
                            if plugin and plugin["handle"] != handle:
                                owned = False
                                raise RuntimeError("The saved configuration now loads another hy3 setup. Equal tiling has stopped.")
                            apply_layout(build, not plugin)
                            handle = loaded_hy3()["handle"]
            finally:
                if owned:
                    try:
                        # Clear Lua callbacks before unloading their native code.
                        ctl("reload")
                        plugin = loaded_hy3()
                        if plugin and (handle is None or plugin["handle"] == handle):
                            ctl("plugin", "unload", str(build / "libhy3-cosmic.so"))
                            ctl("reload")
                        print("Restored the saved Hyprland configuration.", flush=True)
                    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
                        print(f"Could not reload Hyprland during cleanup: {error}", flush=True)
    # A new worker may have lost the lock while this one was cleaning up.
    # Recheck enabled state in main after releasing the lock.
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="Build the native dependency in the user cache")
    args = parser.parse_args()
    if args.build:
        install.BUILD = native_build_dir()
        install.build_hy3()
        return
    log_dir = xdg("XDG_STATE_HOME", ".local/state") / "omarchy-equal-tiling"
    log_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(log_dir / "service.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.dup2(descriptor, 1)
    os.dup2(descriptor, 2)
    os.close(descriptor)
    def stop(_signal, _frame):
        global STOP
        STOP = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        restart = run()
        if restart and enabled() and not STOP:
            os.execv(sys.executable, [sys.executable, "-B", str(ROOT / "service.py")])
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        notify(str(error))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
