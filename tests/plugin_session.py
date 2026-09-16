#!/usr/bin/env python3
"""Run the real Omarchy plugin commands against a disposable desktop and shell."""
import json
import hashlib
import fcntl
import importlib.util
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ID = 'ralphsmith80.equal-tiling'


def wait_for(check, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
        time.sleep(.2)
    raise TimeoutError('Condition did not become true')


def stop(process):
    if process and process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def run():
    parent_display = Path(os.environ['XDG_RUNTIME_DIR']) / os.environ['WAYLAND_DISPLAY']
    with tempfile.TemporaryDirectory(prefix='op-', dir='/tmp') as temporary:
        root = Path(temporary)
        home, runtime = root / 'home', root / 'rt'
        runtime.mkdir(mode=0o700)
        config = home / '.config/hypr/hyprland.lua'
        config.parent.mkdir(parents=True)
        original = '''dofile("/usr/share/omarchy/default/hypr/bootstrap.lua")
hl.monitor({output="", mode="preferred", position="0x0", scale=1})
hl.config({input={follow_mouse=0}, animations={enabled=false}})
test_bindings = {}
o = {bind=function(key, description, action, opts) test_bindings[key]=action; hl.bind(key, action, opts or {}) end}
'''
        config.write_text(original)
        shell_config = home / '.config/omarchy/shell.json'
        shell_config.parent.mkdir(parents=True)
        disabled = [json.loads(path.read_text())['id'] for path in Path('/usr/share/omarchy/shell/plugins').rglob('manifest.json')]
        shell_config.write_text(json.dumps({'version':1,'disabledPlugins':disabled,
            'plugins':[], 'bar':{'id':'omarchy.bar','layout':{'left':[],'center':[],'right':[]}}}))
        source = root / 'source'
        source.mkdir()
        files = subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
        for name in set(files):
            target = source / name
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,target)
        def git(*args):
            return subprocess.check_output(['git','-c','user.name=Test','-c','user.email=test@example.invalid',*args],cwd=source,text=True)
        git('init','-b','main'); git('add','.'); git('commit','-qm','Test plugin')
        # Reuse the verified native build; the service still validates its inputs.
        spec = importlib.util.spec_from_file_location('install', ROOT/'install.py')
        installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)
        key = hashlib.sha256(json.dumps(installer.build_signature(),sort_keys=True).encode()).hexdigest()[:20]
        cached = home / '.cache/omarchy-equal-tiling' / key
        if not os.environ.get('EQUAL_TILING_TEST_FRESH'):
            shutil.copytree(ROOT/'.build',cached)
        env = dict(os.environ,HOME=str(home),XDG_CONFIG_HOME=str(home/'.config'),
            XDG_STATE_HOME=str(home/'.local/state'),XDG_CACHE_HOME=str(home/'.cache'),
            XDG_RUNTIME_DIR=str(runtime),WAYLAND_DISPLAY=str(parent_display),
            OMARCHY_PATH='/usr/share/omarchy',AQ_DRM_DEVICES='/dev/null')
        env.pop('HYPRLAND_INSTANCE_SIGNATURE',None); env.pop('DISPLAY',None)
        compositor = shell = None
        def command(*args):
            result = subprocess.run(args,env=env,capture_output=True,text=True,timeout=20)
            if result.returncode:
                raise RuntimeError(f'{args}: {result.stdout}\n{result.stderr}')
            return result.stdout.strip()
        def ctl(*args):return command('hyprctl',*args)
        def ev(code):
            result=ctl('eval',code)
            assert result=='ok',result
            time.sleep(.2)
        def loaded():return any(p['name']=='hy3' for p in json.loads(ctl('plugin','list','-j')))
        def omarchy(*args):return command('omarchy','plugin',*args)
        with (root/'hyprland.log').open('w') as hyprlog, (root/'shell.log').open('w') as shelllog:
            try:
                compositor=subprocess.Popen(['Hyprland','--config',str(config)],env=env,stdout=hyprlog,stderr=subprocess.STDOUT,start_new_session=True)
                wait_for(lambda:list((runtime/'hypr').glob('*/.socket.sock')))
                env['HYPRLAND_INSTANCE_SIGNATURE']=next((runtime/'hypr').glob('*/.socket.sock')).parent.name
                wait_for(lambda:list(runtime.glob('wayland-*')))
                env['WAYLAND_DISPLAY']=str(next(p for p in runtime.glob('wayland-*') if p.is_socket()))
                shell=subprocess.Popen(['dbus-run-session','--','qs','-p','/usr/share/omarchy/shell'],env=env,stdout=shelllog,stderr=subprocess.STDOUT,start_new_session=True)
                def shell_ready():
                    try:return command('omarchy-shell','shell','ping')=='ok'
                    except RuntimeError:return False
                wait_for(shell_ready)
                omarchy('add',str(source),'--enable','--yes')
                if os.environ.get('EQUAL_TILING_TEST_FRESH'):
                    wait_for(lambda: list(cached.glob('compile-*')))
                    omarchy('disable',PLUGIN_ID)
                    def build_stopped():
                        with (cached/'.build.lock').open('w') as lock:
                            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                            except BlockingIOError:return False
                            return True
                    wait_for(build_stopped)
                    omarchy('enable',PLUGIN_ID)
                wait_for(loaded,180)
                assert config.read_text()==original
                assert not (config.parent/'equal-tiling.lua').exists()
                assert not ctl('configerrors'),ctl('configerrors')
                print('PASS: real plugin add/enable loads native hy3 without editing Hyprland files',flush=True)
                for label in 'ABC':
                    ev(f'hl.exec_cmd("foot --config=/dev/null --title={label} sleep 300")')
                    wait_for(lambda: any(w['title']==label for w in json.loads(ctl('clients','-j'))))
                ev('test_bindings["SUPER + SHIFT + DOWN"]()')
                assert len(json.loads(ctl('clients','-j')))==3
                for _ in range(2):
                    assert ctl('reload')=='ok'
                    def bindings_ready():
                        try:return ctl('eval','assert(test_bindings["SUPER + SHIFT + RIGHT"])')=='ok'
                        except RuntimeError:return False
                    wait_for(bindings_ready)
                    ev('test_bindings["SUPER + SHIFT + RIGHT"]()')
                    assert not ctl('configerrors'),ctl('configerrors')
                print('PASS: compositor reload reapplies the layout and movement bindings',flush=True)
                omarchy('disable',PLUGIN_ID)
                wait_for(lambda:not loaded())
                assert config.read_text()==original
                omarchy('enable',PLUGIN_ID)
                wait_for(loaded)
                print('PASS: disable restores the saved config; re-enable loads it again',flush=True)
                for _ in range(3):
                    omarchy('disable',PLUGIN_ID)
                    omarchy('enable',PLUGIN_ID)
                    time.sleep(2)
                    wait_for(loaded)
                print('PASS: rapid disable/re-enable keeps the layout active',flush=True)
                omarchy('disable',PLUGIN_ID)
                wait_for(lambda:not loaded())
                ctl('plugin','load',str(cached/'libhy3-cosmic.so'))
                owner=json.loads(ctl('plugin','list','-j'))[0]['handle']
                omarchy('enable',PLUGIN_ID)
                log=home/'.local/state/omarchy-equal-tiling/service.log'
                wait_for(lambda:'Another hy3 setup is already loaded' in log.read_text())
                assert json.loads(ctl('plugin','list','-j'))[0]['handle']==owner
                omarchy('disable',PLUGIN_ID)
                ctl('plugin','unload',str(cached/'libhy3-cosmic.so'))
                omarchy('enable',PLUGIN_ID)
                wait_for(loaded)
                print('PASS: existing hy3 ownership is preserved on conflict',flush=True)
                module=source/'config/hypr/equal-tiling.lua'
                module.write_text(module.read_text().replace('return true\n','equal_tiling_test_revision = "updated"\nreturn true\n'))
                git('add','.');git('commit','-qm','Test update')
                omarchy('update',PLUGIN_ID,'--yes')
                def updated():
                    try:return ctl('eval','assert(equal_tiling_test_revision == "updated")')=='ok'
                    except RuntimeError:return False
                wait_for(updated)
                print('PASS: real plugin update activates the changed Lua module',flush=True)
                stop(shell)
                shell=subprocess.Popen(['dbus-run-session','--','qs','-p','/usr/share/omarchy/shell'],env=env,stdout=shelllog,stderr=subprocess.STDOUT,start_new_session=True)
                wait_for(shell_ready)
                assert loaded()
                omarchy('remove',PLUGIN_ID,'--yes')
                wait_for(lambda:not loaded())
                assert not (home/'.config/omarchy/plugins'/PLUGIN_ID).exists()
                assert config.read_text()==original
                assert not ctl('configerrors'),ctl('configerrors')
                print('PASS: shell restart and removal leave no active plugin or config edits',flush=True)
            except BaseException:
                for log in [root/'hyprland.log',root/'shell.log',home/'.local/state/omarchy-equal-tiling/service.log']:
                    if log.exists():print(f'\n{log.name}:\n{log.read_text()[-6000:]}',flush=True)
                raise
            finally:
                try:
                    cfg=json.loads(shell_config.read_text());cfg['plugins']=[];shell_config.write_text(json.dumps(cfg))
                except (OSError,ValueError):pass
                time.sleep(1.2)
                stop(shell);stop(compositor)


if __name__=='__main__':
    run()
