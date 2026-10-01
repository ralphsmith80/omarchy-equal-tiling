#!/usr/bin/env python3
"""Capture real tiling in a disposable desktop with public demo text only."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from plugin_session import stop, wait_for

ROOT = Path(__file__).resolve().parents[1]


def run():
    parent_display = Path(os.environ["XDG_RUNTIME_DIR"]) / os.environ["WAYLAND_DISPLAY"]
    # Keep Unix socket paths below Linux's 108-byte limit.
    with tempfile.TemporaryDirectory(prefix="eqp-", dir="/tmp") as temporary:
        root = Path(temporary)
        home, runtime = root / "home", root / "rt"
        runtime.mkdir(mode=0o700)
        config = home / ".config/hypr/hyprland.lua"
        config.parent.mkdir(parents=True)
        config.write_text('''dofile("/usr/share/omarchy/default/hypr/bootstrap.lua")
hl.monitor({output="", mode="preferred", position="0x0", scale=1})
hl.config({general={gaps_in=6,gaps_out=12}, input={follow_mouse=0},
  animations={enabled=false}, misc={disable_hyprland_logo=true,disable_splash_rendering=true}})
o={bind=function(key, description, action, opts) hl.bind(key, action, opts or {}) end}
''')
        env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
                   XDG_CACHE_HOME=str(home / ".cache"), XDG_STATE_HOME=str(home / ".local/state"),
                   XDG_RUNTIME_DIR=str(runtime), WAYLAND_DISPLAY=str(parent_display),
                   AQ_DRM_DEVICES="/dev/null")
        env.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
        env.pop("DISPLAY", None)
        subprocess.run(["/usr/bin/python3", str(ROOT / "install.py"), "--home", str(home), "--apply"],
                       env=env, check=True, stdout=subprocess.DEVNULL)
        # Use Omarchy's Tokyo Night colors in otherwise plain terminal windows.
        foot = root / "foot.ini"
        foot.write_text("[main]\nfont=monospace:size=17\npad=24x20\n"
                        "[colors-dark]\nbackground=1a1b26\nforeground=c0caf5\n")
        samples = {
            "A": "COSMIC-style equal tiling\n\nOmarchy + patched hy3\n\n"
                 "Equal space within each group.\n\n"
                 "One window on the left.\nThree equal windows on the right.\n\n"
                 "Resize by hand. Your sizes stay.\n\n"
                 "github.com/ralphsmith80/\nomarchy-equal-tiling",
            "B": "FOCUS\n\nSuper + arrows\n\nFollow the layout tree.",
            "C": "MOVE\n\nSuper + Shift + arrows\n\nMove through tiling groups.",
            "D": "PRIORITY COLUMN\n\nSuper + Alt + P\n\nGive the middle of three columns half the width.",
        }
        for label, content in samples.items():
            (root / f"{label}.py").write_text(
                "import signal\nprint(" + repr("\033[?25l" + content) + ", flush=True)\nsignal.pause()\n")
        with (root / "session.log").open("w+") as log:
            terminals = []
            compositor = subprocess.Popen(["Hyprland", "--config", str(config)], env=env,
                                          stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                wait_for(lambda: list((runtime / "hypr").glob("*/.socket.sock")))
                env["HYPRLAND_INSTANCE_SIGNATURE"] = next((runtime / "hypr").glob("*/.socket.sock")).parent.name
                wait_for(lambda: any(path.is_socket() for path in runtime.glob("wayland-*")))
                env["WAYLAND_DISPLAY"] = str(next(path for path in runtime.glob("wayland-*") if path.is_socket()))

                def ctl(*args):
                    return subprocess.check_output(["hyprctl", *args], env=env, text=True, timeout=5).strip()

                def evaluate(code):
                    result = ctl("eval", code)
                    assert result == "ok", result
                    time.sleep(.2)

                def windows():
                    return {window["title"]: window for window in json.loads(ctl("clients", "-j"))}

                assert any(plugin["name"] == "hy3" for plugin in json.loads(ctl("plugin", "list", "-j")))
                # Only resize this script's temporary window in the parent desktop.
                def preview_window():
                    clients = json.loads(subprocess.check_output(["hyprctl", "clients", "-j"], text=True, timeout=5))
                    return next((window for window in clients if window["pid"] == compositor.pid), None)
                wait_for(preview_window)
                window = preview_window()
                code = 'hl.dispatch(hl.dsp.focus({window="address:' + window["address"] + '"}))'
                if not window["floating"]:
                    code += '; hl.dispatch(hl.dsp.window.float({action="toggle"}))'
                code += '; hl.dispatch(hl.dsp.window.resize({x=1600,y=900}))'
                subprocess.run(["hyprctl", "eval", code], check=True, stdout=subprocess.DEVNULL, timeout=5)
                wait_for(lambda: any(m["width"] == 1600 and m["height"] == 900 for m in json.loads(ctl("monitors", "-j"))))
                for label in samples:
                    terminals.append(subprocess.Popen(["foot", f"--config={foot}", f"--title={label}",
                                      "/usr/bin/python3", str(root / f"{label}.py")],
                                     env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True))
                    wait_for(lambda: label in windows())
                    evaluate('hl.dispatch(hl.dsp.focus({window="address:' + windows()[label]["address"] + '"}))')
                    if label == "B":
                        evaluate('hl.dispatch(hl.plugin.hy3.change_group("h"))')
                        evaluate('hl.dispatch(hl.plugin.hy3.make_group("v", {ephemeral=true}))')
                    elif label == "C":
                        evaluate('hl.dispatch(hl.plugin.hy3.make_group("h", {ephemeral=true}))')
                for direction in ("r", "r", "l", "l"):
                    evaluate('hl.dispatch(hl.plugin.hy3.move_cosmic("' + direction + '"))')
                current = windows()
                assert set(current) == set(samples)
                assert len({current[label]["at"][0] for label in "BCD"}) == 1
                assert max(current[label]["size"][1] for label in "BCD") - min(current[label]["size"][1] for label in "BCD") <= 2
                assert abs(current["A"]["size"][0] - current["B"]["size"][0]) <= 2
                assert current["A"]["at"][0] < current["B"]["at"][0], current
                assert not ctl("configerrors"), ctl("configerrors")
                # Hide the expected direct-launch notice in this test compositor.
                assert ctl("dismissnotify", "-1") == "ok"
                time.sleep(.5)
                subprocess.run(["grim", str(ROOT / "preview.png")], env=env, check=True, timeout=10)
                print("Captured preview.png from four real tiled windows in the disposable desktop.")
            except BaseException:
                log.seek(0)
                print(log.read()[-4000:])
                raise
            finally:
                for terminal in terminals:
                    stop(terminal)
                stop(compositor)


if __name__ == "__main__":
    run()
