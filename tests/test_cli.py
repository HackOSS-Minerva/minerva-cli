import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import git_environment, git_fixture, local_git, write_csv
from minerva_cli.__main__ import main
from minerva_cli.generate import apply_plan, build_plan
from minerva_cli.tenants import parse_tenants


class CliTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        environment = patch.dict(os.environ, git_environment(self.root), clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.repo, self.remote = git_fixture(self.root)
        self.csv = write_csv(self.root / "response data.csv")

    def invoke(self, *flags):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = main(["tenants", "sync", str(self.csv), "--repo", str(self.repo), *flags])
        return result, output.getvalue()

    def test_dry_run_lists_paths_without_network_or_mutation(self):
        before = {p.relative_to(self.repo): p.read_bytes() for p in self.repo.rglob("*") if p.is_file()}
        with patch("minerva_cli.__main__.preflight", side_effect=AssertionError("preflight")), \
             patch("minerva_cli.__main__.publish", side_effect=AssertionError("publish")):
            result, output = self.invoke("--dry-run")
        self.assertEqual(result, 0, output)
        self.assertIn("example-hack", output)
        self.assertIn("tenants/example-hack/descriptions/participants.mdx", output)
        after = {p.relative_to(self.repo): p.read_bytes() for p in self.repo.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_invalid_csv_stops_before_git_calls(self):
        self.csv.write_text("wrong,headers\n")
        with patch("subprocess.run", side_effect=AssertionError("unexpected subprocess")):
            result, output = self.invoke()
        self.assertEqual(result, 1)
        self.assertIn("headers", output)

    def test_missing_repo_integration_is_actionable(self):
        (self.repo / "tenants/generated.ts").unlink()
        result, output = self.invoke("--dry-run")
        self.assertEqual(result, 1)
        self.assertIn("integration", output)

    def test_normal_noop_does_not_publish(self):
        apply_plan(self.repo, build_plan(self.repo, parse_tenants(self.csv)))
        with patch("minerva_cli.__main__.preflight"), \
             patch("minerva_cli.__main__.publish", side_effect=AssertionError("unexpected publish")):
            result, output = self.invoke()
        self.assertEqual(result, 0, output)
        self.assertIn("No changes", output)

    def test_csv_path_is_relative_to_operator_directory(self):
        with contextlib.chdir(self.root):
            self.csv = Path("response data.csv")
            result, output = self.invoke("--dry-run")
        self.assertEqual(result, 0, output)

    def test_publication_error_returns_nonzero(self):
        with patch("minerva_cli.__main__.preflight"), \
             patch("minerva_cli.__main__.publish", side_effect=RuntimeError("PR failed; branch preserved")):
            result, output = self.invoke()
        self.assertEqual(result, 1)
        self.assertIn("PR failed", output)

    def test_preflight_failure_does_not_change_checkout(self):
        head = local_git(self.repo, "rev-parse", "HEAD")
        with patch("minerva_cli.__main__.preflight", side_effect=RuntimeError("stale base")):
            result, output = self.invoke()
        self.assertEqual(result, 1)
        self.assertEqual(local_git(self.repo, "rev-parse", "HEAD"), head)
        self.assertEqual(local_git(self.repo, "status", "--porcelain"), "")
