"""Tests for the five responsibilities. Standard library `unittest` — no test runner to install.

    python3 -m unittest discover -s helios/tests -t .
"""

from __future__ import annotations

import contextlib
import csv
import io
import tempfile
import unittest
from datetime import date
from pathlib import Path

from helios import __main__, export, mapping, reference, spec, validation

VALID = {
    "reviewId": "AREV-31",
    "title": "SS1/23 model risk tested for AI/ML credibility",
    "reviewType": "Core - Externally mandated",
    "reviewCategory": "Global",
    "assuranceFunction": "Traded Risk Assurance",
    "reviewLead": "45012345",
    "reviewTeam": "Global",
    "targetStart": "2027-03-18",
    "scopeRationale": "Assess the credibility of SS1/23 model risk coverage over AI/ML.",
}


class RequiredFields(unittest.TestCase):
    def test_a_complete_row_has_no_errors(self):
        _, errors = validation.prepare_row(VALID)
        self.assertEqual(errors, [])

    def test_each_missing_required_field_is_reported_by_label(self):
        clean, errors = validation.prepare_row({})
        reported = {e.field for e in errors if e.code == "required"}
        self.assertEqual(reported, set(spec.REQUIRED))
        self.assertIn("Review Lead (Staff ID) is required.", [e.message for e in errors])
        self.assertEqual(clean["title"], "")

    def test_whitespace_only_does_not_satisfy_a_required_field(self):
        _, errors = validation.prepare_row({**VALID, "reviewLead": "   "})
        self.assertEqual([e.field for e in errors], ["reviewLead"])

    def test_errors_are_reported_in_column_order(self):
        def column(key: str) -> int:
            return spec.HEADER.index(spec.BY_KEY[key].label)

        _, errors = validation.prepare_row({"reviewLead": "45012345"})
        fields = [e.field for e in errors]
        self.assertEqual(fields, sorted(fields, key=column))


class ReferenceNormalisation(unittest.TestCase):
    def test_casing_and_spacing_are_normalised(self):
        value, ok = reference.normalise("  traded   RISK assurance ", spec.ASSURANCE_FUNCTIONS)
        self.assertTrue(ok)
        self.assertEqual(value, "Traded Risk Assurance")

    def test_a_hyphen_matches_the_reference_lists_em_dash(self):
        value, ok = reference.normalise("CIB - Global Banking", reference.BUSINESSES)
        self.assertTrue(ok)
        self.assertEqual(value, "CIB — Global Banking")

    def test_common_planning_side_aliases_resolve(self):
        for raw, expected in [("United Kingdom", "UK"), ("US", "USA"), ("HK", "Hong Kong")]:
            value, ok = reference.normalise(raw, reference.LOCATIONS)
            self.assertTrue(ok, raw)
            self.assertEqual(value, expected)

    def test_multi_value_locations_are_split_deduped_and_rejoined(self):
        joined, unknown = reference.normalise_many("uk, UK; Hong Kong ;;", reference.LOCATIONS)
        self.assertEqual(joined, "UK; Hong Kong")
        self.assertEqual(unknown, [])

    def test_normalisation_happens_before_the_required_check(self):
        clean, errors = validation.prepare_row({**VALID, "business": "iwpb - wealth"})
        self.assertEqual(clean["business"], "IWPB — Wealth")
        self.assertEqual(errors, [])

    def test_an_empty_optional_reference_field_is_not_an_error(self):
        _, errors = validation.prepare_row({**VALID, "business": "", "location": ""})
        self.assertEqual(errors, [])


class ExplicitRejection(unittest.TestCase):
    def test_an_off_list_value_is_rejected_but_left_on_screen_to_be_fixed(self):
        clean, errors = validation.prepare_row({**VALID, "assuranceFunction": "Made Up Assurance"})
        self.assertEqual([e.code for e in errors], ["unknown_value"])
        self.assertEqual(clean["assuranceFunction"], "Made Up Assurance")

    def test_an_off_list_value_never_reaches_the_csv(self):
        result = export.build([{**VALID, "assuranceFunction": "Made Up Assurance"}])
        self.assertFalse(result.ok)
        self.assertEqual(result.csv, "")

    def test_an_unknown_location_is_kept_alongside_the_ones_that_resolved(self):
        clean, errors = validation.prepare_row({**VALID, "location": "uk; Atlantis"})
        self.assertEqual(clean["location"], "UK; Atlantis")
        self.assertEqual([e.code for e in errors], ["unknown_value"])

    def test_a_near_miss_is_suggested(self):
        _, errors = validation.prepare_row({**VALID, "reviewTeam": "Hong Kong"})
        self.assertIn("Did you mean 'Hong Kong (FC)'?", errors[0].message)

    def test_an_unrecognised_value_with_no_near_miss_lists_the_allowed_values(self):
        _, errors = validation.prepare_row({**VALID, "esgFlag": "maybe"})
        self.assertIn("Allowed: 'Yes', 'No'", errors[0].message)

    def test_each_unknown_location_is_named_individually(self):
        _, errors = validation.prepare_row({**VALID, "location": "UK; Atlantis; Narnia"})
        self.assertEqual([e.code for e in errors], ["unknown_value", "unknown_value"])
        self.assertIn("'Atlantis'", errors[0].message)
        self.assertIn("'Narnia'", errors[1].message)

    def test_an_unparseable_date_is_rejected_with_the_accepted_formats(self):
        _, errors = validation.prepare_row({**VALID, "targetStart": "sometime next spring"})
        self.assertEqual(errors[0].code, "bad_date")
        self.assertIn("YYYY-MM-DD", errors[0].message)

    def test_errors_carry_the_row_number_the_user_sees(self):
        prepared = validation.prepare([VALID, {}, VALID])
        self.assertEqual({e.row for e in prepared.errors}, {2})
        self.assertEqual(prepared.errors_for(1), [])


class DerivedFields(unittest.TestCase):
    def test_quarter_and_year_follow_the_target_start_date(self):
        clean, _ = validation.prepare_row({**VALID, "targetStart": "2027-11-02"})
        self.assertEqual(clean["planQuarter"], "Q4")
        self.assertEqual(clean["iapQuarter"], "Q4")
        self.assertEqual(clean["planYear"], "2027")
        self.assertEqual(clean["iapYear"], "2027")

    def test_a_supplied_derived_value_is_discarded_not_trusted(self):
        clean, _ = validation.prepare_row({**VALID, "planQuarter": "Q1", "planYear": "1999"})
        self.assertEqual(clean["planQuarter"], "Q1")  # Q1 is correct for 18 Mar
        self.assertEqual(clean["planYear"], "2027")   # the supplied 1999 is ignored

    def test_no_target_start_leaves_the_derived_fields_empty(self):
        clean, _ = validation.prepare_row({k: v for k, v in VALID.items() if k != "targetStart"})
        self.assertEqual([clean[k] for k in spec.DERIVED], ["", "", "", ""])

    def test_free_text_dates_are_parsed(self):
        for raw, expected in [
            ("18 Mar 2027", date(2027, 3, 18)),
            ("Sep 2026", date(2026, 9, 1)),
            ("01/01/2027", date(2027, 1, 1)),
            ("2027-06-30", date(2027, 6, 30)),
        ]:
            self.assertEqual(spec.parse_date(raw).value, expected, raw)

    def test_an_impossible_date_is_not_coerced(self):
        self.assertFalse(spec.parse_date("31 Feb 2027").ok)


class Mapping(unittest.TestCase):
    def test_a_mandated_review_maps_to_its_helios_defaults(self):
        row = mapping.to_helios({
            "ref": "4.1",
            "title": "New incident reporting regime",
            "team": "Regulatory Reporting Assurance",
            "sub-team": "UK (RC)",
            "go-live": "18 Mar 2027",
            "mandated": "yes",
        })
        self.assertEqual(row["reviewId"], "AREV-41")
        self.assertEqual(row["reviewType"], "Core - Externally mandated")
        self.assertEqual(row["assuranceFunction"], "Regulatory Reporting Assurance")
        self.assertEqual(row["reviewTeam"], "UK (RC)")
        self.assertEqual(row["status"], "Planned")
        self.assertEqual(row["riskFlags"], "NA")
        self.assertEqual(row["esgFlag"], "No")

    def test_a_non_mandated_review_defaults_to_additional(self):
        row = mapping.to_helios({"ref": "3.2", "title": "Agentic AI in payments"})
        self.assertEqual(row["reviewType"], "Additional")
        self.assertEqual(row["targetStart"], "")

    def test_one_rationale_populates_both_narrative_columns(self):
        row = mapping.to_helios({"ref": "3.2", "rationale": "Coverage gap on agentic AI."})
        self.assertEqual(row["reviewDetail"], "Coverage gap on agentic AI.")
        self.assertEqual(row["scopeRationale"], "Coverage gap on agentic AI.")

    def test_an_existing_lookup_key_is_left_alone(self):
        self.assertEqual(mapping.to_helios({"ref": "AREV-99"})["reviewId"], "AREV-99")

    def test_planning_side_headers_are_recognised_on_import(self):
        text = (
            "ref,title,team,sub-team,business,location,go-live,mandated\n"
            "4.1,Incident reporting,Regulatory Reporting Assurance,UK (RC),"
            "CIB - Global Banking,UK; HK,18 Mar 2027,yes\n"
        )
        rows, ignored = mapping.from_csv(text)
        self.assertEqual(ignored, [])
        self.assertEqual(len(rows), 1)
        clean, _ = validation.prepare_row(rows[0])
        self.assertEqual(clean["business"], "CIB — Global Banking")
        self.assertEqual(clean["location"], "UK; Hong Kong")
        self.assertEqual(clean["targetStart"], "2027-03-18")

    def test_unrecognised_columns_are_reported_not_dropped_silently(self):
        rows, ignored = mapping.from_csv("ref,title,sme_days\n3.1,A review,45\n")
        self.assertEqual(ignored, ["sme_days"])
        self.assertEqual(len(rows), 1)

    def test_a_helios_file_round_trips(self):
        result = export.build([VALID])
        rows, ignored = mapping.from_csv(result.csv)
        self.assertEqual(ignored, [])
        self.assertEqual(export.build(rows).csv, result.csv)

    def test_blank_rows_in_the_source_are_skipped(self):
        rows, _ = mapping.from_csv("ref,title\n3.1,A review\n,\n\n")
        self.assertEqual(len(rows), 1)


class CsvGeneration(unittest.TestCase):
    def test_the_header_is_the_spec_labels_in_spec_order(self):
        header = next(csv.reader(io.StringIO(export.build([VALID]).csv)))
        self.assertEqual(header, spec.HEADER)
        self.assertEqual(header[0], "Lookup Key (Review ID)")

    def test_every_row_has_one_cell_per_column(self):
        text = export.build([VALID, {**VALID, "reviewId": "AREV-32"}]).csv
        for row in csv.reader(io.StringIO(text)):
            self.assertEqual(len(row), len(spec.FIELDS))

    def test_commas_and_quotes_and_newlines_survive_a_round_trip(self):
        nasty = 'Scope: A, B and "C"\nsecond line'
        text = export.build([{**VALID, "scopeRationale": nasty}]).csv
        body = list(csv.reader(io.StringIO(text)))[1]
        self.assertEqual(body[spec.HEADER.index("Review Scope and Rationale")], nasty)

    def test_rows_are_crlf_terminated_and_fully_quoted(self):
        text = export.build([VALID]).csv
        self.assertTrue(text.endswith("\r\n"))
        self.assertTrue(text.startswith('"Lookup Key (Review ID)"'))

    def test_an_invalid_batch_produces_errors_and_no_file(self):
        result = export.build([VALID, {}])
        self.assertFalse(result.ok)
        self.assertEqual(result.csv, "")
        self.assertTrue(all(e.row == 2 for e in result.errors))

    def test_an_empty_batch_is_refused(self):
        result = export.build([])
        self.assertFalse(result.ok)
        self.assertEqual(result.errors[0].code, "empty")

    def test_the_filename_follows_the_plan_year(self):
        self.assertEqual(export.build([VALID]).filename, "2027_IAP_Helios_upload.csv")


class FilesAcrossPlatforms(unittest.TestCase):
    """The CSV has to survive the round trip on Windows as well as here."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name)
        self.source = (
            "ref,title,team,sub-team,category,lead,business,go-live,rationale\n"
            "5.1,Basel 3.1,Treasury Risk Assurance,Global,Global,45012345,"
            "Global Functions — Finance,1 Jan 2027,Capital model readiness.\n"
        )

        self.quiet = contextlib.redirect_stderr(io.StringIO())  # progress and error notes
        self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)

    def _write(self, name: str, encoding: str) -> Path:
        path = self.path / name
        path.write_bytes(self.source.encode(encoding))
        return path

    def test_excel_on_windows_saves_cp1252_and_it_still_reads(self):
        # "CSV (Comma delimited)" — Excel's default, and not UTF-8.
        rows, _ = mapping.from_csv(__main__.read_text(self._write("ansi.csv", "cp1252")))
        self.assertEqual(rows[0]["business"], "Global Functions — Finance")

    def test_excel_csv_utf8_carries_a_bom_and_it_still_reads(self):
        rows, _ = mapping.from_csv(__main__.read_text(self._write("bom.csv", "utf-8-sig")))
        self.assertEqual(rows[0]["reviewId"], "AREV-51")
        self.assertEqual(rows[0]["business"], "Global Functions — Finance")

    def test_plain_utf8_reads(self):
        rows, _ = mapping.from_csv(__main__.read_text(self._write("plain.csv", "utf-8")))
        self.assertEqual(rows[0]["business"], "Global Functions — Finance")

    def test_a_written_file_is_utf8_with_crlf_and_no_stray_carriage_returns(self):
        out = self.path / "out.csv"
        __main__.convert(self._write("in.csv", "utf-8"), out)
        raw = out.read_bytes()
        raw.decode("utf-8")  # raises if the platform encoding leaked in
        self.assertNotIn(b"\r\r\n", raw)
        self.assertEqual(raw.count(b"\r\n"), raw.count(b"\n"))

    def test_the_csv_is_utf8_on_stdout_whatever_the_console_encoding_is(self):
        # Stands in for a redirected stdout on Windows, where the console code page
        # would otherwise decide the file's encoding.
        buffer = io.BytesIO()
        stdout = io.TextIOWrapper(buffer, encoding="cp1252")
        with contextlib.redirect_stdout(stdout):
            __main__.convert(self._write("in.csv", "utf-8"), None)
        self.assertIn("Global Functions — Finance", buffer.getvalue().decode("utf-8"))

    def test_a_binary_file_is_refused_rather_than_mangled(self):
        path = self.path / "not.csv"
        path.write_bytes(b"\x81\x8d\x8f\x90\x9d\x00\xff")
        with self.assertRaises(SystemExit):
            __main__.read_text(path)


if __name__ == "__main__":
    unittest.main()
