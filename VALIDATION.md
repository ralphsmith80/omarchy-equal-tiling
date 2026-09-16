# Validation

Validated on 2026-09-16 with Hyprland 0.56.2, commit
`efb50993780079460b0cbed1363e2166a2de1d9f`, on Linux x86_64.

- Downloaded the pinned hy3 archive, verified its SHA-256, applied the patch,
  and compiled the shared library against the installed headers.
- All 13 installer tests passed. These cover backups, byte and permission
  preservation, local edits, write failures, concurrent edits, symlink conflicts,
  loader insertion, build-cache integrity, and conflicting dotfiles setup.
- Loaded the built library in a separate nested Hyprland session with a temporary
  home and four real foot windows. No plugin was loaded into the existing desktop.
- Verified directional grouping, equal sibling sizes, workspace-edge behavior,
  and 40 mixed-direction moves. All windows kept positive sizes and did not
  overlap. Focus stayed on the moved window.
- Verified floating and retiling, saved workspace layout toggles, configuration
  reload, and movement after reload.
- Changed the temporary install's build stamp to an incompatible commit. Reload
  skipped the plugin without configuration errors. Restoring the stamp loaded
  the plugin again.
- Ran the real installer in the temporary home. Preview wrote no configuration,
  repeated apply changed no files, and rollback restored the prior main config
  and removed the installed module and library.

The nested test uses Omarchy's module bootstrap and a minimal configuration.
Other Hyprland releases, multiple monitors, and full desktop startup on another
machine have not been tested. Reproduce with the commands in README.md.
