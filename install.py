#!/usr/bin/env python3
"""Install equal tiling for Omarchy. Preview by default; never install packages."""

import argparse
from contextlib import contextmanager
import hashlib
import fcntl
import json
import os
from pathlib import Path
import platform
import re
import shlex
import stat
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parent
PROFILE = REPO
BUILD = PROFILE / ".build"
OMARCHY = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy"))
HY3_COMMIT = "42b7ed8fd9aefd3f36e5f617afd5071245c67853"
ARCHIVE_SHA256 = "b4b8842cdfb0562f1f4228ef35c746f040379a33ee0912ad089f693206c34076"
OUTPUTS = {"libhy3-cosmic.so": ".local/lib/omarchy-equal-tiling/libhy3-cosmic.so",
           "hyprland-commit": ".local/lib/omarchy-equal-tiling/hyprland-commit"}

def safe_path(root, relative):
    """Refuse symlinks and non-directory parents before reading or writing."""
    relative = Path(relative)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError(f"Unsafe relative path: {relative}")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Refusing symlink: {current}")
        if current.exists() and current != root / relative and not current.is_dir():
            raise ValueError(f"Parent is not a directory: {current}")
    if current.exists() and not current.is_file():
        raise ValueError(f"Not a regular file: {current}")
    return current


def fingerprint(data, mode):
    return {"sha256": hashlib.sha256(data).hexdigest(), "mode": mode}


def state(path):
    if not path.exists():
        return None
    return fingerprint(path.read_bytes(), stat.S_IMODE(path.stat().st_mode))


def atomic_write(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".equal-tiling-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def build_signature():
    return {"upstream": HY3_COMMIT, "arch": platform.machine(),
            "headers": hashlib.sha256(Path("/usr/include/hyprland/src/version.h").read_bytes()).hexdigest(),
            "patch": hashlib.sha256((PROFILE / "hy3.patch").read_bytes()).hexdigest()}


def build_current(signature):
    metadata = BUILD / "signature.json"
    if not metadata.is_file():
        return False
    saved = json.loads(metadata.read_text())
    return saved.get("inputs") == signature and all(
        saved.get("outputs", {}).get(name) is not None
        and state(safe_path(BUILD, name)) == saved["outputs"][name] for name in OUTPUTS)


@contextmanager
def build_lock():
    """The kernel releases this lock even when a build is interrupted."""
    BUILD.mkdir(parents=True, exist_ok=True)
    marker = safe_path(BUILD, ".build.lock")
    with marker.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another native build is running. Retry when it finishes.") from None
        yield


def build_hy3():
    signature = build_signature()
    BUILD.mkdir(parents=True, exist_ok=True)
    with build_lock():
        if build_current(signature):
            print("hy3 build is unchanged; skipping download and compile.")
            return
        (BUILD / "signature.json").unlink(missing_ok=True)
        with tempfile.TemporaryDirectory(prefix="compile-", dir=BUILD) as temporary:
            work = Path(temporary)
            archive = work / "hy3.tar.gz"
            url = f"https://codeload.github.com/outfoxxed/hy3/tar.gz/{HY3_COMMIT}"
            subprocess.run(["curl", "-fsSL", "--retry", "2", url, "-o", str(archive)], check=True)
            if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
                raise ValueError("hy3 download checksum mismatch; nothing was built or installed.")
            subprocess.run(["tar", "-xzf", str(archive), "-C", str(work)], check=True)
            source = work / f"hy3-{HY3_COMMIT}"
            subprocess.run(["patch", "--batch", "--forward", "-p1", "-i", str(PROFILE / "hy3.patch")], cwd=source, check=True)
            subprocess.run(["cmake", "-S", str(source), "-B", str(work / "out"), "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release"], check=True)
            subprocess.run(["cmake", "--build", str(work / "out"), "--parallel", "4"], check=True)
            header = Path("/usr/include/hyprland/src/version.h").read_text()
            commit = re.search(r'^#define\s+GIT_COMMIT_HASH\s+"([0-9a-f]+)"', header, re.MULTILINE)
            if not commit:
                raise ValueError("Cannot identify the installed Hyprland headers.")
            atomic_write(BUILD / "libhy3-cosmic.so", (work / "out/libhy3.so").read_bytes(), 0o755)
            atomic_write(BUILD / "hyprland-commit", (commit[1] + "\n").encode(), 0o644)
        metadata = {"inputs": signature, "outputs": {name: state(BUILD / name) for name in OUTPUTS}}
        atomic_write(BUILD / "signature.json", json.dumps(metadata).encode(), 0o644)
        print("Built patched hy3 in .build. Nothing installed; preview before applying.")


def find_loader(text, module):
    # Ignore long Lua comments/strings while keeping offsets into the original.
    masked = re.sub(r"(?s)(?:--)?\[(=*)\[.*?\]\1\]",
                    lambda match: re.sub(r"[^\n]", " ", match[0]), text)
    return re.search(r'(?m)^[ \t]*require[ \t]*\([ \t]*["\x27]' + re.escape(module)
                     + r'["\x27][ \t]*\)[ \t]*;?[ \t]*(?:--[^\n]*)?$', masked)


def collect_files(args):
    files = {}
    for source in sorted((PROFILE / "config").rglob("*")):
        if source.is_file():
            relative = str(source.relative_to(PROFILE / "config"))
            files[".config/" + relative] = (source.read_bytes(), 0o644)
    if (BUILD / "signature.json").is_file() and build_current(build_signature()):
        for name, relative in OUTPUTS.items():
            source = BUILD / name
            files[relative] = (source.read_bytes(), stat.S_IMODE(source.stat().st_mode))
    elif args.apply:
        raise ValueError("Build custom tiling first: python3 install.py --build")
    else:
        print("BUILD REQUIRED: python3 install.py --build")
    # Keep the machine's main configuration; load our overrides before saved layouts.
    target = ".config/hypr/hyprland.lua"
    main = safe_path(args.home, target)
    original = main.read_bytes()
    mode = stat.S_IMODE(main.stat().st_mode)
    text = original.decode()
    if find_loader(text, "hypr.dotfiles"):
        raise ValueError("hypr.dotfiles already provides this layout. Remove its tiling section and loader dependency before installing this standalone package.")
    loader = 'require("hypr.equal-tiling")'
    if not find_loader(text, "hypr.equal-tiling"):
        toggles = find_loader(text, "default.hypr.toggles")
        if toggles:
            text = text[:toggles.start()] + loader + "\n" + text[toggles.start():]
        else:
            text = text.rstrip() + "\n" + loader + "\n"
    files[target] = (text.encode(), mode)
    return files, {target: fingerprint(original, mode)}


@contextmanager
def write_lock(home):
    marker = safe_path(home, ".local/state/omarchy-equal-tiling/.write-lock")
    marker.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError(f"Another restore may be running. Inspect {marker} before removing a stale lock.") from None
    try:
        os.close(fd)
        yield
    finally:
        marker.unlink()


def rollback(home, backup, apply, only=None):
    backup = backup.resolve()
    journal = json.loads(safe_path(backup, "journal.json").read_text())
    if journal["home"] != str(home):
        raise ValueError("Backup belongs to another home directory.")
    if only is not None:
        journal["files"] = [entry for entry in journal["files"] if entry["target"] in only]
    operations = []
    for entry in reversed(journal["files"]):
        target = safe_path(home, entry["target"])
        current = state(target)
        if current == entry["before"]:
            continue
        if current != entry["after"]:
            raise ValueError(f"Changed since restore; refusing to overwrite: {target}")
        data = None
        if entry["before"] is not None:
            saved = safe_path(backup, "files/" + entry["target"])
            if state(saved) != entry["before"]:
                raise ValueError(f"Backup has changed: {saved}")
            data = saved.read_bytes()
        operations.append((target, data, entry))
    managed = read_managed(home)
    for target, data, entry in operations:
        print(f"UNDO {target}")
        if apply:
            if state(safe_path(home, entry["target"])) != entry["after"]:
                raise ValueError(f"File changed while undo was running: {target}")
            if data is None:
                target.unlink()
            else:
                atomic_write(target, data, entry["before"]["mode"])
    if apply:
        original_managed = dict(managed)
        for entry in journal["files"]:
            # Repair an interrupted undo only while this restore still owns the
            # fingerprint. An old undo must not erase newer ownership records.
            if ("managed_before" in entry and managed.get(entry["target"]) == entry["after"]
                    and state(safe_path(home, entry["target"])) == entry["before"]):
                if entry["managed_before"] is None:
                    managed.pop(entry["target"], None)
                else:
                    managed[entry["target"]] = entry["managed_before"]
        if managed != original_managed:
            save_managed(home, managed)
    print(f"{'Restored' if apply else 'Would restore'} {len(operations)} files.")


def read_managed(home):
    path = safe_path(home, ".local/state/omarchy-equal-tiling/managed.json")
    return json.loads(path.read_text()) if path.exists() else {}


def save_managed(home, managed):
    atomic_write(safe_path(home, ".local/state/omarchy-equal-tiling/managed.json"), json.dumps(managed, sort_keys=True).encode(), 0o600)


def restore_files(args, files, expected=None):
    managed = read_managed(args.home)
    updated_managed = dict(managed)
    changes = []
    for relative, (data, mode) in files.items():
        target = safe_path(args.home, relative)
        before, after = state(target), fingerprint(data, mode)
        # Transformed files must still match the bytes read during collection.
        if expected and relative in expected and before != expected[relative]:
            raise ValueError(f"File changed during collection: {target}. Preview again.")
        if before != after:
            if relative in managed and before != managed[relative] and not args.overwrite_local:
                raise ValueError(f"Edited since last apply: {target}. Save the edit to the repository or use --overwrite-local to back up and replace it.")
            print(f"{'REPLACE' if before else 'CREATE '} {relative}")
            changes.append(({"target": relative, "before": before, "after": after, "managed_before": managed.get(relative)}, data))
        updated_managed[relative] = after
    print(f"{len(changes)} changes. {'Applying.' if args.apply else 'Preview only; use --apply to write.'}")
    if not args.apply or (not changes and managed == updated_managed):
        return
    with write_lock(args.home):
        if read_managed(args.home) != managed:
            raise ValueError("Another restore changed the managed files. Preview again.")
        if not changes:
            save_managed(args.home, updated_managed)
            return
        backup = Path(tempfile.mkdtemp(prefix="restore-", dir=args.home / ".local/state/omarchy-equal-tiling"))
        for entry, _ in changes:
            target = safe_path(args.home, entry["target"])
            if state(target) != entry["before"]:
                raise ValueError(f"File changed during preview: {target}")
            if entry["before"] is not None:
                atomic_write(backup / "files" / entry["target"], target.read_bytes(), entry["before"]["mode"])
        journal = {"home": str(args.home), "files": [entry for entry, _ in changes]}
        atomic_write(backup / "journal.json", (json.dumps(journal, indent=2) + "\n").encode(), 0o600)
        print(f"Backup: {backup}", flush=True)
        written = set()
        try:
            for entry, data in changes:
                target = safe_path(args.home, entry["target"])
                if state(target) != entry["before"]:
                    raise ValueError(f"File changed during restore: {target}")
                atomic_write(target, data, entry["after"]["mode"])
                written.add(entry["target"])
            save_managed(args.home, updated_managed)
        except (OSError, ValueError, KeyboardInterrupt):
            print("Apply failed. Attempting rollback.", file=sys.stderr)
            # An untouched later file may have been edited concurrently. It must
            # not block undoing the files this apply actually replaced.
            rollback(args.home, backup, True, only=written)
            raise
    command = ["python3", str(REPO / "install.py"), "--home", str(args.home), "--rollback", str(backup), "--apply"]
    print("Undo: " + shlex.join(command))
    print("After login, check: hyprctl reload && hyprctl configerrors && hyprctl plugin list")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true", help="Back up and apply the overrides")
    action.add_argument("--build", action="store_true", help="Download pinned hy3, apply our patch, and build locally")
    parser.add_argument("--overwrite-local", action="store_true", help="Back up and replace later local edits")
    parser.add_argument("--rollback", type=Path, help="Preview an undo; add --apply to perform it")
    parser.add_argument("--home", type=Path, default=Path.home(), help="Target home; must have Omarchy's config already")
    args = parser.parse_args()
    args.home = args.home.expanduser().resolve()
    try:
        if not args.home.is_dir():
            raise ValueError("Target home must exist.")
        if args.rollback:
            if args.build:
                parser.error("--build and --rollback cannot be combined")
            if args.apply:
                with write_lock(args.home):
                    rollback(args.home, args.rollback, True)
            else:
                rollback(args.home, args.rollback, False)
        elif platform.system() != "Linux" or not (OMARCHY / "default/hypr/bootstrap.lua").is_file():
            raise ValueError("This package requires Omarchy with Lua configuration.")
        elif args.build:
            build_hy3()
        else:
            if os.environ.get("XDG_CONFIG_HOME") and Path(os.environ["XDG_CONFIG_HOME"]).resolve() != args.home / ".config":
                raise ValueError("These overrides require Omarchy's standard ~/.config location.")
            if args.apply and BUILD.is_dir():
                with build_lock():
                    files, expected = collect_files(args)
            else:
                files, expected = collect_files(args)
            restore_files(args, files, expected)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
