import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from openreview_downloader.cli import (
    collect_selected,
    compile_regexes,
    filter_selected,
    parse_decisions,
    print_selected,
    split_existing,
)


class CliSelectionTests(unittest.TestCase):
    def note(self, **overrides):
        defaults = {
            "id": "note-1",
            "number": 1,
            "content": {
                "venueid": {"value": "Test.cc/2026/Conference"},
                "venue": {"value": "Test 2026 poster"},
                "title": {"value": "Diffusion for Proteins"},
                "authors": {"value": ["Ada Lovelace", "Grace Hopper"]},
                "abstract": {
                    "value": "A graph diffusion method for protein design."
                },
                "pdf": {"value": "/pdf"},
            },
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def args(self, **overrides):
        defaults = {
            "venue_id": "Test.cc/2026/Conference",
            "decisions": ["accepted"],
            "search_terms": [],
            "regexes": [],
            "case_sensitive": False,
            "head": None,
            "format": "text",
            "list": True,
        }
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    def test_all_decision_expands_to_accepted_and_rejected(self):
        self.assertEqual(
            parse_decisions("oral,all,accepted"),
            ["oral", "accepted", "rejected"],
        )

    def test_search_and_regex_filter_selection(self):
        notes = [
            self.note(),
            self.note(
                id="note-2",
                number=2,
                content={
                    "venueid": {"value": "Test.cc/2026/Conference"},
                    "title": {"value": "Transformers Everywhere"},
                    "authors": {"value": ["Katherine Johnson"]},
                    "abstract": {"value": "Attention models."},
                    "pdf": {"value": "/pdf"},
                },
            ),
        ]
        selected = collect_selected(
            notes,
            [],
            "Test.cc/2026/Conference",
            ["accepted"],
            Path("/tmp/out"),
        )
        args = self.args(
            search_terms=["diffusion"],
            regexes=compile_regexes(["protein(s)?"], False),
        )

        filtered = filter_selected(selected, args)

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0][0].id, "note-1")
        self.assertGreaterEqual(filtered[0][3]["hit_count"], 2)

    def test_split_existing_respects_skip_existing(self):
        note = self.note()
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "accepted" / "paper.pdf"
            path.parent.mkdir()
            path.write_bytes(b"%PDF")
            selected = [(note, "accepted", path, None)]

            to_download, existing = split_existing(selected, True)

        self.assertEqual(to_download, [])
        self.assertEqual(existing, 1)

    def test_jsonl_output_starts_with_summary(self):
        note = self.note()
        selected = [(note, "accepted", Path("/tmp/out/accepted/paper.pdf"), None)]
        args = self.args(format="jsonl", head=1)
        output = io.StringIO()

        with redirect_stdout(output):
            print_selected(selected, total_before_head=10, args=args)

        first_line = output.getvalue().splitlines()[0]
        summary = json.loads(first_line)
        self.assertEqual(summary["type"], "summary")
        self.assertEqual(summary["matched_papers"], 10)
        self.assertEqual(summary["shown_papers"], 1)


if __name__ == "__main__":
    unittest.main()
