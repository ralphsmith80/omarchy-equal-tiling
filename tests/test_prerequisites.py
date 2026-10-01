"""Check actionable setup failures before any download or native build."""
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("installer", ROOT / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class PrerequisiteTest(unittest.TestCase):
    def test_missing_tools_and_transitive_libraries_are_reported_together(self):
        commands = []

        def probe(command, **kwargs):
            commands.append(command)
            self.assertEqual(kwargs["env"], installer.build_environment("/tmp/check"))
            self.assertEqual(kwargs["cwd"], Path("/tmp/check"))
            failed = command[-1] in {"hyprland", "pango", "pangocairo"}
            return subprocess.CompletedProcess(command, int(failed), stdout="",
                                               stderr="Package dependency missing" if failed else "")

        with patch.object(installer.os, "access", side_effect=lambda path, _: path not in {
                "/usr/bin/curl", "/usr/bin/ninja", "/usr/bin/c++"}), \
                patch.object(Path, "is_file", return_value=False), \
                patch.object(installer.subprocess, "run", side_effect=probe):
            errors = installer.prerequisite_errors(installer.build_environment("/tmp/check"), Path("/tmp/check"))
        message = "\n".join(errors)
        for expected in ("/usr/bin/curl", "/usr/bin/ninja", "/usr/bin/c++", "version.h",
                         "hyprland", "pango", "Package dependency missing"):
            self.assertIn(expected, message)
        self.assertTrue(all(command[0] == "/usr/bin/pkg-config" for command in commands))

    def test_unsupported_curl_and_compiler_are_reported_together(self):
        def probe(command, **_kwargs):
            if command[0] == "/usr/bin/curl":
                return subprocess.CompletedProcess(command, 0, stdout="curl 8.3.0", stderr="")
            failed = command[0] == "/usr/bin/c++"
            return subprocess.CompletedProcess(command, int(failed), stdout="",
                                               stderr="unrecognized option -std=c++23" if failed else "")

        with patch.object(installer.os, "access", return_value=True), \
                patch.object(Path, "is_file", return_value=True), \
                patch.object(installer.subprocess, "run", side_effect=probe):
            message = "\n".join(installer.prerequisite_errors({}, Path("/tmp")))
        self.assertIn("curl 8.4.0", message)
        self.assertIn("C++23 compiler support", message)

    def test_check_exit_status_and_no_installation_side_effects(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            for errors, status in (([], 0), (["Missing /usr/bin/ninja. Arch package: ninja."], 1)):
                output = io.StringIO()
                with self.subTest(errors=errors), \
                        patch.object(sys, "argv", ["install.py", "--check", "--home", str(home)]), \
                        patch.object(Path, "is_file", return_value=True), \
                        patch.object(installer, "prerequisite_errors", return_value=errors), \
                        patch.object(installer, "build_hy3", side_effect=AssertionError("must not build")), \
                        patch.object(installer, "collect_files", side_effect=AssertionError("must not install")), \
                        redirect_stdout(output), redirect_stderr(output):
                    self.assertEqual(installer.main(), status)
                self.assertEqual(list(home.iterdir()), [])
                self.assertIn("ninja" if errors else "Build prerequisites passed", output.getvalue())

    def test_fresh_build_stops_before_downloading_when_setup_fails(self):
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(installer, "BUILD", Path(temporary)), \
                patch.object(installer, "build_signature", return_value={"test": True}), \
                patch.object(installer, "check_prerequisites", side_effect=ValueError("Missing ninja")), \
                patch.object(installer, "download_archive") as download:
            with self.assertRaisesRegex(ValueError, "Missing ninja"):
                installer.build_hy3()
            download.assert_not_called()
            self.assertFalse((Path(temporary) / "signature.json").exists())


if __name__ == "__main__":
    unittest.main()
