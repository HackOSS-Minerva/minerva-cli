import tempfile
import unittest
from pathlib import Path

from helpers import DESCRIPTIONS, END, SCHEDULES, START, response, write_csv
from minerva_cli.tenants import parse_tenants


class TenantCsvTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "responses.csv"

    def parse(self, **overrides):
        return parse_tenants(write_csv(self.path, [response(**overrides)]))

    def test_complete_config_and_all_description_mappings(self):
        tenant = self.parse()[0]
        self.assertEqual(tenant.slug, "example-hack")
        self.assertEqual(tenant.config, {
            "slug": "example-hack", "name": "Example Hack",
            "domain": "https://example.org", "email": "team@example.org",
            "discord": "", "instagram": "", "linkedin": "", "devpost": "",
            "heart": "", "logo": "https://example.org/logo.png",
            "calendarid": "example@group.calendar.google.com",
            "event": {"name": "Example Hack 2026", "startTime": START,
                      "endTime": END, "deadline": "2026-11-21T19:00:00-08:00",
                      "gitCommitGraceWindowMinutes": 15},
            "locks": {
                "forms": {key: [START, END] for key in (
                    "participant", "judge", "speaker", "superadmin", "volunteer",
                    "submission", "feedback")},
                "judge": {key: [START, END] for key in (
                    "assignments", "submissions", "orientation", "certificate")},
                "sponsor": {key: [START, END] for key in (
                    "resume-book", "team-projects", "analytics")},
                "live": {"checkin": [START, END], "teams": [START, END]},
            },
        })
        expected_files = (
            "participants.mdx", "judges.mdx", "speakers.mdx", "superadmins.mdx",
            "volunteers.mdx", "feedback.mdx", "submission.mdx", "rules.mdx",
            "venue.mdx", "code-of-conduct.mdx", "judge-orientation.mdx",
        )
        answers = {title: f"Content {index}\r\n  indentation\r" for index, title in
                   enumerate(DESCRIPTIONS)}
        tenant = self.parse(**answers)[0]
        self.assertEqual(tenant.descriptions, {
            filename: f"Content {index}\r\n  indentation\r"
            for index, filename in enumerate(expected_files)
        })

    def test_quoted_multiline_description_is_not_normalized(self):
        value = '  # Title\r\n\r\n"hello, tenant"\r\n\r\n'
        tenant = self.parse(**{"Participant registration introduction": value})[0]
        self.assertEqual(tenant.descriptions["participants.mdx"], value)

    def test_bom_reordered_headers_and_header_whitespace(self):
        row = response()
        headers = list(reversed(row))
        values = [[row[header] for header in headers]]
        write_csv(self.path, values, [f" {header} " for header in headers], bom=True)
        self.assertEqual(parse_tenants(self.path)[0].slug, "example-hack")

    def test_timestamp_is_optional_and_ignored(self):
        headers = [key for key in response() if key != "Timestamp"]
        self.assertEqual(len(parse_tenants(write_csv(self.path, headers=headers))), 1)

    def test_empty_rows_skipped_and_entire_sheet_processed(self):
        rows = [[], ["  "] * 61, list(response().values()), [],
                list(response(**{"Tenant ID": "second-hack"}).values())]
        tenants = parse_tenants(write_csv(self.path, rows))
        self.assertEqual([tenant.slug for tenant in tenants], ["example-hack", "second-hack"])

    def test_header_only_sheet_is_empty(self):
        self.assertEqual(parse_tenants(write_csv(self.path, [])), [])

    def test_invalid_headers_rejected(self):
        headers = list(response())
        for invalid in ([], headers[:-1], headers + ["Unexpected"],
                        headers + [" Tenant ID "], headers + ["Timestamp"]):
            with self.subTest(headers=invalid):
                write_csv(self.path, [], invalid)
                with self.assertRaises(ValueError):
                    parse_tenants(self.path)

    def test_wrong_record_width_rejected(self):
        row = list(response().values())
        for invalid in (row[:-1], row + ["extra"]):
            with self.subTest(width=len(invalid)):
                with self.assertRaisesRegex(ValueError, "row 2"):
                    parse_tenants(write_csv(self.path, [invalid]))

    def test_malformed_csv_quotes_rejected(self):
        write_csv(self.path, [])
        with self.path.open("a") as stream:
            stream.write('"unterminated')
        with self.assertRaisesRegex(ValueError, "row 2"):
            parse_tenants(self.path)

    def test_duplicate_slug_rejected_after_trimming(self):
        rows = [response(), response(**{"Tenant ID": " example-hack "})]
        with self.assertRaisesRegex(ValueError, "row 3.*Tenant ID"):
            parse_tenants(write_csv(self.path, rows))

    def test_required_answers_and_each_schedule_endpoint(self):
        required = ["Tenant ID", "Organization name", "Website URL", "Contact email",
                    "Logo URL", "Google Calendar ID", "Event name", "Event start",
                    "Event end", "Submission deadline"]
        required += [title + suffix for title in SCHEDULES for suffix in (" opens", " closes")]
        for title in required:
            with self.subTest(title=title):
                with self.assertRaisesRegex(ValueError, "row 2") as error:
                    self.parse(**{title: "  "})
                self.assertIn(title, str(error.exception))

    def test_partially_filled_row_not_ignored(self):
        with self.assertRaises(ValueError):
            parse_tenants(write_csv(self.path, [{"Timestamp": "today"}]))

    def test_invalid_slugs(self):
        for slug in ("../outside", "Uppercase", "a_b", "a--b", "-a", "a-", "é"):
            with self.subTest(slug=slug), self.assertRaisesRegex(ValueError, "Tenant ID"):
                self.parse(**{"Tenant ID": slug})

    def test_optional_blanks_and_optional_values(self):
        tenant = self.parse(**{"Git commit grace period (minutes)": "",
                               **{title: "" for title in DESCRIPTIONS}})[0]
        self.assertNotIn("gitCommitGraceWindowMinutes", tenant.config["event"])
        self.assertNotIn("openOffset", tenant.config["event"])
        self.assertTrue(all(value == "" for value in tenant.descriptions.values()))
        tenant = self.parse(**{"Registration opening override (advanced)": " -2d ",
                               "Organization name": " Example ",
                               "Brand heart or symbol": " ♥ "})[0]
        self.assertEqual(tenant.config["event"]["openOffset"], "-2d")
        self.assertEqual(tenant.config["name"], "Example")
        self.assertEqual(tenant.config["heart"], "♥")

    def test_grace_boundaries_and_invalid_integers(self):
        for value in ("0", "1440"):
            self.assertEqual(self.parse(**{"Git commit grace period (minutes)": value})[0]
                             .config["event"]["gitCommitGraceWindowMinutes"], int(value))
        for value in ("-1", "1441", "1.5", "01", "1e2", "+1", "NaN", "١", "9" * 5000):
            with self.subTest(value=value[:20]), self.assertRaisesRegex(ValueError, "grace period"):
                self.parse(**{"Git commit grace period (minutes)": value})

    def test_timestamp_format_and_timezone_preserved(self):
        for value in ("2026-11-21T08:00Z", "2026-11-21T08:00:00+08:00",
                      "2026-11-21T08:00:00.123Z"):
            self.assertEqual(self.parse(**{"Event start": value})[0].config["event"]["startTime"], value)
        for value in ("2026-11-21", "2026-11-21T08:00:00", "2026-02-30T08:00:00Z",
                      "2026-11-21T08:00:00+0800", "2026-11-21 08:00:00Z",
                      "2026-11-21T24:00:00Z"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Event start"):
                self.parse(**{"Event start": value})

    def test_event_and_deadline_ranges(self):
        for overrides in ({"Event end": START}, {"Event end": "2026-11-20T08:00:00Z"},
                          {"Submission deadline": "2026-11-20T08:00:00Z"}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.parse(**overrides)
        self.parse(**{"Submission deadline": START})
        self.parse(**{"Submission deadline": "2026-11-25T08:00:00Z"})

    def test_invalid_timezone_components_are_not_normalized(self):
        for offset in ("+08:99", "+00:60", "-00:99", "+24:00"):
            for title in ("Event start", "Participant registration opens"):
                with self.subTest(offset=offset, title=title), self.assertRaisesRegex(ValueError, title):
                    self.parse(**{title: "2026-11-21T08:00:00" + offset})

    def test_every_schedule_range_is_checked(self):
        for title in SCHEDULES:
            with self.subTest(title=title), self.assertRaises(ValueError):
                self.parse(**{title + " closes": START})

    def test_url_compatibility_cases_on_every_link_field(self):
        # Recorded from the existing Zod validator; controls deliberately tightened.
        cases = {
            "https://example.org/path?q=1#section": True,
            "http://localhost:3000": True, "mailto:team@example.org": True,
            "ftp://example.org/file": True, "example.org": False,
            "https://": False, "https://exa mple.org": False,
            "https://example.org/a b": True, "https://exa\nmple.org": False,
            "https://example.org:bad": False, "https://example.org:99999": False,
            "http:example.org": True, "https:///example.org": True,
            "custom:value": True, "mailto:": True,
            "https://user:pass@example.org": True, "https://[::1]:3000": True,
            "https://éxample.org": True,
        }
        for field in ("Website URL", "Logo URL", "Discord invite URL", "Instagram URL",
                      "LinkedIn URL", "Devpost event URL"):
            for value, accepted in cases.items():
                with self.subTest(field=field, value=value):
                    if accepted:
                        self.parse(**{field: value})
                    else:
                        with self.assertRaises(ValueError):
                            self.parse(**{field: value})

    def test_embedded_url_controls_rejected(self):
        for control in ("\x00", "\t", "\n", "\r", "\x1f", "\x7f", "\x85"):
            with self.subTest(control=repr(control)), self.assertRaises(ValueError):
                self.parse(**{"Website URL": "https://example.org/a" + control + "b"})

    def test_email_compatibility_cases(self):
        cases = {"team+event@example.org": True, "team@sub.example.org": True,
                 "team@": False, "@example.org": False, "a..b@example.org": False,
                 '"team"@example.org': False, "équipe@example.org": False}
        for value, accepted in cases.items():
            with self.subTest(value=value):
                if accepted:
                    self.assertEqual(self.parse(**{"Contact email": value})[0].config["email"], value)
                else:
                    with self.assertRaisesRegex(ValueError, "Contact email"):
                        self.parse(**{"Contact email": value})


if __name__ == "__main__":
    unittest.main()
