# Validation

## Setup check and preview

Validated on 2026-10-01 with Hyprland 0.56.2.

- `python3 install.py --check` passed against the installed tools and development
  libraries. In a read-only Bubblewrap filesystem with Ninja and Hyprland's
  pkg-config file hidden, it returned exit 1 and named both missing requirements.
  The sandbox had no network access and did not change system packages.
- All 26 automated tests passed, including grouped prerequisite failures,
  unsupported tool versions, check exit status, and stopping before download.
- Exercised cancelled-build recovery and a fresh native build through the actual
  Omarchy service. The library compiled and loaded in the disposable compositor.
  The full lifecycle test then passed using the verified cached build.
- Corrected two test assumptions exposed during fresh-build runs. The square
  assertion now sets zero aspect-ratio tolerance in the test compositor. The
  reload test waits for the service callback instead of accepting Omarchy's
  temporary default dispatcher. Runtime tiling code is unchanged.
- Captured and inspected the 1600x900 preview from four real windows. Geometry
  checks confirmed equal column widths and three equal heights on the right.
  The screenshot contains public demo text only.
- Checked dependency package names against the installed Arch package database
  and repository metadata. Manifest validation and diff checks passed. An
  independent scenario review found no P1 or P2 issues.

## Build security changes

Validated on 2026-09-29 against Hyprland 0.56.2 and curl 8.22.0.

- Rebuilt the pinned native source with invalid inherited PATH, CC, CXX,
  CMAKE_TOOLCHAIN_FILE, CMAKE_PROJECT_INCLUDE, CMAKE_PROJECT_INCLUDE_BEFORE,
  CXXFLAGS, LDFLAGS, LD_PRELOAD, PYTHONPATH, PKG_CONFIG_PATH, TAR_OPTIONS, and
  CURL_HOME values. The build used the system compiler and completed successfully.
- Tested actual curl transfers against a local HTTPS server. Oversized responses
  with and without Content-Length stopped with exit 63. A stalled response hit
  the total deadline with exit 28. Invalid checksums removed the download.
  Valid downloads ignored user curl configuration. Older curl versions were
  rejected before transfer because they lack a streaming size limit.
- Checked the actual QML launcher in an offscreen Quickshell with a fake Python
  on PATH and a Python startup hook. The worker used `/usr/bin/python3`, disabled
  site startup and Python environment controls, and received only the documented
  session environment. This test also caught and fixed a missing Quickshell.Io
  import that a full Omarchy shell had masked.
- Ran the fresh-build plugin lifecycle test in a disposable home, nested
  compositor, and private shell. Cancelling a build, enabling again, loading hy3,
  reload, disable/enable, rapid toggles, ownership conflict, update, shell restart,
  and removal passed. The test did not edit the active desktop's configuration.
- All 22 automated tests passed. The separate layout and installer session test,
  manifest validation, and diff checks passed. An independent scenario review
  found no P1 or P2 issues. The QML linter reports the Quickshell.Io import as
  unused, but the standalone launcher test confirms it is needed to register
  the process context type.

The catalog's approval and automated validation are separate from these local
checks. The corrected commit still needs marketplace revalidation and review.

## Initial validation

Validated on 2026-09-16 with Hyprland 0.56.2, commit
`efb50993780079460b0cbed1363e2166a2de1d9f`, on Linux x86_64.

- Downloaded the pinned hy3 archive, verified its SHA-256, applied the patch,
  and compiled the shared library against the installed headers.
- All 16 unit tests passed. The 14 installer tests cover backups, byte and permission
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
- Verified custom XDG_STATE_HOME layouts take priority over conflicting
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

## Priority column and manual sizes in 0.3.0

Validated on 2026-09-24 with the same Hyprland build.

- Removed automatic balancing. The first grouping check and the 40 random moves
  still passed, so hy3 keeps tiles equal without it.
- Pressed Super+Alt+P on the middle of three columns. Each side column was
  within 4 px of a quarter of the combined width, and the middle column was
  within 8 px of half.
- Opened and closed a fourth window and switched workspaces. The three widths
  stayed within 4 px of their priority sizes.
- Pressed Super+Alt+P again on the middle column, and then on a side column
  while priority was on. Both times, all tiles became equal.
- Made the right column over 75% wide, then pressed Super+Alt+P. Both side
  columns reached a quarter. The wider side is resized first, and a second pass
  corrects the few pixels that hy3 loses to gaps.
- Built two rows of three windows and pressed Super+Alt+P on the top middle
  window. Both rows got the priority split.
- With window animations slowed down, Lua reported the final window size right
  after a resize. The second pass therefore reads settled sizes.
- Ran the plugin lifecycle test and all 16 unit tests again. All passed.

## Omarchy plugin lifecycle in 0.2.0

- Validated `manifest.json` with `omarchy plugin validate` and checked `Service.qml`
  with Qt's QML linter.
- Started the real Omarchy shell on a private D-Bus session with a temporary home
  and a separate nested compositor.
- Ran actual `omarchy plugin add --enable`, disable, enable, update, and remove.
  Verified that add loads hy3, reload restores movement bindings, update runs the
  new Lua module, and disable/removal unload hy3 without editing Hyprland files.
- Restarted the isolated shell while enabled and then removed the plugin.
- Loaded a separate hy3 instance, enabled the service, and confirmed it reported
  the conflict without unloading or replacing that instance.
- Ran three rapid disable/enable cycles and verified that tiling stayed active.
- Cancelled an uncached native build, then enabled again. The retry downloaded,
  compiled, and activated the plugin successfully.
- Added deterministic tests for re-enable during cleanup and kernel build-lock
  release after SIGTERM. These reproduce both service review findings.

## Publication review

Independent scenario reviews covered the installer, layout, and Omarchy service
lifecycle. The service review found two disable/re-enable bugs. Both were fixed
and have regression tests. No concrete high- or medium-severity findings remain
open after review and runtime verification.

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
## Omarchy window controls in 0.3.1

- Built the pinned native source with the updated patch against Hyprland 0.56.2.
- Ran `python3 tests/session.py` in a disposable nested compositor. Verified
  centered 1:1 and 4:3 single-window ratios, tolerance, fullscreen transitions,
  adding and closing a second tile, disabling the ratio, and pseudotiling.
- Verified that Omarchy's Super+J binding remains registered and changes a split
  in both directions. Native Super+G groups retained usable geometry, accepted a
  second window, switched tabs by cycle and index, extracted and rejoined a
  window, and dissolved back into tiles.
- The existing movement, equal sizing, priority column, floating, reload,
  saved-layout, build mismatch, and installer rollback checks also passed.
- Ran `python3 tests/plugin_session.py` with a private Omarchy shell. The actual
  square-toggle command resized the window after the service reapplied the
  layout, and toggling off restored its size. Super+J remained registered.
  Add, enable, disable, update, reload, ownership conflict, and removal passed.
- All 16 installer and service unit tests passed. `omarchy plugin validate .`
  and `git diff --check` passed. An independent code review found no P1 or P2
  findings.
