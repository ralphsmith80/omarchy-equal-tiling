"""Exercise Omarchy's window controls inside session.py's isolated compositor."""
import json
import os


def check_controls(ctl, ev, windows, focus, open_window):
    def key(shortcut):
        ev('local action = test_bindings[' + json.dumps(shortcut) + ']; '
           'if type(action) == "function" then action() else hl.dispatch(action) end')

    def workspace(number):
        ev(f'hl.dispatch(hl.dsp.focus({{workspace="{number}"}}))')

    def visible(label):
        window = windows()[label]
        assert window['visible'] and min(window['size']) > 100, window
        return window

    def close(label):
        focus(label)
        ev('hl.dispatch(hl.dsp.window.kill())')

    # Allow one focused reproduction without first failing on another control.
    case = os.environ.get('EQUAL_TILING_CONTROL_CASE', 'all')
    if case in ('all', 'aspect'):
        workspace(40)
        open_window('Aspect')
        full = visible('Aspect')
        ev('hl.config({layout={single_window_aspect_ratio={1,1}}})')
        square = visible('Aspect')
        assert abs(square['size'][0] - square['size'][1]) <= 2, (full, square)
        assert square['size'] != full['size'], (full, square)
        for axis in (0, 1):
            assert abs(square['at'][axis] - full['at'][axis] - (full['size'][axis] - square['size'][axis]) / 2) <= 2
        ev('hl.config({layout={single_window_aspect_ratio={4,3}}})')
        rectangle = visible('Aspect')
        assert abs(rectangle['size'][0] / rectangle['size'][1] - 4 / 3) < .02, rectangle
        ev('hl.config({layout={single_window_aspect_ratio={1,1},single_window_aspect_ratio_tolerance=.5}})')
        assert visible('Aspect')['size'] == full['size']
        ev('hl.config({layout={single_window_aspect_ratio_tolerance=.1}})')
        key('SUPER + F')
        fullscreen = visible('Aspect')
        assert fullscreen['fullscreen'] != 0 and fullscreen['size'][0] >= full['size'][0], fullscreen
        key('SUPER + F')
        assert visible('Aspect')['size'] == square['size']
        open_window('Aspect2')
        two = visible('Aspect2')
        assert abs(two['size'][0] - visible('Aspect')['size'][0]) <= 2
        assert min(two['at'][0], visible('Aspect')['at'][0]) == full['at'][0]
        close('Aspect2')
        assert visible('Aspect')['size'] == square['size']
        ev('hl.config({layout={single_window_aspect_ratio={0,0}}})')
        assert visible('Aspect')['size'] == full['size']
        key('SUPER + P')
        assert visible('Aspect')['size'] != full['size']
        key('SUPER + P')
        assert visible('Aspect')['size'] == full['size']
        print('PASS: single-window ratios, tolerance, fullscreen, second window, and pseudotile', flush=True)

    if case in ('all', 'split'):
        workspace(41)
        for label in ('SplitA', 'SplitB'):
            open_window(label)
        assert any(b['modmask'] == 64 and b['key'].lower() == 'j' for b in json.loads(ctl('binds', '-j'))), 'Super+J is missing'
        before = {label: (windows()[label]['at'], windows()[label]['size']) for label in ('SplitA', 'SplitB')}
        key('SUPER + J')
        for axis in (0, 1):
            was_aligned = before['SplitA'][0][axis] == before['SplitB'][0][axis]
            now_aligned = windows()['SplitA']['at'][axis] == windows()['SplitB']['at'][axis]
            assert was_aligned != now_aligned, windows()
        key('SUPER + J')
        assert {label: (windows()[label]['at'], windows()[label]['size']) for label in before} == before
        print('PASS: Omarchy Super+J remains bound and toggles the split both ways', flush=True)

    if case in ('all', 'group'):
        workspace(42)
        open_window('GroupA')
        before = visible('GroupA')
        key('SUPER + G')
        grouped = visible('GroupA')
        assert grouped['grouped'], grouped
        assert grouped['size'][0] == before['size'][0], (before, grouped)
        open_window('GroupB')
        assert len(visible('GroupB')['grouped']) == 2, windows()
        assert not windows()['GroupA']['visible'], windows()
        key('SUPER + ALT + TAB')
        assert json.loads(ctl('activewindow', '-j'))['title'] == 'GroupA'
        visible('GroupA')
        assert not windows()['GroupB']['visible'], windows()
        key('SUPER + CTRL + RIGHT')
        assert json.loads(ctl('activewindow', '-j'))['title'] == 'GroupB'
        key('SUPER + ALT + code:10')
        assert json.loads(ctl('activewindow', '-j'))['title'] == 'GroupA'
        key('SUPER + ALT + G')
        assert not visible('GroupA')['grouped'], windows()
        assert visible('GroupB')['grouped'], windows()
        a, b = windows()['GroupA']['at'], windows()['GroupB']['at']
        if a[0] != b[0]:
            direction = 'LEFT' if b[0] < a[0] else 'RIGHT'
        else:
            direction = 'UP' if b[1] < a[1] else 'DOWN'
        key('SUPER + ALT + ' + direction)
        assert len(visible('GroupA')['grouped']) == 2, windows()
        key('SUPER + G')
        for label in ('GroupA', 'GroupB'):
            assert not visible(label)['grouped'], windows()
        assert windows()['GroupA']['at'] != windows()['GroupB']['at'], windows()
        print('PASS: create group, add window, cycle/index tabs, extract, rejoin, and dissolve', flush=True)

    for label in list(windows()):
        close(label)
    workspace(1)
