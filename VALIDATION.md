# Validation

Validated on 2026-09-16 with Hyprland 0.56.2, commit
`efb50993780079460b0cbed1363e2166a2de1d9f`, on Linux x86_64.

- Downloaded the pinned hy3 archive, verified its SHA-256, applied the patch,
  and compiled the shared library against the installed headers.
- All 14 installer tests passed. These cover backups, byte and permission
  preservation, local edits, write failures, concurrent edits, symlink conflicts,
  loader insertion, build-cache integrity, conflicting dotfiles setup, and an
  editor save between configuration collection and apply.
- Loaded the built library in a separate nested Hyprland session with a temporary
  home and four real foot windows. No plugin was loaded into the existing desktop.
- Verified directional grouping, equal sibling sizes, workspace-edge behavior,
  and 40 mixed-direction moves. All windows kept positive sizes and did not
  overlap. Focus stayed on the moved window.
- Verified floating and retiling, saved workspace layout toggles, configuration
  reload, and movement after reload.
- Resized sibling windows, floated one, and verified the remaining tiles became
  equal. Verified custom XDG_STATE_HOME layouts take priority over conflicting
  default-state files across two reloads, including the missing-plugin fallback.
- Changed the temporary install's build stamp to an incompatible commit. Reload
  skipped the plugin without configuration errors. Restoring the stamp loaded
  the plugin again.
- Ran the real installer in the temporary home. Preview wrote no configuration,
  repeated apply changed no files, and rollback restored the prior main config
  and removed the installed module and library.

The nested test uses Omarchy's module bootstrap and a minimal configuration.
Other Hyprland releases, multiple monitors, and full desktop startup on another
machine have not been tested. Reproduce with the commands in README.md.

## Publication review

Quality score: 100/100 under the QA code-review checklist. Two independent,
read-only scenario reviews covered the installer and layout code. No findings
remain open after fixes and runtime verification.

- Fixed a first-install race that could replace an editor save made after the
  installer read the main configuration. Apply now checks the original input
  fingerprint before any write. A regression test confirms the edit survives.
- Fixed balancing being skipped while the focused window is floating.
- Fixed saved layout paths and module lookup when XDG_STATE_HOME is customized.
  The module gives that directory priority before the plugin version guard so
  fallback layouts also load correctly.
- Scanned tracked files and reachable Git history for embedded credentials,
  private keys, known token formats, and private machine paths. None were found.
  Public commit metadata uses GitHub's noreply email address.
- Reviewed network and command execution. The installer downloads pinned hy3
  source over HTTPS and checks its SHA-256 before unpacking or building. No
  unexpected uploads or telemetry were found in the reviewed code.
- Retained upstream GPL and Omarchy MIT notices. The README credits COSMIC as
  the intended behavior and states the limits of this independent implementation.
