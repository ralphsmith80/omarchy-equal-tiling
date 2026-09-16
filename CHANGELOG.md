# Changelog

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
