import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import git_environment, git_fixture, local_git, write_csv
from minerva_cli.__main__ import main
from minerva_cli.generate import SyncPlan, apply_plan, build_plan
from minerva_cli.git import preflight, publish, validate_checkout
from minerva_cli.tenants import parse_tenants


class GitTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        environment = patch.dict(os.environ, git_environment(self.root), clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.repo, self.remote = git_fixture(self.root)
        self.real_run = subprocess.run
        self.gh_calls = []
        self.body = ""
        self.fail_stage = None
        self.plan = SyncPlan(["example-hack"], {Path("tenants/generated.ts"): "// updated\n"})

    def run_command(self, args, **kwargs):
        stage = args[1] if args[0] == "git" else " ".join(args[:3])
        if stage == self.fail_stage:
            raise subprocess.CalledProcessError(1, args, stderr="simulated failure")
        if args[0] == "gh":
            self.gh_calls.append((args, kwargs["cwd"]))
            if tuple(args[1:3]) == ("pr", "create"):
                self.body = Path(args[args.index("--body-file") + 1]).read_text()
                return subprocess.CompletedProcess(args, 0, "https://github.com/example/minerva/pull/1\n", "")
            return subprocess.CompletedProcess(args, 0, "", "")
        return self.real_run(args, **kwargs)

    def test_preflight_accepts_clean_current_base_without_changing_identity(self):
        before = local_git(self.repo, "config", "--local", "--list")
        with patch("minerva_cli.git.subprocess.run", side_effect=self.run_command):
            validate_checkout(self.repo)
            preflight(self.repo)
        self.assertEqual(local_git(self.repo, "config", "--local", "--list"), before)
        self.assertEqual(local_git(self.repo, "status", "--porcelain"), "")

    def test_preflight_rejects_dirty_tracked_and_untracked_files(self):
        for name in ("package.json", "untracked.txt"):
            with self.subTest(name=name):
                path = self.repo / name
                previous = path.read_bytes() if path.exists() else None
                path.write_text("dirty")
                with patch("minerva_cli.git.subprocess.run", side_effect=self.run_command):
                    with self.assertRaisesRegex(RuntimeError, "clean"):
                        preflight(self.repo)
                if previous is None:
                    path.unlink()
                else:
                    path.write_bytes(previous)
        self.assertEqual(self.gh_calls, [])

    def test_preflight_rejects_wrong_branch_and_invalid_base(self):
        local_git(self.repo, "switch", "-c", "feature")
        with self.assertRaisesRegex(RuntimeError, "main"):
            preflight(self.repo)
        for base in ("--help", "main~1", "main:other", "../main"):
            with self.subTest(base=base), self.assertRaises(RuntimeError):
                preflight(self.repo, base)

    def test_preflight_rejects_stale_base_without_moving_head(self):
        before = local_git(self.repo, "rev-parse", "HEAD")
        other = self.root / "other"
        local_git(self.root, "clone", str(self.remote), str(other))
        local_git(other, "commit", "--allow-empty", "-m", "advance")
        local_git(other, "push", "origin", "main")
        with self.assertRaisesRegex(RuntimeError, "up.to.date"):
            preflight(self.repo)
        self.assertEqual(local_git(self.repo, "rev-parse", "HEAD"), before)

    def test_preflight_rejects_missing_identity_and_auth(self):
        local_git(self.repo, "config", "--unset", "user.email")
        with self.assertRaisesRegex(RuntimeError, "identity"):
            preflight(self.repo)
        local_git(self.repo, "config", "user.email", "operator@example.org")
        self.fail_stage = "gh auth status"
        with patch("minerva_cli.git.subprocess.run", side_effect=self.run_command):
            with self.assertRaisesRegex(RuntimeError, "authentication"):
                preflight(self.repo)

    def test_checkout_requires_root_and_registry_integration(self):
        with self.assertRaises(RuntimeError):
            validate_checkout(self.repo / "tenants")
        (self.repo / "hooks/get-tenant.ts").write_text("export const tenantSlugs = [];\n")
        with self.assertRaisesRegex(RuntimeError, "integration"):
            validate_checkout(self.repo)

    def test_publish_commits_exact_paths_and_creates_draft_on_selected_base(self):
        local_git(self.repo, "switch", "-c", "integration")
        local_git(self.repo, "push", "origin", "integration")
        with patch("minerva_cli.git.subprocess.run", side_effect=self.run_command):
            preflight(self.repo, "integration")
            url = publish(self.repo, self.plan, "integration", draft=True)
        branch = local_git(self.repo, "branch", "--show-current")
        self.assertRegex(branch, r"^tenant-sync/\d{8}T\d{12}Z$")
        self.assertEqual(local_git(self.repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"), "tenants/generated.ts")
        self.assertEqual(local_git(self.repo, "log", "-1", "--format=%an <%ae>"), "Test Operator <operator@example.org>")
        self.assertIn(branch, local_git(self.remote, "branch", "--list"))
        args, cwd = self.gh_calls[-1]
        self.assertEqual(cwd, self.repo)
        self.assertEqual(args[args.index("--base") + 1], "integration")
        self.assertEqual(args[args.index("--head") + 1], branch)
        self.assertIn("--repo", args)
        self.assertEqual(args[args.index("--repo") + 1], str(self.remote).removesuffix(".git"))
        self.assertIn("--draft", args)
        self.assertTrue(url.endswith("/pull/1"))
        self.assertIn("example-hack", self.body)
        for section in ("Context", "Core Changes", "Testing & Verification", "Impact & Edge Cases"):
            self.assertIn("### " + section, self.body)
        self.assertFalse(Path(args[args.index("--body-file") + 1]).exists())

    def test_noop_does_not_run_git_or_gh(self):
        with patch("minerva_cli.git.subprocess.run", side_effect=AssertionError("unexpected command")):
            self.assertEqual(publish(self.repo, SyncPlan([], {})), "")

    def test_full_cli_generates_commits_and_pushes_only_to_local_remote(self):
        csv_path = write_csv(self.root / "responses.csv")
        output = io.StringIO()
        with patch("minerva_cli.git.subprocess.run", side_effect=self.run_command), \
             contextlib.redirect_stdout(output):
            result = main(["tenants", "sync", str(csv_path), "--repo", str(self.repo), "--draft"])
        self.assertEqual(result, 0, output.getvalue())
        paths = local_git(self.repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines()
        self.assertEqual(len(paths), 12)
        self.assertTrue(all(path.startswith("tenants/") for path in paths))
        self.assertEqual(build_plan(self.repo, parse_tenants(csv_path)).changes, {})
        self.assertIn("https://github.com/example/minerva/pull/1", output.getvalue())

    def test_full_cli_noop_on_clean_current_base_creates_nothing(self):
        csv_path = write_csv(self.root / "responses.csv")
        apply_plan(self.repo, build_plan(self.repo, parse_tenants(csv_path)))
        local_git(self.repo, "add", "tenants")
        local_git(self.repo, "commit", "-m", "existing configuration")
        local_git(self.repo, "push", "origin", "main")
        before = local_git(self.repo, "show-ref")
        with patch("minerva_cli.git.subprocess.run", side_effect=self.run_command), \
             contextlib.redirect_stdout(io.StringIO()):
            result = main(["tenants", "sync", str(csv_path), "--repo", str(self.repo)])
        self.assertEqual(result, 0)
        self.assertEqual(local_git(self.repo, "show-ref"), before)
        self.assertEqual(len(self.gh_calls), 1)
        self.assertEqual(tuple(self.gh_calls[0][0]), ("gh", "auth", "status"))

    def test_write_failure_preserves_branch_without_committing(self):
        head = local_git(self.repo, "rev-parse", "HEAD")
        with patch("minerva_cli.git.subprocess.run", side_effect=self.run_command), \
             patch("minerva_cli.git.apply_plan", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(RuntimeError, "write.*tenant-sync/"):
                publish(self.repo, self.plan)
        self.assertEqual(local_git(self.repo, "rev-parse", "HEAD"), head)
        self.assertEqual(self.gh_calls, [])

    def test_publish_failures_stop_and_report_preserved_branch(self):
        # Each case has a fresh checkout so a prior failure cannot mask behavior.
        for stage, label in (("switch", "branch"), ("commit", "commit"),
                             ("push", "push"), ("gh pr create", "PR")):
            with self.subTest(stage=stage):
                case = self.root / label
                case.mkdir()
                self.repo, self.remote = git_fixture(case)
                self.gh_calls.clear()
                self.fail_stage = stage
                with patch("minerva_cli.git.subprocess.run", side_effect=self.run_command):
                    with self.assertRaisesRegex(RuntimeError, label) as error:
                        publish(self.repo, self.plan)
                if stage != "switch":
                    self.assertIn("tenant-sync/", str(error.exception))
                if stage == "gh pr create":
                    self.assertIn("pushed", str(error.exception))
                    self.assertIn("tenant-sync/", local_git(self.remote, "branch", "--list"))
                else:
                    self.assertEqual(self.gh_calls, [])
