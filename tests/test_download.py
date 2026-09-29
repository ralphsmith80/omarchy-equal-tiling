"""Exercise curl's transfer limits against a local HTTPS server."""

from contextlib import ExitStack
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import os
from pathlib import Path
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("installer", ROOT / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class DownloadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cert, key = cls.root / "cert.pem", cls.root / "key.pem"
        subprocess.run([
            "/usr/bin/openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(cert), "-days", "1",
            "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1",
        ], check=True, capture_output=True)
        cls.cert = cert

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                self.send_response(200)
                body = b"wrong archive" if self.path == "/corrupt" else b"verified archive"
                if self.path == "/oversized-length":
                    self.send_header("Content-Length", "1000000")
                elif self.path not in {"/oversized-stream", "/stall"}:
                    self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    if self.path == "/stall":
                        time.sleep(1)
                    elif self.path in {"/oversized-length", "/oversized-stream"}:
                        for _ in range(32):
                            self.wfile.write(b"x" * 4096)
                    else:
                        self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                    pass

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(cert, key)
        cls.server.socket = tls.wrap_socket(cls.server.socket, server_side=True)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.addClassCleanup(cls.server.server_close)
        cls.addClassCleanup(cls.thread.join)
        cls.addClassCleanup(cls.server.shutdown)

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.work = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.archive = self.work / "archive.tar.gz"
        self.env = installer.build_environment(self.work)
        self.route = "/valid"
        self.transfers = []
        real_run = subprocess.run

        def local_transfer(command, **kwargs):
            if "--output" in command:
                self.transfers.append(command)
                # Only redirect the endpoint and trust this test's certificate.
                # All production transfer limits and HTTPS restrictions remain.
                command = [*command[:-1], "--cacert", str(self.cert),
                           f"https://127.0.0.1:{self.server.server_port}{self.route}"]
            return real_run(command, **kwargs)

        self.stack.enter_context(patch.object(installer.subprocess, "run", side_effect=local_transfer))
        self.stack.enter_context(patch.object(installer, "ARCHIVE_SHA256", hashlib.sha256(b"verified archive").hexdigest()))
        self.stack.enter_context(patch.object(installer, "ARCHIVE_MAX_BYTES", 1024))

    def test_verified_download_ignores_user_curl_config_and_build_controls(self):
        (self.work / ".curlrc").write_text("proxy = http://127.0.0.1:1\n")
        with patch.dict(os.environ, {"PATH": "/missing", "LD_PRELOAD": "/missing.so",
                                    "CURL_HOME": str(self.work), "CMAKE_TOOLCHAIN_FILE": "/missing"}):
            installer.download_archive(self.archive, self.env)
        self.assertEqual(self.archive.read_bytes(), b"verified archive")

    def test_checksum_failure_removes_download(self):
        self.route = "/corrupt"
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            installer.download_archive(self.archive, self.env)
        self.assertFalse(self.archive.exists())

    def test_curl_rejects_oversized_response_with_or_without_content_length(self):
        for route in ("/oversized-length", "/oversized-stream"):
            with self.subTest(route=route):
                self.route = route
                with self.assertRaises(subprocess.CalledProcessError) as failure:
                    installer.download_archive(self.archive, self.env)
                self.assertEqual(failure.exception.returncode, 63)
                self.assertFalse(self.archive.exists())

    def test_stalled_transfer_hits_total_deadline(self):
        self.route = "/stall"
        with patch.object(installer, "DOWNLOAD_SECONDS", .2):
            started = time.monotonic()
            with self.assertRaises(subprocess.CalledProcessError) as failure:
                installer.download_archive(self.archive, self.env)
        self.assertEqual(failure.exception.returncode, 28)
        self.assertLess(time.monotonic() - started, 2)
        self.assertFalse(self.archive.exists())

    def test_curl_without_streaming_size_limit_is_rejected_before_download(self):
        with patch.object(installer.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 0, stdout="curl 8.3.0 (test)")):
            with self.assertRaisesRegex(ValueError, "curl 8.4.0"):
                installer.download_archive(self.archive, self.env)
        self.assertFalse(self.transfers)
        self.assertFalse(self.archive.exists())


if __name__ == "__main__":
    unittest.main()
