# Changelog

## Unreleased

- Add `install.py --check` and automatic checks before fresh builds, with
  missing tools and development libraries listed by their Arch package names.
- Document the dependency setup command and add an equal-tiling preview.

- Build with fixed system tools and a clean environment. Start Python without
  inherited loader settings or Python startup hooks.
- Limit archive downloads to 8 MiB and 120 seconds, with a 15-second connection
  timeout. Require curl 8.4.0 or newer and verify checksums in fixed-size chunks.
- Rebuild native libraries cached before the build environment changes.

## 0.3.1

- Honor Omarchy's single-window aspect ratio and tolerance, including the
  Super+Ctrl+Backspace square-window toggle.
- Keep Super+J available to switch a split between horizontal and vertical.
- Fix native window grouping with Super+G by keeping the layout's target
  references in sync when Hyprland creates or dissolves a group.

## 0.3.0

- Add Super+Alt+P. It gives the middle of three columns half the workspace
  width, and the side columns share the rest. Press it again to make all tiles
  equal.
- Stop resetting sizes when windows open, close, move, or float, and when you
  switch workspaces. hy3 already gives each new tile an equal share. A config
  reload still rebuilds the layout with equal tiles.
- Use Omarchy's default Super+T binding again.

## 0.2.0

- Add an Omarchy service manifest and QML entry point for `omarchy plugin add`.
- Build and load hy3 while enabled without editing Hyprland configuration files.
- Restore saved configuration on disable and removal.
- Handle compositor reload, shell restart, plugin update, and interrupted builds.
- Reject an existing hy3 setup without unloading it.
- Test the actual Omarchy plugin commands in an isolated shell and compositor.

## 0.1.0

- Document the goal of replicating Pop!_OS COSMIC's tiling and window movement.
- Package the existing equal-tiling setup for Omarchy with Hyprland 0.56.2.
- Add directional group movement, automatic equal sizing, and scrolling toggle.
- Build pinned hy3 source with a verified checksum.
- Preview installation, back up changed files, and support rollback.
- Preserve configuration edits made while installation is being prepared.
- Balance tiles after floating and restore layouts from custom state directories.
- Test installation in temporary homes and movement in a nested compositor.
