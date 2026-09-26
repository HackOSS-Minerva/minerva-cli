import json
import tempfile
import unittest
from pathlib import Path

from helpers import response, write_csv
from minerva_cli.generate import SyncPlan, apply_plan, build_plan
from minerva_cli.tenants import parse_tenants


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.repo = self.root / "repo"
        (self.repo / "tenants").mkdir(parents=True)
        self.tenant = self.input()

    def input(self, **overrides):
        return parse_tenants(write_csv(self.root / "input.csv", [response(**overrides)]))[0]

    def snapshot(self):
        return {path.relative_to(self.repo): path.read_bytes()
                for path in self.repo.rglob("*") if path.is_file()}

    def test_create_plan_is_pure_and_apply_is_repeatable(self):
        before = self.snapshot()
        plan = build_plan(self.repo, [self.tenant])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(plan.processed_slugs, ["example-hack"])
        self.assertEqual(len(plan.changes), 13)
        config_path = Path("tenants/example-hack/example-hack.json")
        self.assertEqual(json.loads(plan.changes[config_path]), self.tenant.config)
        self.assertTrue(plan.changes[config_path].endswith("\n"))
        apply_plan(self.repo, plan)
        self.assertEqual(build_plan(self.repo, [self.tenant]).changes, {})

    def test_authoritative_update_clears_values_without_touching_omitted_tenant(self):
        other = self.input(**{"Tenant ID": "other-hack"})
        apply_plan(self.repo, build_plan(self.repo, [self.tenant, other]))
        before = self.snapshot()
        updated = self.input(**{"Git commit grace period (minutes)": "",
                                "Participant registration introduction": ""})
        plan = build_plan(self.repo, [updated])
        self.assertEqual(set(plan.changes), {
            Path("tenants/example-hack/example-hack.json"),
            Path("tenants/example-hack/descriptions/participants.mdx"),
        })
        apply_plan(self.repo, plan)
        self.assertEqual((self.repo / "tenants/example-hack/descriptions/participants.mdx").read_bytes(), b"")
        config = json.loads((self.repo / "tenants/example-hack/example-hack.json").read_text())
        self.assertNotIn("gitCommitGraceWindowMinutes", config["event"])
        for path, content in before.items():
            if path not in plan.changes:
                self.assertEqual((self.repo / path).read_bytes(), content)

    def test_identical_json_keeps_existing_format_and_mtime(self):
        apply_plan(self.repo, build_plan(self.repo, [self.tenant]))
        path = self.repo / "tenants/example-hack/example-hack.json"
        content = json.dumps(self.tenant.config, separators=(",", ":")).encode()
        path.write_bytes(content)
        before = path.stat().st_mtime_ns
        plan = build_plan(self.repo, [self.tenant])
        self.assertEqual(plan.changes, {})
        apply_plan(self.repo, plan)
        self.assertEqual(path.read_bytes(), content)
        self.assertEqual(path.stat().st_mtime_ns, before)

    def test_mdx_normalization_preserves_meaningful_whitespace(self):
        for text, expected in (("", ""), ("\r\n", "\n"),
                               ('  # Hi\r\n\r\n"a,b"\r\n\r\n', '  # Hi\n\n"a,b"\n'),
                               ("  text  ", "  text  \n")):
            with self.subTest(text=text):
                tenant = self.input(**{"Participant registration introduction": text})
                plan = build_plan(self.repo, [tenant])
                self.assertEqual(plan.changes[Path("tenants/example-hack/descriptions/participants.mdx")], expected)

    def test_crlf_existing_mdx_is_compared_as_bytes(self):
        apply_plan(self.repo, build_plan(self.repo, [self.tenant]))
        path = self.repo / "tenants/example-hack/descriptions/participants.mdx"
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        self.assertIn(path.relative_to(self.repo), build_plan(self.repo, [self.tenant]).changes)

    def test_registry_is_sorted_and_contains_all_content_exports(self):
        second = self.input(**{"Tenant ID": "2nd-hack"})
        plan = build_plan(self.repo, [self.tenant, second])
        reverse = build_plan(self.repo, [second, self.tenant])
        self.assertEqual(plan.changes, reverse.changes)
        registry = plan.changes[Path("tenants/generated.ts")]
        self.assertIn('["2nd-hack", "example-hack"] as const', registry)
        self.assertIn('"2nd-hack": tenant_2nd_hack_config', registry)
        for key, suffix in (("participant", "participants"), ("judge", "judges"),
                            ("speaker", "speakers"), ("superadmin", "superadmins"),
                            ("volunteer", "volunteers"), ("feedback", "feedback"),
                            ("submission", "submission"), ("rules", "rules"),
                            ("venue", "venue"), ("codeOfConduct", "code_of_conduct"),
                            ("orientation", "judge_orientation")):
            self.assertIn(f"{key}: tenant_example_hack_{suffix}", registry)
        self.assertIn('@/tenants/example-hack/descriptions/code-of-conduct.mdx', registry)

    def test_registry_bootstrap_uses_existing_tenants_without_rewriting_them(self):
        apply_plan(self.repo, build_plan(self.repo, [self.tenant]))
        registry = self.repo / "tenants/generated.ts"
        expected = registry.read_bytes()
        registry.unlink()
        plan = build_plan(self.repo, [])
        self.assertEqual(set(plan.changes), {Path("tenants/generated.ts")})
        self.assertEqual(plan.changes[Path("tenants/generated.ts")].encode(), expected)

    def test_invalid_json_stops_before_any_writes(self):
        apply_plan(self.repo, build_plan(self.repo, [self.tenant]))
        path = self.repo / "tenants/example-hack/example-hack.json"
        path.write_text("{broken")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "example-hack.json"):
            build_plan(self.repo, [self.tenant])
        self.assertEqual(self.snapshot(), before)

    def test_missing_omitted_import_rejected_but_processed_file_repaired(self):
        apply_plan(self.repo, build_plan(self.repo, [self.tenant]))
        path = self.repo / "tenants/example-hack/descriptions/rules.mdx"
        path.unlink()
        with self.assertRaisesRegex(ValueError, "rules.mdx"):
            build_plan(self.repo, [])
        plan = build_plan(self.repo, [self.tenant])
        self.assertEqual(set(plan.changes), {path.relative_to(self.repo)})

    def test_invalid_existing_directory_rejected(self):
        (self.repo / "tenants/Bad_Name").mkdir()
        with self.assertRaises(ValueError):
            build_plan(self.repo, [self.tenant])

    def test_symlink_tenant_or_output_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        tenant_path = self.repo / "tenants/example-hack"
        tenant_path.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            build_plan(self.repo, [self.tenant])
        tenant_path.unlink()
        registry = self.repo / "tenants/generated.ts"
        registry.symlink_to(outside / "missing.ts")
        with self.assertRaises(ValueError):
            build_plan(self.repo, [self.tenant])
        self.assertEqual(list(outside.iterdir()), [])

    def test_symlinked_tenants_root_rejected(self):
        (self.repo / "tenants").rmdir()
        (self.root / "outside").mkdir()
        (self.repo / "tenants").symlink_to(self.root / "outside", target_is_directory=True)
        with self.assertRaises(ValueError):
            build_plan(self.repo, [self.tenant])

    def test_apply_checks_all_paths_before_writing(self):
        for bad in (Path("../outside"), self.root / "absolute", Path("README.md")):
            with self.subTest(path=bad):
                plan = SyncPlan([], {Path("tenants/generated.ts"): "new", bad: "unsafe"})
                with self.assertRaises(ValueError):
                    apply_plan(self.repo, plan)
                self.assertFalse((self.repo / "tenants/generated.ts").exists())

    def test_apply_rechecks_symlink_changed_after_planning(self):
        plan = build_plan(self.repo, [self.tenant])
        outside = self.root / "outside"
        outside.mkdir()
        (self.repo / "tenants/example-hack").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            apply_plan(self.repo, plan)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.repo / "tenants/generated.ts").exists())

    def test_invalid_input_slug_rejected_at_generation_boundary(self):
        self.tenant.slug = "../outside"
        with self.assertRaises(ValueError):
            build_plan(self.repo, [self.tenant])


if __name__ == "__main__":
    unittest.main()
