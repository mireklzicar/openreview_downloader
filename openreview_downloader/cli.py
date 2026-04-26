#!/usr/bin/env python3

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Pattern, Sequence, Tuple

from tqdm import tqdm

# Environment variables can override defaults.
DEFAULT_VENUE_ID = os.environ.get("VENUE_ID", "NeurIPS.cc/2025/Conference")
ALL_DECISIONS_TOKEN = "all"
VALID_DECISIONS = {"oral", "spotlight", "accepted", "rejected"}
REJECTED_SUFFIXES = ("Rejected_Submission", "Desk_Rejected")
SEARCHABLE_FIELDS = (
    "number",
    "id",
    "decision",
    "title",
    "authors",
    "abstract",
    "keywords",
    "venue",
    "venueid",
)


def build_client():
    """Return an OpenReview client, optionally authenticated via env vars."""
    import openreview

    username = os.environ.get("OPENREVIEW_USERNAME")
    password = os.environ.get("OPENREVIEW_PASSWORD")
    return openreview.api.OpenReviewClient(
        baseurl="https://api2.openreview.net",
        username=username,
        password=password,
    )


def conference_dir(venue_id: str) -> Path:
    """Pick a readable directory name from the venue id."""
    parts = venue_id.split("/")
    short_name = parts[0].split(".")[0] if parts else ""
    year = next((p for p in parts if p.isdigit()), "")
    if short_name and year:
        slug = f"{short_name}{year}".lower()
    else:
        slug = venue_id.replace("/", "_").lower()
    return Path("downloads") / slug


def sanitize_title(title: str) -> str:
    cleaned = "".join(c for c in title if c.isalnum() or c in " _-")
    cleaned = "_".join(cleaned.split())
    return cleaned[:120] or "paper"


def stringify_value(value) -> str:
    if isinstance(value, (list, tuple, set)):
        return ", ".join(stringify_value(item) for item in value if item)
    if isinstance(value, dict):
        return ", ".join(
            f"{key}: {stringify_value(val)}" for key, val in value.items() if val
        )
    return str(value) if value else ""


def content_value(note, key: str) -> str:
    raw_value = note.content.get(key, "")
    if isinstance(raw_value, dict):
        raw_value = raw_value.get("value") or ""
    return stringify_value(raw_value)


def presentation_type(note) -> Optional[str]:
    """Return 'oral' or 'spotlight' if the note matches, else None."""
    venue_text = content_value(note, "venue").lower()
    decision_text = content_value(note, "decision").lower()
    combined = f"{venue_text} {decision_text}"
    if "oral" in combined:
        return "oral"
    if "spotlight" in combined:
        return "spotlight"
    return None


def note_decision(note, venue_id: str) -> Optional[str]:
    venueid = content_value(note, "venueid")
    label = presentation_type(note)

    if venueid == venue_id:
        return label or "accepted"

    lowered_vid = venueid.lower()
    if venueid.startswith(f"{venue_id}/") and (
        "reject" in lowered_vid or "desk" in lowered_vid
    ):
        return "rejected"

    combined_text = (
        f"{content_value(note, 'venue')} {content_value(note, 'decision')}"
    ).lower()
    if "reject" in combined_text:
        return "rejected"

    return label


def paper_path(note, category: str, base_dir: Path) -> Path:
    title = content_value(note, "title")
    fname_parts = []
    if getattr(note, "number", None) is not None:
        fname_parts.append(f"{note.number:05d}")
    safe_title = sanitize_title(title)
    fname_parts.append(safe_title)
    fname = "_".join([p for p in fname_parts if p]) + ".pdf"
    return base_dir / category / fname


def parse_decisions(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    invalid = [p for p in parts if p not in VALID_DECISIONS | {ALL_DECISIONS_TOKEN}]
    if invalid:
        raise argparse.ArgumentTypeError(
            f"Unknown decisions: {', '.join(sorted(set(invalid)))}."
        )
    ordered = []
    for part in parts:
        if part == ALL_DECISIONS_TOKEN:
            expanded = ["accepted", "rejected"]
        else:
            expanded = [part]
        for decision in expanded:
            if decision not in ordered:
                ordered.append(decision)
    return ordered


def parse_nonnegative_int(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if value < 0:
        raise argparse.ArgumentTypeError("must be 0 or greater")
    return value


def compile_regexes(
    patterns: Iterable[str], case_sensitive: bool
) -> List[Pattern[str]]:
    flags = 0 if case_sensitive else re.IGNORECASE
    compiled = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern, flags))
        except re.error as exc:
            raise argparse.ArgumentTypeError(
                f"Invalid regex {pattern!r}: {exc}"
            ) from exc
    return compiled


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download, list, and search OpenReview papers by decision."
    )
    parser.add_argument(
        "decisions",
        nargs="?",
        help=(
            "Comma-separated list of decisions to select "
            "(oral,spotlight,accepted,rejected,all)."
        ),
    )
    parser.add_argument(
        "--venue-id",
        default=DEFAULT_VENUE_ID,
        help="OpenReview venue id (default: NeurIPS 2025 Conference or env VENUE_ID).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (default: downloads/<venue>/).",
    )
    parser.add_argument(
        "--no-skip-existing",
        dest="skip_existing",
        action="store_false",
        help="Re-download even if the file already exists.",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Print decision counts for the venue and exit.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List selected papers and exit without downloading.",
    )
    parser.add_argument(
        "--head",
        type=parse_nonnegative_int,
        metavar="N",
        help=(
            "Limit the selected papers to the first N. With --list this previews "
            "the head; during download this downloads only the first N matches."
        ),
    )
    parser.add_argument(
        "--search",
        "--grep",
        dest="search_terms",
        action="append",
        default=[],
        metavar="TEXT",
        help=(
            "Case-insensitive text search over title, authors, abstract, keywords, "
            "decision, venue, id, and paper number. Repeat to require multiple terms."
        ),
    )
    parser.add_argument(
        "--regex",
        dest="regex_patterns",
        action="append",
        default=[],
        metavar="PATTERN",
        help=(
            "Regex search over the same fields as --search. Repeat to require "
            "multiple patterns."
        ),
    )
    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="Make --search and --regex matching case-sensitive.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "jsonl"),
        default="text",
        help="Output format for --list (default: text).",
    )
    parser.set_defaults(skip_existing=True)

    args = parser.parse_args()
    try:
        parsed_decisions = parse_decisions(args.decisions)
        args.regexes = compile_regexes(args.regex_patterns, args.case_sensitive)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))

    inspection_requested = bool(
        args.info
        or args.list
        or args.head is not None
        or args.search_terms
        or args.regex_patterns
    )
    if not parsed_decisions:
        if args.info:
            parsed_decisions = []
        elif inspection_requested:
            parsed_decisions = ["accepted"]
            args.list = True
        else:
            parser.error(
                "DECISIONS is required unless --info or a listing/search option "
                "is provided."
            )

    args.decisions = parsed_decisions
    return args


def note_search_fields(note, category: str) -> List[Tuple[str, str]]:
    number = getattr(note, "number", None)
    fields = {
        "number": str(number) if number is not None else "",
        "id": getattr(note, "id", ""),
        "decision": category,
        "title": content_value(note, "title"),
        "authors": content_value(note, "authors"),
        "abstract": content_value(note, "abstract"),
        "keywords": content_value(note, "keywords"),
        "venue": content_value(note, "venue"),
        "venueid": content_value(note, "venueid"),
    }
    return [(field, fields[field]) for field in SEARCHABLE_FIELDS if fields[field]]


def snippet(text: str, start: int, end: int, context: int = 60) -> str:
    left = max(0, start - context)
    right = min(len(text), end + context)
    prefix = "..." if left > 0 else ""
    suffix = "..." if right < len(text) else ""
    return f"{prefix}{text[left:start]}[{text[start:end]}]{text[end:right]}{suffix}"


def text_match_details(
    fields: Sequence[Tuple[str, str]], term: str, case_sensitive: bool
) -> Tuple[int, Optional[Dict[str, object]]]:
    if not term:
        return 0, None

    needle = term if case_sensitive else term.lower()
    total = 0
    first_match: Optional[Dict[str, object]] = None
    for field, text in fields:
        haystack = text if case_sensitive else text.lower()
        start = haystack.find(needle)
        if start == -1:
            continue
        count = haystack.count(needle)
        total += count
        if first_match is None:
            first_match = {
                "field": field,
                "query": term,
                "count": count,
                "snippet": snippet(text, start, start + len(term)),
            }
    return total, first_match


def regex_match_details(
    fields: Sequence[Tuple[str, str]], regex: Pattern[str]
) -> Tuple[int, Optional[Dict[str, object]]]:
    total = 0
    first_match: Optional[Dict[str, object]] = None
    for field, text in fields:
        matches = list(regex.finditer(text))
        if not matches:
            continue
        total += len(matches)
        if first_match is None:
            match = matches[0]
            first_match = {
                "field": field,
                "pattern": regex.pattern,
                "count": len(matches),
                "snippet": snippet(text, match.start(), match.end()),
            }
    return total, first_match


def note_match_info(
    note, category: str, args: argparse.Namespace
) -> Optional[Dict[str, object]]:
    fields = note_search_fields(note, category)
    details = []
    total_hits = 0

    for term in args.search_terms:
        count, detail = text_match_details(fields, term, args.case_sensitive)
        if count == 0:
            return None
        total_hits += count
        if detail:
            details.append(detail)

    for regex in args.regexes:
        count, detail = regex_match_details(fields, regex)
        if count == 0:
            return None
        total_hits += count
        if detail:
            details.append(detail)

    return {"hit_count": total_hits, "details": details}


def has_search_filters(args: argparse.Namespace) -> bool:
    return bool(args.search_terms or args.regexes)


def filter_selected(
    selected: Sequence[Tuple[object, str, Path]], args: argparse.Namespace
) -> List[Tuple[object, str, Path, Optional[Dict[str, object]]]]:
    filtered = []
    for note, category, path in selected:
        match_info = note_match_info(note, category, args)
        if has_search_filters(args) and match_info is None:
            continue
        filtered.append((note, category, path, match_info))
    return filtered


def paper_record(
    note, category: str, path: Path, match_info: Optional[Dict[str, object]]
) -> Dict[str, object]:
    return {
        "number": getattr(note, "number", None),
        "id": getattr(note, "id", ""),
        "decision": category,
        "title": content_value(note, "title"),
        "authors": content_value(note, "authors"),
        "venue": content_value(note, "venue"),
        "venueid": content_value(note, "venueid"),
        "pdf_path": str(path),
        "match_count": match_info["hit_count"] if match_info else 0,
        "matches": match_info["details"] if match_info else [],
    }


def format_paper_line(note, category: str) -> str:
    number = getattr(note, "number", None)
    number_part = f"{number:05d}" if isinstance(number, int) else "-----"
    return f"{number_part} [{category}] {content_value(note, 'title')}"


def print_selected(
    selected: Sequence[Tuple[object, str, Path, Optional[Dict[str, object]]]],
    total_before_head: int,
    args: argparse.Namespace,
) -> None:
    if args.format == "jsonl":
        summary = {
            "type": "summary",
            "venue_id": args.venue_id,
            "decisions": args.decisions,
            "matched_papers": total_before_head,
            "shown_papers": len(selected),
            "head": args.head,
        }
        print(json.dumps(summary, sort_keys=True))
        for note, category, path, match_info in selected:
            record = paper_record(note, category, path, match_info)
            record["type"] = "paper"
            print(json.dumps(record, sort_keys=True))
        return

    print(f"Matched papers: {total_before_head}")
    if args.head is not None:
        print(f"Showing first: {len(selected)}")
    if has_search_filters(args):
        total_hits = sum(
            match_info["hit_count"]
            for _, _, _, match_info in selected
            if match_info
        )
        print(f"Text hits shown: {total_hits}")
    print("---")
    for note, category, path, match_info in selected:
        print(format_paper_line(note, category))
        authors = content_value(note, "authors")
        if authors:
            print(f"  authors: {authors}")
        print(f"  id: {getattr(note, 'id', '')}")
        print(f"  pdf: {path}")
        if match_info:
            for detail in match_info["details"]:
                label = detail.get("query") or detail.get("pattern")
                print(
                    f"  match: {detail['field']} / {label}: "
                    f"{detail['snippet']}"
                )


def split_existing(
    selected: Sequence[Tuple[object, str, Path, Optional[Dict[str, object]]]],
    skip_existing: bool,
) -> Tuple[List[Tuple[object, str, Path, Optional[Dict[str, object]]]], int]:
    if not skip_existing:
        return list(selected), 0
    to_download = []
    existing = 0
    for item in selected:
        path = item[2]
        if path.exists():
            existing += 1
        else:
            to_download.append(item)
    return to_download, existing


def fetch_notes(
    client, venue_id: str, need_rejected: bool
) -> Tuple[List, List]:
    accepted = client.get_all_notes(content={"venueid": venue_id})
    rejected: List = []
    if need_rejected:
        for suffix in REJECTED_SUFFIXES:
            rejected.extend(
                client.get_all_notes(content={"venueid": f"{venue_id}/{suffix}"})
            )
    return accepted, rejected


def decision_counts(
    accepted: Sequence, rejected: Sequence, venue_id: str
) -> Dict[str, int]:
    counts = {key: 0 for key in VALID_DECISIONS}
    for note in accepted:
        label = note_decision(note, venue_id)
        if label == "oral":
            counts["oral"] += 1
            counts["accepted"] += 1
        elif label == "spotlight":
            counts["spotlight"] += 1
            counts["accepted"] += 1
        elif label == "accepted":
            counts["accepted"] += 1
    for note in rejected:
        if note_decision(note, venue_id) == "rejected":
            counts["rejected"] += 1
    return counts


def target_category(label: Optional[str], requested: set) -> Optional[str]:
    if label == "oral":
        if "oral" in requested:
            return "oral"
        if "accepted" in requested:
            return "accepted"
    elif label == "spotlight":
        if "spotlight" in requested:
            return "spotlight"
        if "accepted" in requested:
            return "accepted"
    elif label == "accepted":
        if "accepted" in requested:
            return "accepted"
    elif label == "rejected" and "rejected" in requested:
        return "rejected"
    return None


def collect_selected(
    accepted: Sequence,
    rejected: Sequence,
    venue_id: str,
    decisions: List[str],
    base_dir: Path,
) -> List[Tuple[object, str, Path]]:
    requested = set(decisions)
    selected = []
    seen_ids = set()

    for note in accepted:
        label = note_decision(note, venue_id)
        target = target_category(label, requested)
        if not target or note.id in seen_ids:
            continue
        path = paper_path(note, target, base_dir)
        selected.append((note, target, path))
        seen_ids.add(note.id)

    for note in rejected:
        target = target_category("rejected", requested)
        if not target or note.id in seen_ids:
            continue
        path = paper_path(note, target, base_dir)
        selected.append((note, target, path))
        seen_ids.add(note.id)

    return selected


def print_info(venue_id: str, counts: Dict[str, int]) -> None:
    parts = venue_id.split("/")
    short_name = parts[0].split(".")[0] if parts else venue_id
    year = next((p for p in parts if p.isdigit()), "")
    heading = " ".join(part for part in (short_name, year) if part)

    print(heading or venue_id)
    print("---")
    print(f"Oral: {counts['oral']}")
    print(f"Spotlight: {counts['spotlight']}")
    print(f"Accepted: {counts['accepted']}")
    print(f"Rejected: {counts['rejected']}")


def status(message: str, args: argparse.Namespace) -> None:
    stream = sys.stderr if args.list and args.format == "jsonl" else sys.stdout
    print(message, file=stream)


def main() -> None:
    args = parse_args()

    client = build_client()
    base_dir = args.out_dir or conference_dir(args.venue_id)
    if not args.info and not args.list:
        base_dir.mkdir(parents=True, exist_ok=True)

    need_rejected = args.info or "rejected" in args.decisions
    status(f"Fetching accepted submissions for {args.venue_id}...", args)
    accepted, rejected = fetch_notes(client, args.venue_id, need_rejected)
    status(f"Accepted submissions: {len(accepted)}", args)
    if need_rejected:
        status(f"Rejected submissions: {len(rejected)}", args)

    counts = decision_counts(accepted, rejected, args.venue_id)
    if args.info:
        print_info(args.venue_id, counts)
        return

    selected = collect_selected(
        accepted=accepted,
        rejected=rejected,
        venue_id=args.venue_id,
        decisions=args.decisions,
        base_dir=base_dir,
    )
    matched = filter_selected(selected, args)
    total_matches = len(matched)
    selected_for_action = matched[: args.head] if args.head is not None else matched

    if args.list:
        print_selected(selected_for_action, total_matches, args)
        return

    to_download, already_present = split_existing(
        selected_for_action,
        args.skip_existing,
    )
    print(f"Requested decisions: {', '.join(args.decisions)}")
    if has_search_filters(args):
        total_hits = sum(
            match_info["hit_count"]
            for _, _, _, match_info in selected_for_action
            if match_info
        )
        print(f"Matched papers: {total_matches}. Text hits selected: {total_hits}")
    if args.head is not None:
        print(f"Head limit: first {len(selected_for_action)} selected papers")
    print(f"Already present: {already_present}. To download now: {len(to_download)}")

    for note, category, path, _match_info in tqdm(
        to_download, desc="Downloading", unit="paper"
    ):
        pdf_meta = note.content.get("pdf", {})
        pdf_field_value = pdf_meta.get("value") if isinstance(pdf_meta, dict) else None
        if not pdf_field_value:
            tqdm.write(f"Skipping {note.id}: no pdf field")
            continue

        try:
            pdf_bytes = client.get_attachment(field_name="pdf", id=note.id)
        except Exception as exc:  # noqa: BLE001
            tqdm.write(f"Failed to fetch {note.id}: {exc}")
            continue

        try:
            tmp_path = path.with_suffix(path.suffix + ".part")
            tmp_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_bytes(pdf_bytes)
            tmp_path.replace(path)
        except Exception as exc:  # noqa: BLE001
            tqdm.write(f"Failed to save {path}: {exc}")
            continue

    print(f"Done. Files saved under {base_dir}/<decision>/")


if __name__ == "__main__":
    main()
