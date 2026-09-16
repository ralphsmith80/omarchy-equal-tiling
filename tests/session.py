#!/usr/bin/env python3
"""Exercise the installed package in a disposable nested Hyprland session."""
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def run():
    parent_display = Path(os.environ['XDG_RUNTIME_DIR']) / os.environ['WAYLAND_DISPLAY']
    with tempfile.TemporaryDirectory(prefix='eq-', dir='/tmp') as temporary:
        root = Path(temporary)
        home, runtime = root / 'home', root / 'rt'
        state_home = root / 'custom-state'
        config = home / '.config/hypr/hyprland.lua'
        config.parent.mkdir(parents=True)
        runtime.mkdir(mode=0o700)
        original = '''dofile("/usr/share/omarchy/default/hypr/bootstrap.lua")
hl.monitor({output = "", mode = "preferred", position = "0x0", scale = 1})
hl.config({general = {gaps_in = 5, gaps_out = 10}, input = {follow_mouse = 0}, animations = {enabled = false}, misc = {disable_hyprland_logo = true, disable_splash_rendering = true}})
test_bindings = {}
o = {bind = function(key, description, action, opts) test_bindings[key] = action; hl.bind(key, action, opts or {}) end}
'''
        config.write_text(original)
        env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / '.config'),
                   XDG_STATE_HOME=str(state_home), XDG_CACHE_HOME=str(home / '.cache'),
                   XDG_RUNTIME_DIR=str(runtime), WAYLAND_DISPLAY=str(parent_display),
                   AQ_DRM_DEVICES='/dev/null')
        env.pop('HYPRLAND_INSTANCE_SIGNATURE', None)
        env.pop('DISPLAY', None)
        def install(*args):
            return subprocess.check_output(['python3', str(ROOT / 'install.py'), '--home', str(home), *args], env=env, text=True)
        preview = install()
        assert config.read_text() == original and 'Preview only' in preview
        install('--apply')
        assert '0 changes' in install('--apply')
        backup, = (home / '.local/state/omarchy-equal-tiling').glob('restore-*')
        with (root / 'session.log').open('w') as log:
            compositor = subprocess.Popen(['Hyprland', '--config', str(config)], env=env,
                                          stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    sockets = list((runtime / 'hypr').glob('*/.socket.sock'))
                    if sockets:
                        env['HYPRLAND_INSTANCE_SIGNATURE'] = sockets[0].parent.name
                        break
                    if compositor.poll() is not None:
                        raise RuntimeError((root / 'session.log').read_text())
                    time.sleep(.1)
                else:
                    raise TimeoutError('Nested compositor did not start')
                def ctl(*args):
                    result = subprocess.run(['hyprctl', *args], env=env, text=True, capture_output=True)
                    assert result.returncode == 0, (args, result.stdout, result.stderr)
                    return result.stdout.strip()
                def ev(code):
                    result = ctl('eval', code)
                    assert result == 'ok', result
                    time.sleep(.2)
                def windows():
                    return {w['title']: w for w in json.loads(ctl('clients', '-j'))}
                def focus(label):
                    address = windows()[label]['address']
                    ev('hl.dispatch(hl.dsp.focus({window="address:' + address + '"}))')
                def press(direction):
                    ev('test_bindings["SUPER + SHIFT + ' + direction + '"]()')
                def snapshot():
                    return {k: (w['at'], w['size']) for k, w in windows().items()}
                def open_window(label):
                    ev(f'hl.exec_cmd("foot --config=/dev/null --title={label} sleep 300")')
                    deadline = time.monotonic() + 5
                    while label not in windows():
                        if time.monotonic() >= deadline:
                            raise TimeoutError(f'Window {label} did not open')
                        time.sleep(.1)
                    focus(label)
                time.sleep(1)
                assert not ctl('configerrors'), ctl('configerrors')
                assert 'hy3' in ctl('plugin', 'list'), ctl('plugin', 'list')
                for label in 'AB':
                    open_window(label)
                ev('hl.dispatch(hl.plugin.hy3.change_group("h"))')
                ev('hl.dispatch(hl.plugin.hy3.make_group("v", {ephemeral=true}))')
                open_window('C')
                ev('hl.dispatch(hl.plugin.hy3.make_group("h", {ephemeral=true}))')
                open_window('D')
                press('RIGHT'); press('RIGHT')
                before = snapshot(); press('RIGHT')
                assert snapshot() == before, ('Workspace edge changed the layout', before, snapshot())
                press('LEFT'); press('LEFT')
                ws = windows()
                column = [ws[label] for label in 'BCD']
                assert len({w['at'][0] for w in column}) == 1, ws
                assert max(w['size'][1] for w in column) - min(w['size'][1] for w in column) <= 2, ws
                assert all(abs(w['size'][0] - ws['A']['size'][0]) <= 2 for w in column), ws
                print('PASS: directional grouping, equal siblings, and workspace edge', flush=True)
                random.seed(80)
                for _ in range(40):
                    label = random.choice('ABCD')
                    focus(label); press(random.choice(['LEFT', 'RIGHT', 'UP', 'DOWN']))
                    ws = windows()
                    assert set(ws) == set('ABCD'), ws
                    assert json.loads(ctl('activewindow', '-j'))['title'] == label
                    for w in ws.values():
                        assert min(w['size']) > 10, w
                        for other in ws.values():
                            if other['address'] == w['address']:
                                continue
                            overlap = [min(w['at'][axis] + w['size'][axis], other['at'][axis] + other['size'][axis])
                                       - max(w['at'][axis], other['at'][axis]) for axis in (0, 1)]
                            assert min(overlap) <= 0, (w, other)
                print('PASS: 40 moves preserve focus, all tiles, and non-overlapping geometry', flush=True)
                ev('test_bindings["SUPER + T"]()')
                assert json.loads(ctl('activewindow', '-j'))['floating']
                ev('test_bindings["SUPER + T"]()')
                assert not json.loads(ctl('activewindow', '-j'))['floating']
                ev('hl.dispatch(hl.dsp.focus({workspace="2"}))')
                for label in 'EFG':
                    open_window(label)
                ev('hl.dispatch(hl.plugin.hy3.change_group("h"))')
                focus('E')
                ev('hl.dispatch(hl.dsp.window.resize({x=150, y=0, relative=true}))')
                assert abs(windows()['E']['size'][0] - windows()['F']['size'][0]) > 20
                focus('G')
                ev('test_bindings["SUPER + T"]()')
                assert windows()['G']['floating']
                assert abs(windows()['E']['size'][0] - windows()['F']['size'][0]) <= 2
                print('PASS: floating a resized sibling equalizes the remaining tiles', flush=True)
                ev('test_bindings["SUPER + L"]()')
                legacy = home / '.local/state/omarchy/workspace-layouts/2.lua'
                legacy.parent.mkdir(parents=True)
                legacy.write_text('hl.workspace_rule({workspace="2", layout="dwindle"})\n')
                for _ in range(2):
                    assert ctl('reload') == 'ok'
                    time.sleep(.5)
                    ev('require("default.hypr.workspace-layouts")')
                    ev('assert(hl.get_active_workspace().tiled_layout == "scrolling")')
                print('PASS: custom state directory wins over stale defaults across reloads', flush=True)
                ev('test_bindings["SUPER + L"]()')
                saved = list((state_home / 'omarchy/workspace-layouts').glob('*.lua'))
                assert len(saved) == 1 and 'hl.plugin.hy3' in saved[0].read_text()
                assert ctl('reload') == 'ok'
                time.sleep(.5)
                assert not ctl('configerrors'), ctl('configerrors')
                focus('A'); press('RIGHT')
                print('PASS: floating, saved layout toggle, reload, and movement after reload', flush=True)
                stamp = home / '.local/lib/omarchy-equal-tiling/hyprland-commit'
                commit = stamp.read_text()
                stamp.write_text('0000000000000000000000000000000000000000\n')
                assert ctl('reload') == 'ok'
                time.sleep(.5)
                assert not ctl('configerrors'), ctl('configerrors')
                assert 'hy3' not in ctl('plugin', 'list')
                ev('require("default.hypr.workspace-layouts")')
                ev('hl.dispatch(hl.dsp.focus({workspace="2"}))')
                ev('assert(hl.get_active_workspace().tiled_layout == "dwindle")')
                stamp.write_text(commit)
                assert ctl('reload') == 'ok'
                time.sleep(.5)
                assert not ctl('configerrors'), ctl('configerrors')
                assert 'hy3' in ctl('plugin', 'list')
                print('PASS: mismatched build is skipped and matching build loads again', flush=True)
            finally:
                if compositor.poll() is None:
                    os.killpg(compositor.pid, signal.SIGTERM)
                    try:
                        compositor.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(compositor.pid, signal.SIGKILL)
                        compositor.wait()
        install('--rollback', str(backup), '--apply')
        assert config.read_text() == original
        assert not (home / '.config/hypr/equal-tiling.lua').exists()
        assert not (home / '.local/lib/omarchy-equal-tiling/libhy3-cosmic.so').exists()
        print('PASS: real install, repeated apply, and rollback in a temporary home', flush=True)


if __name__ == '__main__':
    run()
