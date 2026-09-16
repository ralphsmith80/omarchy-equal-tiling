"""Check the Omarchy restore in disposable homes, without a desktop session."""

import argparse
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "install.py"
spec = importlib.util.spec_from_file_location("omarchy", SCRIPT)
omarchy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(omarchy)


class RestoreTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="equal tiling test's ")
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.args = argparse.Namespace(home=self.home, apply=False, overwrite_local=False)
        self.output = io.StringIO()
        capture = redirect_stdout(self.output)
        capture.__enter__()
        self.addCleanup(capture.__exit__, None, None, None)
        self.files = {"config": (b"saved configuration", 0o644)}

    def backups(self):
        return set((self.home / ".local/state/omarchy-equal-tiling").glob("restore-*"))

    def test_preview_apply_repeat_and_undo_preserve_bytes_and_permissions(self):
        omarchy.restore_files(self.args, self.files)
        self.assertEqual(list(self.home.iterdir()), [])
        target = self.home / "config"
        target.write_bytes(b"original\x00\xff")
        target.chmod(0o600)
        original = omarchy.state(target)
        self.args.apply = True
        omarchy.restore_files(self.args, self.files)
        backup = self.backups().pop()
        self.assertEqual(backup.stat().st_mode & 0o777, 0o700)
        omarchy.restore_files(self.args, self.files)
        self.assertEqual(len(self.backups()), 1)
        omarchy.rollback(self.home, backup, False)
        self.assertEqual(target.read_bytes(), self.files["config"][0])
        omarchy.rollback(self.home, backup, True)
        self.assertEqual(omarchy.state(target), original)
        omarchy.rollback(self.home, backup, True)

    def test_local_edits_need_explicit_replacement_and_are_backed_up(self):
        self.args.apply = True
        omarchy.restore_files(self.args, self.files)
        target = self.home / "config"
        target.write_bytes(b"local edit")
        with self.assertRaisesRegex(ValueError, "Edited since last apply"):
            omarchy.restore_files(self.args, self.files)
        backups = self.backups()
        self.args.overwrite_local = True
        omarchy.restore_files(self.args, self.files)
        backup = (self.backups() - backups).pop()
        self.assertEqual((backup / "files/config").read_bytes(), b"local edit")
        target.write_bytes(b"another edit")
        with self.assertRaisesRegex(ValueError, "Changed since restore"):
            omarchy.rollback(self.home, backup, True)

    def test_old_undo_cannot_remove_new_edit_protection(self):
        target = self.home / "config"
        target.write_bytes(b"original")
        self.args.apply = True
        omarchy.restore_files(self.args, self.files)
        backup = self.backups().pop()
        omarchy.rollback(self.home, backup, True)
        original_files = {"config": (b"original", 0o644)}
        omarchy.restore_files(self.args, original_files)
        omarchy.rollback(self.home, backup, True)
        target.write_bytes(b"new local edit")
        with self.assertRaisesRegex(ValueError, "Edited since last apply"):
            omarchy.restore_files(self.args, original_files)

    def test_interrupted_undo_can_repair_metadata_on_retry(self):
        (self.home / "config").write_bytes(b"original")
        self.args.apply = True
        omarchy.restore_files(self.args, self.files)
        backup = self.backups().pop()
        with patch.object(omarchy, "save_managed", side_effect=OSError("full disk")):
            with self.assertRaises(OSError):
                omarchy.rollback(self.home, backup, True)
        omarchy.rollback(self.home, backup, True)
        omarchy.restore_files(self.args, self.files)
        self.assertEqual((self.home / "config").read_bytes(), self.files["config"][0])

    def test_conflicts_are_rejected_before_any_configuration_write(self):
        self.args.apply = True
        outside = self.home / "outside"
        outside.mkdir()
        (self.home / "linked").symlink_to(outside)
        for relative in ["linked/file", "../escape", "outside"]:
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                omarchy.restore_files(self.args, {"first": (b"value", 0o644), relative: (b"value", 0o644)})
            self.assertFalse((self.home / "first").exists())
        with omarchy.write_lock(self.home):
            with self.assertRaisesRegex(ValueError, "Another restore"):
                with omarchy.write_lock(self.home):
                    self.fail("Concurrent writer acquired the lock")

    def test_failed_apply_restores_already_written_files(self):
        self.args.apply = True
        atomic_write = omarchy.atomic_write

        def fail_second(path, data, mode):
            if path == self.home / "second":
                raise OSError("full disk")
            atomic_write(path, data, mode)

        with patch.object(omarchy, "atomic_write", side_effect=fail_second):
            with self.assertRaises(OSError):
                omarchy.restore_files(self.args, {"first": (b"value", 0o644), "second": (b"value", 0o644)})
        self.assertFalse((self.home / "first").exists())

    def test_concurrent_edit_of_later_file_does_not_block_automatic_undo(self):
        self.args.apply = True
        (self.home / "first").write_bytes(b"original first")
        (self.home / "second").write_bytes(b"original second")
        atomic_write = omarchy.atomic_write

        def edit_second(path, data, mode):
            atomic_write(path, data, mode)
            if path == self.home / "first" and data == b"new first":
                (self.home / "second").write_bytes(b"concurrent edit")

        with patch.object(omarchy, "atomic_write", side_effect=edit_second):
            with self.assertRaisesRegex(ValueError, "File changed during restore"):
                omarchy.restore_files(self.args, {"first": (b"new first", 0o644), "second": (b"new second", 0o644)})
        self.assertEqual((self.home / "first").read_bytes(), b"original first")
        self.assertEqual((self.home / "second").read_bytes(), b"concurrent edit")

    def test_printed_undo_quotes_shell_paths(self):
        self.args.apply = True
        with patch.object(omarchy, "REPO", self.home / "my checkout"):
            omarchy.restore_files(self.args, self.files)
        command = self.output.getvalue().split("Undo: ", 1)[1].splitlines()[0]
        self.assertEqual(omarchy.shlex.split(command)[1], str(self.home / "my checkout/install.py"))

    def test_main_config_is_preserved_and_only_tiling_is_installed(self):
        main = self.home / ".config/hypr/hyprland.lua"
        main.parent.mkdir(parents=True)
        original = 'require("default.hypr.omarchy")\n-- personal settings\nrequire("default.hypr.toggles")\n'
        main.write_text(original)
        with patch.object(omarchy, "BUILD", self.home / "no-build"):
            files, expected = omarchy.collect_files(self.args)
            self.assertEqual(set(files), {".config/hypr/equal-tiling.lua", ".config/hypr/hyprland.lua"})
            edited = files[".config/hypr/hyprland.lua"][0].decode()
            self.assertIn('-- personal settings\nrequire("hypr.equal-tiling")\nrequire("default.hypr.toggles")', edited)
            main.write_text(edited)
            self.assertEqual(omarchy.collect_files(self.args)[0][".config/hypr/hyprland.lua"][0], edited.encode())
            self.args.apply = True
            with self.assertRaisesRegex(ValueError, "Build custom tiling first"):
                omarchy.collect_files(self.args)

    def test_build_cache_checks_inputs_and_actual_outputs(self):
        build = self.home / "build"
        build.mkdir()
        for name in omarchy.OUTPUTS:
            (build / name).write_bytes(b"output")
        signature = {"version": "test"}
        metadata = {"inputs": signature, "outputs": {name: omarchy.state(build / name) for name in omarchy.OUTPUTS}}
        (build / "signature.json").write_text(json.dumps(metadata))
        with patch.object(omarchy, "BUILD", build), patch.object(omarchy, "build_signature", return_value=signature):
            with patch.object(omarchy.subprocess, "run", side_effect=AssertionError("Build should be skipped")):
                omarchy.build_hy3()
            self.assertFalse(omarchy.build_current({"version": "changed"}))
            (build / "libhy3-cosmic.so").write_bytes(b"corrupt")
            self.assertFalse(omarchy.build_current(signature))

    def test_edit_after_collection_is_rejected_before_any_write(self):
        main = self.home / ".config/hypr/hyprland.lua"
        main.parent.mkdir(parents=True)
        main.write_text('require("default.hypr.toggles")\n')
        with patch.object(omarchy, "BUILD", self.home / "no-build"):
            files, expected = omarchy.collect_files(self.args)
        edited = main.read_text() + '-- saved by editor while apply was starting\n'
        main.write_text(edited)
        self.args.apply = True
        with self.assertRaisesRegex(ValueError, "File changed during collection"):
            omarchy.restore_files(self.args, files, expected)
        self.assertEqual(main.read_text(), edited)
        self.assertFalse((main.parent / "equal-tiling.lua").exists())
        self.assertEqual(self.backups(), set())

    def test_commented_loaders_are_ignored_and_single_quotes_are_supported(self):
        main = self.home / ".config/hypr/hyprland.lua"
        main.parent.mkdir(parents=True)
        comments = '-- require("hypr.equal-tiling")\n--[=[\nrequire("hypr.equal-tiling")\nrequire("default.hypr.toggles")\n]=]\n'
        original = comments + "require('default.hypr.toggles') -- saved layouts\n"
        main.write_text(original)
        with patch.object(omarchy, "BUILD", self.home / "no-build"):
            edited = omarchy.collect_files(self.args)[0][".config/hypr/hyprland.lua"][0].decode()
        self.assertIn(comments, edited)
        loader = omarchy.find_loader(edited, "hypr.equal-tiling")
        self.assertIsNotNone(loader)
        self.assertLess(loader.start(), omarchy.find_loader(edited, "default.hypr.toggles").start())

    def test_other_systems_fail_without_writing(self):
        env = dict(os.environ, OMARCHY_PATH=str(self.home / "not-omarchy"))
        result = subprocess.run(["python3", str(SCRIPT), "--home", str(self.home), "--apply"], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("requires Omarchy with Lua", result.stderr)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_combined_dotfiles_setup_is_rejected_before_install(self):
        main = self.home / ".config/hypr/hyprland.lua"
        main.parent.mkdir(parents=True)
        original = 'require("hypr.dotfiles")\n'
        main.write_text(original)
        with patch.object(omarchy, "BUILD", self.home / "no-build"):
            with self.assertRaisesRegex(ValueError, "already provides this layout"):
                omarchy.collect_files(self.args)
        self.assertEqual(main.read_text(), original)
        self.assertFalse((main.parent / "equal-tiling.lua").exists())


if __name__ == "__main__":
    unittest.main()
