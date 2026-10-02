#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow"]
# ///
"""Record the README previews from real key presses in a disposable desktop.

Run `uv run tests/capture_preview.py` after building. It writes `preview.gif`
for the README and a still `preview.png` for the plugin marketplace.
"""
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

from plugin_session import stop, wait_for

ROOT = Path(__file__).resolve().parents[1]
SIZE = (1920, 960)
FPS = 30
# The compositor background. Pixels of this color become the wallpaper.
KEY = (0x2a, 0x16, 0x40)
WALLPAPER = Path("/usr/share/omarchy/themes/tokyo-night/backgrounds/0-winding-road.jpg")
FONTS = Path("/usr/share/fonts/TTF")
TITLE = "Equal tiling for Omarchy"
# Tokyo Night, from Omarchy's theme.
BLUE, PURPLE, RED = (0x7a, 0xa2, 0xf7), (0xbb, 0x9a, 0xf7), (0xf7, 0x76, 0x8e)
FOOT = """[main]
font=JetBrainsMono Nerd Font:size=10
pad=16x12
[colors-dark]
background=1a1b26
foreground=c0caf5
regular0=15161e
regular1=f7768e
regular2=9ece6a
regular3=e0af68
regular4=7aa2f7
regular5=bb9af7
regular6=7dcfff
regular7=a9b1d6
bright0=565f89
bright1=f7768e
bright2=9ece6a
bright3=e0af68
bright4=7aa2f7
bright5=bb9af7
bright6=7dcfff
bright7=c0caf5
"""
TOOLS = ("Hyprland", "hyprctl", "foot", "grim", "ffmpeg", "git", "bat", "eza")
OPENING = "New windows open side by side at equal widths"


def pane_commands(tree):
    """Shell commands for each window. `tree` is an export of the committed files,
    so untracked files and local branch names stay out of the preview."""
    show = f"/usr/bin/python3 {shlex.quote(str(Path(__file__).resolve()))} --show"
    return {
        "log": f"git -C {shlex.quote(str(ROOT))} log --graph --oneline --decorate --decorate-refs=refs/tags "
               "--color=always -n 60 HEAD",
        "code": f"{show} code {shlex.quote(str(tree))} | bat --color=always --theme=ansi "
                "--style=numbers --paging=never --wrap=never --language=cpp",
        "tree": f"cd {shlex.quote(str(tree))} && eza --tree --level=1 --icons=always --color=always "
                "--group-directories-first .",
        "keys": f"{show} keys",
        "logo": f"{show} logo",
    }


def run_pane(command, columns, lines):
    """Run a pane command at a terminal size. Fail if any part of a pipeline fails."""
    env = dict(os.environ, COLUMNS=str(columns), LINES=str(lines))
    return subprocess.run(["/bin/bash", "-c", "set -o pipefail; " + command],
                          capture_output=True, text=True, env=env)


def columns(windows):
    """Distinct column widths, left to right."""
    return [width for _, width in sorted({(w["at"][0], w["size"][0]) for w in windows.values()})]


def equal(widths):
    return max(widths) - min(widths) <= 2


# Each press is a real binding from config/hypr/equal-tiling.lua.
STEPS = [
    ("caption", TITLE), ("wait", 1.4),
    ("caption", OPENING),
    ("open", "log"), ("wait", .9), ("open", "code"), ("wait", .9),
    ("open", "tree"), ("wait", .9), ("open", "keys"), ("wait", 1.1),
    ("press", "SUPER + LEFT", "focus", .5), ("press", "SUPER + LEFT", "focus", .7),
    ("caption", OPENING), ("open", "logo"), ("wait", 1.4),
    ("check", "five equal columns", lambda w: len(columns(w)) == 5 and equal(columns(w))),
    ("press", "SUPER + RIGHT", "focus", .7),
    ("press", "SUPER + SHIFT + RIGHT", "move", 1.3),
    ("press", "SUPER + LEFT", "focus", .7),
    ("press", "SUPER + SHIFT + RIGHT", "move", 1.3),
    ("press", "SUPER + SHIFT + UP", "move", 1.5),
    ("press", "SUPER + DOWN", "focus", .5),
    ("press", "SUPER + RIGHT", "focus", .7),
    ("press", "SUPER + SHIFT + UP", "move", 1.2),
    ("press", "SUPER + SHIFT + UP", "move", 1.5),
    ("press", "SUPER + LEFT", "focus", .7),
    ("check", "a stack of three equal windows",
     lambda w: equal(columns(w)) and equal([w[name]["size"][1] for name in ("logo", "keys", "tree")])),
    ("still",),
    ("press", "SUPER + ALT + P", "priority column", 2.2),
    ("check", "a half-width middle column", lambda w: abs(columns(w)[1] - 2 * columns(w)[0]) <= 4),
    ("press", "SUPER + ALT + P", "equal tiles", 1.6),
    ("check", "three equal columns again", lambda w: len(columns(w)) == 3 and equal(columns(w))),
    ("caption", TITLE), ("wait", 2.2),
]


def show(kind, tree=None):
    """Print one window's content. Runs inside the demo terminals."""
    if kind == "code":
        # The move dispatcher this plugin adds to hy3, with its one-space indents widened.
        lines = (Path(tree) / "hy3.patch").read_text().splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith("+// Move through one"))
        for line in lines[start:]:
            if not line.startswith("+"):
                break
            body = line[1:].lstrip(" ")
            print("    " * (len(line) - 1 - len(body)) + body)
    elif kind == "keys":
        def key(name): return f"\033[1;30;44m {name} \033[0m"
        def heading(color, text): return f"\033[1;{color}m{text}\033[0m"
        def note(text): return f"\033[90m{text}\033[0m"
        print(f"\n {heading(33, 'MOVE')}\n {key('Super')} {key('Shift')} {key('←↑↓→')}\n"
              f" {note('into, across, or out of a group')}\n\n"
              f" {heading(36, 'FOCUS')}\n {key('Super')} {key('←↑↓→')}\n\n"
              f" {heading(35, 'PRIORITY COLUMN')}\n {key('Super')} {key('Alt')} {key('P')}\n"
              f" {note('middle of three gets half')}")
    elif kind == "logo":
        # Omarchy's icon at half size, centered, with a diagonal theme gradient.
        art = [line[::2] for line in Path("/usr/share/omarchy/icon.txt").read_text().splitlines()[::2]]
        width, height = max(map(len, art)), len(art)
        cols, rows = int(os.environ.get("COLUMNS", 80)), int(os.environ.get("LINES", 24))
        print("\n" * max((rows - height - 2) // 2, 0), end="")
        for y, line in enumerate(art):
            cells = "".join(f"\033[38;2;{r};{g};{b}m{ch}" for x, ch in enumerate(line)
                            for r, g, b in [gradient((x / width + y / height) / 2)])
            print(" " * max((cols - width) // 2, 0) + cells + "\033[0m")
        print("\n" + " " * max((cols - 7) // 2, 0) + "\033[1momarchy\033[0m")


def gradient(t):
    stops = (BLUE, PURPLE, RED)
    t = min(max(t, 0), 1) * (len(stops) - 1)
    i = min(int(t), len(stops) - 2)
    return tuple(round(a + (b - a) * (t - i)) for a, b in zip(stops[i], stops[i + 1]))


def window(command):
    """Show a command's output cut to the terminal size. Redraw after each resize."""
    dirty = [True]
    signal.signal(signal.SIGWINCH, lambda *_: dirty.__setitem__(0, True))
    while True:
        if not dirty[0]:
            signal.pause()
            continue
        time.sleep(.12)  # Let a resize animation settle before drawing.
        dirty[0] = False
        size = os.get_terminal_size()
        text = run_pane(command, size.columns, size.lines).stdout
        lines = []
        for line in text.splitlines()[:size.lines - 1]:
            out, seen = [], 0
            for token in re.split(r"(\x1b\[[0-9;]*m)", line):
                out.append(token if token.startswith("\x1b") else token[:max(size.columns - 1 - seen, 0)])
                seen += 0 if token.startswith("\x1b") else len(token)
            lines.append("".join(out) + "\x1b[0m")
        # Hide the cursor and clear scrollback that a resize can pull back into view.
        sys.stdout.write("\x1b[?25l\x1b[3J\x1b[2J\x1b[H" + "\n".join(lines))
        sys.stdout.flush()


class Recorder:
    """Capture about FPS frames per second with a few grim workers."""

    def __init__(self, env, folder):
        self.env, self.folder, self.frames, self.marks, self.errors = env, folder, [], [], []
        self.lock, self.done = threading.Lock(), threading.Event()
        self.start = time.monotonic()
        self.threads = [threading.Thread(target=self.work) for _ in range(3)]

    def __enter__(self):
        for thread in self.threads:
            thread.start()
        return self

    def __exit__(self, *_):
        self.done.set()
        for thread in self.threads:
            thread.join()
        if self.errors:
            raise RuntimeError("Frame capture failed, so the recording is incomplete.") from self.errors[0]
        # Drop slots claimed after the last step finished.
        self.frames = sorted((frame for frame in self.frames if frame), key=lambda frame: frame[1])

    def now(self):
        return time.monotonic() - self.start

    def mark(self, caption):
        self.marks.append((self.now(), caption))

    def work(self):
        while not self.done.is_set():
            with self.lock:
                index = len(self.frames)
                self.frames.append(None)
            time.sleep(max(self.start + index / FPS - time.monotonic(), 0))
            path = self.folder / f"{index:05d}.png"
            at = self.now()
            try:
                subprocess.run(["grim", "-t", "png", "-l", "1", str(path)], env=self.env, check=True, timeout=10)
            except (OSError, subprocess.SubprocessError) as error:
                self.errors.append(error)
                self.done.set()
                return
            self.frames[index] = (path, at)


def record(folder):
    """Play STEPS in a disposable desktop. Return the recorder and the still's time."""
    parent_display = Path(os.environ["XDG_RUNTIME_DIR"]) / os.environ["WAYLAND_DISPLAY"]
    # Keep Unix socket paths below Linux's 108-byte limit.
    with tempfile.TemporaryDirectory(prefix="eqp-", dir="/tmp") as temporary:
        root = Path(temporary)
        home, runtime = root / "home", root / "rt"
        runtime.mkdir(mode=0o700)
        config = home / ".config/hypr/hyprland.lua"
        config.parent.mkdir(parents=True)
        config.write_text(f'''dofile("/usr/share/omarchy/default/hypr/bootstrap.lua")
hl.monitor({{output="", mode="preferred", position="0x0", scale=1}})
hl.config({{general={{gaps_in=6, gaps_out=14, border_size=2, col={{
    active_border={{colors={{"rgba(7aa2f7ff)", "rgba(bb9af7ff)", "rgba(f7768eff)"}}, angle=45}},
    inactive_border="rgba(414868ff)"}}}},
  input={{follow_mouse=0}}, cursor={{invisible=true}},
  misc={{disable_hyprland_logo=true, disable_splash_rendering=true, background_color="rgb({bytes(KEY).hex()})"}}}})
-- Fading windows would blend with the key color.
hl.animation({{leaf="fade", enabled=false}})
test_bindings = {{}}
o = {{bind=function(key, description, action, opts) test_bindings[key]=action; hl.bind(key, action, opts or {{}}) end}}
''')
        env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
                   XDG_CACHE_HOME=str(home / ".cache"), XDG_STATE_HOME=str(home / ".local/state"),
                   XDG_RUNTIME_DIR=str(runtime), WAYLAND_DISPLAY=str(parent_display),
                   AQ_DRM_DEVICES="/dev/null")
        env.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
        env.pop("DISPLAY", None)
        subprocess.run(["/usr/bin/python3", str(ROOT / "install.py"), "--home", str(home), "--apply"],
                       env=env, check=True, stdout=subprocess.DEVNULL)
        foot = root / "foot.ini"
        foot.write_text(FOOT)
        tree = root / "tree"
        tree.mkdir()
        archive = subprocess.run(["git", "-C", str(ROOT), "archive", "HEAD"], check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", str(tree)], input=archive, check=True)
        panes = pane_commands(tree)
        for name, command in panes.items():
            result = run_pane(command, 80, 40)
            if result.returncode or not result.stdout.strip():
                raise RuntimeError(f"The {name} window has no content: {result.stderr.strip() or command}")
        with (root / "session.log").open("w+") as log:
            terminals = {}
            compositor = subprocess.Popen(["Hyprland", "--config", str(config)], env=env,
                                          stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                wait_for(lambda: list((runtime / "hypr").glob("*/.socket.sock")))
                env["HYPRLAND_INSTANCE_SIGNATURE"] = next((runtime / "hypr").glob("*/.socket.sock")).parent.name
                wait_for(lambda: any(path.is_socket() for path in runtime.glob("wayland-*")))
                env["WAYLAND_DISPLAY"] = str(next(path for path in runtime.glob("wayland-*") if path.is_socket()))

                def ctl(*args):
                    return subprocess.check_output(["hyprctl", *args], env=env, text=True, timeout=5).strip()

                def windows():
                    return {window["title"]: window for window in json.loads(ctl("clients", "-j"))}

                # Only resize this script's temporary window in the parent desktop.
                def preview_window():
                    clients = json.loads(subprocess.check_output(["hyprctl", "clients", "-j"], text=True, timeout=5))
                    return next((window for window in clients if window["pid"] == compositor.pid), None)
                wait_for(preview_window, timeout=60)
                window = preview_window()
                code = 'hl.dispatch(hl.dsp.focus({window="address:' + window["address"] + '"}))'
                if not window["floating"]:
                    code += '; hl.dispatch(hl.dsp.window.float({action="toggle"}))'
                code += f'; hl.dispatch(hl.dsp.window.resize({{x={SIZE[0]},y={SIZE[1]}}}))'
                subprocess.run(["hyprctl", "eval", code], check=True, stdout=subprocess.DEVNULL, timeout=5)
                wait_for(lambda: any((m["width"], m["height"]) == SIZE for m in json.loads(ctl("monitors", "-j"))))
                wait_for(lambda: ctl("eval", 'assert(type(test_bindings["SUPER + ALT + P"]) == "function")') == "ok")
                # Hide the expected direct-launch notice before the first frame.
                wait_for(lambda: ctl("dismissnotify", "-1") == "ok")
                still = None
                with Recorder(env, folder) as recorder:
                    for step in STEPS:
                        if recorder.errors:
                            break
                        kind = step[0]
                        if kind == "caption":
                            recorder.mark(("text", step[1]))
                        elif kind == "wait":
                            time.sleep(step[1])
                        elif kind == "open":
                            terminals[step[1]] = subprocess.Popen(
                                ["foot", f"--config={foot}", f"--title={step[1]}", "/usr/bin/python3",
                                 str(Path(__file__).resolve()), "--window", panes[step[1]]],
                                env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                            wait_for(lambda: step[1] in windows())
                        elif kind == "press":
                            _, combo, label, pause = step
                            recorder.mark(("keys", combo, label))
                            assert ctl("eval", f'test_bindings["{combo}"]()') == "ok", combo
                            time.sleep(pause)
                        elif kind == "check":
                            assert step[2](windows()), f"Expected {step[1]}: {windows()}"
                        elif kind == "still":
                            still = recorder.now()
                assert not ctl("configerrors"), ctl("configerrors")
                return recorder, still
            except BaseException:
                log.seek(0)
                print(log.read()[-4000:])
                raise
            finally:
                for terminal in terminals.values():
                    stop(terminal)
                stop(compositor)


def caption_layer(caption):
    """A rounded caption with keycaps, centered near the bottom of the frame."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    regular = ImageFont.truetype(str(FONTS / "JetBrainsMonoNerdFont-Regular.ttf"), 28)
    bold = ImageFont.truetype(str(FONTS / "JetBrainsMonoNerdFont-Bold.ttf"), 28)
    if caption[0] == "keys":
        arrows = {"LEFT": "←", "RIGHT": "→", "UP": "↑", "DOWN": "↓"}
        parts = []
        for name in caption[1].split(" + "):
            parts += [("plus", "+")] if parts else []
            parts.append(("key", arrows.get(name, name.title() if len(name) > 1 else name)))
        parts.append(("label", caption[2]))
    else:
        parts = [("title" if caption[1] == TITLE else "label", caption[1])]
    layer = Image.new("RGBA", SIZE)
    draw = ImageDraw.Draw(layer)
    widths = [draw.textlength(text, font=bold if kind in ("key", "title") else regular) + (30 if kind == "key" else 0)
              for kind, text in parts]
    width, height = sum(widths) + 12 * (len(parts) - 1) + 56, 72
    x, y = (SIZE[0] - width) / 2, SIZE[1] - height - 50
    shadow = Image.new("RGBA", SIZE)
    ImageDraw.Draw(shadow).rounded_rectangle([x, y + 8, x + width, y + height + 8], 36, fill=(0, 0, 0, 150))
    layer.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)))
    draw.rounded_rectangle([x, y, x + width, y + height], 36, fill=(22, 22, 34, 238), outline=BLUE, width=2)
    x, middle = x + 28, y + height / 2
    for (kind, text), part in zip(parts, widths):
        if kind == "key":
            draw.rounded_rectangle([x, middle - 22, x + part, middle + 22], 9, fill=BLUE, outline=PURPLE)
            draw.text((x + part / 2, middle), text, font=bold, fill=(22, 22, 34), anchor="mm")
        else:
            color = {"plus": (86, 95, 137), "title": (192, 202, 245)}.get(kind, (169, 177, 214))
            draw.text((x, middle), text, font=bold if kind == "title" else regular, fill=color, anchor="lm")
        x += part + 12
    return layer


def compose(recorder, still):
    """Write preview.gif and preview.png from the recorded frames."""
    from PIL import Image, ImageChops
    wallpaper = Image.open(WALLPAPER).convert("RGB")
    scale = max(SIZE[0] / wallpaper.width, SIZE[1] / wallpaper.height)
    wallpaper = wallpaper.resize((round(wallpaper.width * scale), round(wallpaper.height * scale)), Image.LANCZOS)
    wallpaper = wallpaper.crop(((wallpaper.width - SIZE[0]) // 2, (wallpaper.height - SIZE[1]) // 2,
                                (wallpaper.width + SIZE[0]) // 2, (wallpaper.height + SIZE[1]) // 2))
    key = Image.new("RGB", SIZE, KEY)
    captions = {caption: caption_layer(caption) for _, caption in recorder.marks}

    def desktop(path):
        shot = Image.open(path).convert("RGB")
        mask = ImageChops.difference(shot, key).convert("L").point(lambda v: 255 if v < 4 else 0)
        # Before the first window opens, only the hidden pointer's position differs. Show the wallpaper.
        if mask.histogram()[255] > SIZE[0] * SIZE[1] * .98:
            return wallpaper.copy()
        return Image.composite(wallpaper, shot, mask)

    def caption_at(t):
        return next((caption for at, caption in reversed(recorder.marks) if at <= t), recorder.marks[0][1])

    # Drop idle stretches over 0.9 s so the loop keeps moving. Hold the final layout longer.
    kept, previous, changed_at = [], None, 0
    for path, t in recorder.frames:
        small = Image.open(path).reduce(8)
        if previous is None or ImageChops.difference(small, previous).getbbox():
            changed_at = t
        previous = small
        hold = 2.5 if t >= recorder.marks[-1][0] else .9
        if t - changed_at < hold:
            kept.append((path, t))
    with tempfile.TemporaryDirectory(prefix="eqp-out-", dir="/tmp") as temporary:
        out, clock, index = Path(temporary), 0, 0
        for i, (path, t) in enumerate(kept):
            step = t - kept[i - 1][1] if i and t - kept[i - 1][1] < .5 else 1 / FPS
            clock += step
            while index / FPS <= clock:
                frame = desktop(path).convert("RGBA")
                frame.alpha_composite(captions[caption_at(t)])
                frame.convert("RGB").resize((1000, 500), Image.LANCZOS).save(out / f"{index:05d}.png", compress_level=1)
                index += 1
        palette = out / "palette.png"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", str(FPS), "-i", str(out / "%05d.png"),
                        "-vf", "fps=12,palettegen=max_colors=128:stats_mode=diff", str(palette)], check=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", str(FPS), "-i", str(out / "%05d.png"),
                        "-i", str(palette), "-lavfi", "fps=12[v];[v][1:v]paletteuse=dither=none:diff_mode=rectangle",
                        str(ROOT / "preview.gif")], check=True)
    last = max((path for path, t in recorder.frames if t <= still), key=lambda path: path.name)
    desktop(last).save(ROOT / "preview.png", optimize=True)


def main():
    if sys.argv[1:2] == ["--show"]:
        return show(*sys.argv[2:4])
    if sys.argv[1:2] == ["--window"]:
        return window(sys.argv[2])
    missing = [tool for tool in TOOLS if not shutil.which(tool)]
    missing += [str(path) for path in (WALLPAPER, Path("/usr/share/omarchy/icon.txt"),
                                        FONTS / "JetBrainsMonoNerdFont-Regular.ttf") if not path.exists()]
    if missing:
        sys.exit("Missing: " + ", ".join(missing))
    with tempfile.TemporaryDirectory(prefix="eqp-frames-", dir="/tmp") as temporary:
        recorder, still = record(Path(temporary))
        compose(recorder, still)
    print("Wrote preview.gif and preview.png from real key presses in the disposable desktop.")


if __name__ == "__main__":
    main()
