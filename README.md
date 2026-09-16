# Equal tiling for Omarchy

Equal-sized window groups and directional movement for Omarchy's Lua-based
Hyprland setup. This package builds a patched [hy3](https://github.com/outfoxxed/hy3)
and installs the Lua configuration that controls it.

The goal is to replicate the equal tiling and directional window movement of
the [COSMIC desktop from Pop!_OS](https://system76.com/cosmic) in Omarchy.
This is an independent implementation using hy3. It is not affiliated with or
endorsed by System76, and it does not reproduce every COSMIC desktop feature.

Press Super+Shift+an arrow to move the focused window through the layout tree.
Moving across a split creates a group, enters a neighboring group, or steps out
of the current group. At the workspace edge, movement stops. Windows in each
group share its space equally.

For example, with `A | D | (B / C)`, focus D and press Right twice. The result is
`A | (B / D / C)`. B, D, and C share the right half equally.

## Requirements

Tested with Hyprland **0.56.2** and Omarchy's Lua configuration. Older `.conf`
setups are unsupported. Other Hyprland releases need a compatible hy3 revision
and a fresh build. Keep the default `~/.config` location.

The build needs Python 3.9+, curl, tar, patch, CMake, Ninja, pkg-config, a C++23
compiler, and development files for Hyprland, pixman, libdrm, Pango, libinput,
Wayland, and xkbcommon. The installer does not install system packages.

This is a Hyprland plugin with an Omarchy configuration module. Use the installer
below. Omarchy's `omarchy plugin` command manages shell widgets and does not
install this layout. Do not load a second copy of hy3 alongside this package.

## Install

Download or clone this repository, open its directory, and run:

```bash
git clone https://github.com/ralphsmith80/omarchy-equal-tiling.git
cd omarchy-equal-tiling
python3 install.py --build
python3 install.py          # Preview the files that will change
python3 install.py --apply  # Back up and install
```

The build verifies a pinned source archive, applies `hy3.patch`, and compiles
against the installed Hyprland headers. It writes only to `.build/`. The first
build requires internet access. Unchanged builds skip the download and compile.

Apply installs these files and adds `require("hypr.equal-tiling")` to your main
Hyprland Lua configuration before Omarchy restores saved workspace layouts:

- `~/.config/hypr/equal-tiling.lua`
- `~/.local/lib/omarchy-equal-tiling/libhy3-cosmic.so`
- `~/.local/lib/omarchy-equal-tiling/hyprland-commit`

The package contains only the tiling configuration. Your monitor settings,
application shortcuts, themes, dictation, and workspace number bindings stay in
your own configuration.

Hyprland may reload when the files change. Then check:

```bash
hyprctl reload
hyprctl configerrors
hyprctl plugin list
```

There should be no configuration errors, and the plugin list should show `hy3`.
The underlying layout and Lua namespace retain the upstream name.

## Shortcuts

| Shortcut | Action |
| --- | --- |
| Super+arrows | Focus a window through hy3's layout tree |
| Super+Shift+arrows | Move a window through tiling groups |
| Super+T | Float or retile the window, then balance the group |
| Super+L | Switch the workspace between equal tiling and scrolling |

These replace Omarchy's directional focus, directional swap, floating, and
workspace layout shortcuts. Super+J, Omarchy's split toggle, is disabled because
Super+Shift+arrows controls the arrangement. Other shortcuts remain available.
Movement does not move windows across monitors. This package does not reproduce
the whole COSMIC desktop or its tab behavior.

## Updates and removal

After updating Hyprland, log in again and rerun the build, preview, and apply
commands. The configuration skips the plugin when its build commit differs from
the running compositor. Saved layouts created by Super+L fall back to dwindle
when hy3 is unavailable. Replacing a loaded library can require a new session.

Changed files are backed up under `~/.local/state/omarchy-equal-tiling/restore-*`.
Each apply prints its exact rollback command. Run that command to undo the apply.
For several updates, undo backups in reverse order to remove the full install.
Rollback preserves files that you changed after the install and reports the
conflict instead of overwriting them. It restores the main configuration's exact
prior contents, so reconcile later main-config edits before rolling back.

Apply also detects edits to files it installed. Use `--overwrite-local --apply`
only when you intend to back up and replace those edits. Symlink and directory
conflicts stop the operation before configuration writes. An installation that
already uses the dotfiles `hypr.dotfiles` tiling module must remove that module's
tiling setup before installing this package.

## Development

```bash
python3 -m unittest discover -s tests -v
python3 install.py --build
python3 tests/session.py
```

The session test requires an active Wayland desktop and `foot`. It opens a
separate nested Hyprland window with a temporary home. It checks the compiled
plugin's movement and equal sizing, floating, saved layout toggles, reload,
installation, repeated apply, and rollback. It does not load the plugin into
your existing desktop.

`hy3.patch` applies to upstream commit
`42b7ed8fd9aefd3f36e5f617afd5071245c67853`. The expected archive SHA-256 is
`b4b8842cdfb0562f1f4228ef35c746f040379a33ee0912ad089f693206c34076`.
The patch adds `hl.plugin.hy3.move_cosmic(direction)` and leaves upstream movement
and focus dispatchers intact. Update the source pin and checksum together, then
build and run both checks before publishing a release.

## License and credit

GPL-3.0, see [LICENSE](LICENSE). hy3 is by outfoxxed and its contributors.
Ralph Smith's package adds the directional movement patch, Omarchy configuration,
and installer. Omarchy-derived configuration retains its MIT notice in
[LICENSE.omarchy](LICENSE.omarchy).
