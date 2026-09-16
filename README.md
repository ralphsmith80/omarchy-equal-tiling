# COSMIC-style equal tiling for Omarchy

An Omarchy service plugin that aims to replicate the equal tiling and directional
window movement of the [COSMIC desktop from Pop!_OS](https://system76.com/cosmic).
It builds a patched [hy3](https://github.com/outfoxxed/hy3) and applies the layout
while the plugin is enabled. It does not edit your Hyprland configuration files.

This is an independent implementation. It is not affiliated with or endorsed by
System76, and it does not reproduce every COSMIC desktop feature.

Press Super+Shift+an arrow to move the focused window through the layout tree.
Moving across a split creates a group, enters a neighboring group, or steps out
of the current group. At the workspace edge, movement stops. Windows in each
group share its space equally.

For example, with `A | D | (B / C)`, focus D and press Right twice. The result is
`A | (B / D / C)`. B, D, and C share the right half equally.

## Requirements

Tested with Hyprland **0.56.2** and Omarchy's Lua configuration and Quickshell
plugin system. Older `.conf` setups are unsupported. Other Hyprland releases
need a compatible hy3 revision and a fresh build. Keep Omarchy's standard
`~/.config` location.

The build needs Python 3.9+, curl, tar, patch, CMake, Ninja, pkg-config, a C++23
compiler, and development files for Hyprland, pixman, libdrm, Pango, libinput,
Wayland, and xkbcommon. The plugin does not install system packages or use sudo.
The first build requires internet access to download pinned hy3 source.

Do not load another copy of hy3 alongside this plugin. If you installed version
0.1.0 with `install.py`, use its printed rollback command first. A custom
`hypr.dotfiles` loader that supplies equal tiling must also stop loading hy3
before this plugin can take over. The service reports a conflict and leaves an
existing hy3 instance alone.

## Install

```bash
omarchy plugin add https://github.com/ralphsmith80/omarchy-equal-tiling --enable --yes
```

The first enable builds hy3 in the background. Once ready, the service loads it
and applies the shortcuts below. Allow a few minutes for compilation. Check:

```bash
hyprctl plugin list
hyprctl configerrors
```

The plugin list should show `hy3`, with no configuration errors. The underlying
layout and Lua namespace retain the upstream name.

Build and service messages go to
`${XDG_STATE_HOME:-$HOME/.local/state}/omarchy-equal-tiling/service.log`.
If the build fails, resolve the reported dependency or version problem, then
disable and enable the plugin to retry.

## Shortcuts

| Shortcut | Action |
| --- | --- |
| Super+arrows | Focus a window through hy3's layout tree |
| Super+Shift+arrows | Move a window through tiling groups |
| Super+T | Float or retile the window, then balance the group |
| Super+L | Switch the workspace between equal tiling and scrolling |

These replace Omarchy's directional focus, directional swap, floating, and
workspace layout shortcuts while enabled. Super+J, Omarchy's split toggle, is
disabled because Super+Shift+arrows controls the arrangement. Other shortcuts
remain available. Movement does not move windows across monitors. This plugin
does not reproduce COSMIC's tab behavior.

Super+L saves the workspace's layout choice in Omarchy's workspace state. Saved
hy3 choices fall back to dwindle while hy3 is unavailable.

## Updates and removal

```bash
omarchy plugin update ralphsmith80.equal-tiling --yes
omarchy plugin disable ralphsmith80.equal-tiling
omarchy plugin enable ralphsmith80.equal-tiling
omarchy plugin remove ralphsmith80.equal-tiling --yes
```

Update applies the new service code. Disable and removal unload the native
plugin and reload your saved Hyprland configuration. Cleanup can take a few
seconds. They also stop an unfinished build. Restarting the Omarchy shell keeps
the service active; ending the Hyprland session stops it.

After updating Hyprland, log out and back in. The service rebuilds against the
installed headers when needed. It refuses to load a build that does not match
the running compositor.

Builds remain under `${XDG_CACHE_HOME:-$HOME/.cache}/omarchy-equal-tiling` for reuse.
Removal keeps that cache, the service log, and your saved workspace choices. You
can delete the cache and log directory after removing the plugin.

## What runs on your computer

Omarchy loads `Service.qml`, which starts a Python worker. The worker uses
Hyprland IPC to load the native library, apply Lua bindings, and restore the
saved configuration on disable. It follows Omarchy's enabled service state and
allows one worker per Hyprland session.

The builder verifies the pinned source archive's SHA-256 before unpacking and
compiling it. Native plugins execute inside Hyprland. The code makes no telemetry
or upload requests. Review the source before enabling it, as with other
unsandboxed Omarchy plugins.

## Standalone installer

The older standalone install remains available for users who do not want the
Omarchy service. Use only one installation method.

```bash
git clone https://github.com/ralphsmith80/omarchy-equal-tiling.git
cd omarchy-equal-tiling
python3 install.py --build
python3 install.py          # Preview changes
python3 install.py --apply  # Back up and install
```

This method installs `~/.config/hypr/equal-tiling.lua`, the library and build stamp
under `~/.local/lib/omarchy-equal-tiling`, and a loader in `hyprland.lua`. Each apply
prints an exact rollback command. Backups live under
`~/.local/state/omarchy-equal-tiling/restore-*`. Undo multiple applies in reverse
order. Rollback refuses to overwrite later local edits. Reconcile those edits
before retrying. Rebuild and apply after Hyprland updates.

## Development

```bash
omarchy plugin validate .
python3 -m unittest discover -s tests -v
python3 install.py --build
python3 tests/session.py
python3 tests/plugin_session.py
EQUAL_TILING_TEST_FRESH=1 python3 tests/plugin_session.py
```

The session tests need an active Wayland desktop and `foot`. They use temporary
homes and separate nested Hyprland sessions. The plugin test also starts a private
Omarchy shell and runs the real add, enable, disable, update, and remove commands.
The fresh-build mode interrupts the first build, then verifies that enabling
again compiles and activates the plugin. See [VALIDATION.md](VALIDATION.md).

`hy3.patch` applies to upstream commit
`42b7ed8fd9aefd3f36e5f617afd5071245c67853`. The expected archive SHA-256 is
`b4b8842cdfb0562f1f4228ef35c746f040379a33ee0912ad089f693206c34076`.
The patch adds `hl.plugin.hy3.move_cosmic(direction)` and leaves upstream movement
and focus dispatchers intact. Update the source pin and checksum together, then
build and run the checks before publishing a release.

## License and credit

GPL-3.0, see [LICENSE](LICENSE). hy3 is by outfoxxed and its contributors.
Ralph Smith's package adds the directional movement patch, Omarchy configuration,
service, and installer. Omarchy-derived configuration retains its MIT notice in
[LICENSE.omarchy](LICENSE.omarchy).
