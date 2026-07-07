import argparse
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openreview_downloader.cli import (
    auth_main,
    clear_saved_credentials,
    collect_selected,
    compile_regexes,
    filter_selected,
    load_saved_credentials,
    parse_decisions,
    print_selected,
    resolve_credentials,
    save_credentials,
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


class CliAuthTests(unittest.TestCase):
    def test_environment_credentials_take_precedence(self):
        env = {
            "OPENREVIEW_USERNAME": "env@example.com",
            "OPENREVIEW_PASSWORD": "env-password",
        }

        with patch.dict(os.environ, env, clear=False):
            username, password, source = resolve_credentials(allow_prompt=False)

        self.assertEqual(username, "env@example.com")
        self.assertEqual(password, "env-password")
        self.assertEqual(source, "environment")

    def test_credentials_prompt_when_not_configured(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            auth_file = Path(tmp_dir) / "auth.json"
            fake_stdin = SimpleNamespace(
                isatty=lambda: True,
                readline=lambda: "prompt@example.com\n",
            )
            with patch.dict(
                os.environ,
                {
                    "ORDL_AUTH_FILE": str(auth_file),
                    "OPENREVIEW_USERNAME": "",
                    "OPENREVIEW_PASSWORD": "",
                },
            ):
                with patch("sys.stdin", fake_stdin):
                    with patch("sys.stderr", io.StringIO()):
                        with patch(
                            "getpass.getpass",
                            return_value="prompt-password",
                        ):
                            username, password, source = resolve_credentials()

        self.assertEqual(username, "prompt@example.com")
        self.assertEqual(password, "prompt-password")
        self.assertEqual(source, "prompt")

    def test_saved_credentials_round_trip_without_keyring(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            auth_file = Path(tmp_dir) / "auth.json"
            with patch.dict(os.environ, {"ORDL_AUTH_FILE": str(auth_file)}):
                with patch("openreview_downloader.cli.load_keyring", return_value=None):
                    storage = save_credentials("saved@example.com", "secret")
                    username, password, source = load_saved_credentials()
                    removed = clear_saved_credentials()

        self.assertEqual(storage, "file")
        self.assertEqual(username, "saved@example.com")
        self.assertEqual(password, "secret")
        self.assertEqual(source, "file")
        self.assertTrue(removed)
        self.assertFalse(auth_file.exists())

    def test_auth_status_reports_saved_credentials(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            auth_file = Path(tmp_dir) / "auth.json"
            output = io.StringIO()
            with patch.dict(os.environ, {"ORDL_AUTH_FILE": str(auth_file)}):
                with patch("openreview_downloader.cli.load_keyring", return_value=None):
                    save_credentials("saved@example.com", "secret")
                    with redirect_stdout(output):
                        auth_main(["status"])

        text = output.getvalue()
        self.assertIn("OpenReview credentials: file", text)
        self.assertIn("Username: saved@example.com", text)


if __name__ == "__main__":
    unittest.main()
