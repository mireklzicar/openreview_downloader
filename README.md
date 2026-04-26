[![PyPI - Version](https://img.shields.io/pypi/v/openreview-downloader)](https://pypi.org/project/openreview-downloader/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

# OpenReview Paper Downloader

Simple download, listing, and search of oral, spotlight, accepted, or rejected papers from OpenReview into tidy folders by decision.

Despite the name, this works for **any** OpenReview-hosted conference (NeurIPS, ICLR, ICML, etc.).

## Installation

```bash
pip install openreview_downloader
```

## Usage

The CLI saves PDFs into `downloads/<venue>/<decision>/` with sanitized filenames.

**Available decisions:**
- `oral` – Oral presentations
- `spotlight` – Spotlight presentations
- `accepted` – All accepted papers
- `rejected` – Rejected papers
- `all` – Accepted and rejected papers

### Basic examples (NeurIPS)

Download all NeurIPS oral papers:

```bash
ordl oral --venue-id NeurIPS.cc/2025/Conference
```

Download Output:

```
downloads
└── neurips2025
    └── oral
        ├── 27970_Deep_Compositional_Phase_Diffusion.pdf
        ...
        └── 28928_Generalized_Linear_Mode_Connectivity.pdf
```


Download all NeurIPS oral and spotlight papers:

```bash
ordl oral,spotlight --venue-id NeurIPS.cc/2025/Conference
```

Download all accepted NeurIPS papers (any presentation type):

```bash
ordl accepted --venue-id NeurIPS.cc/2025/Conference
```

See decision counts without downloading:

```bash
ordl --info --venue-id NeurIPS.cc/2025/Conference
```

Example output:

```
Fetching accepted submissions for NeurIPS.cc/2025/Conference...
Accepted submissions: 5286
Rejected submissions: 254
NeurIPS 2025
---
Oral: 77
Spotlight: 687
Accepted: 5286
Rejected: 254
```

### List and preview papers

List all accepted papers without downloading:

```bash
ordl accepted --list --venue-id NeurIPS.cc/2025/Conference
```

List accepted and rejected papers:

```bash
ordl all --list --venue-id NeurIPS.cc/2025/Conference
```

Show only the first 3 accepted papers:

```bash
ordl accepted --list --head 3 --venue-id NeurIPS.cc/2025/Conference
```

Example output:

```
Fetching accepted submissions for NeurIPS.cc/2025/Conference...
Accepted submissions: 5286
Matched papers: 5286
Showing first: 3
---
29297 [accepted] Time-o1: Time-Series Forecasting Needs Transformed Label Alignment
  authors: Hao Wang, Licheng Pan, Zhichao Chen, Xu Chen, Qingyang Dai, Lei Wang, Haoxuan Li, Zhouchen Lin
  id: RxWILaXuhb
  pdf: downloads/neurips2025/accepted/29297_Time-o1_Time-Series_Forecasting_Needs_Transformed_Label_Alignment.pdf
29260 [accepted] REVE: A Foundation Model for EEG - Adapting to Any Setup with Large-Scale Pretraining on 25,000 Subjects
  authors: Yassine El Ouahidi, Jonathan Lys, Philipp Thölke, Nicolas Farrugia, Bastien Pasdeloup, Vincent Gripon, Karim Jerbi, Giulia Lioi
  id: ZeFMtRBy4Z
  pdf: downloads/neurips2025/accepted/29260_REVE_A_Foundation_Model_for_EEG_-_Adapting_to_Any_Setup_with_Large-Scale_Pretraining_on_25000_Subjects.pdf
```

If you omit `DECISIONS` while listing or searching, the CLI defaults to accepted papers and exits without downloading:

```bash
ordl --head 20 --venue-id NeurIPS.cc/2025/Conference
```

### Search, grep, and regex workflows

Search over title, authors, abstract, keywords, decision, venue, id, and paper number. `--search` and `--grep` are aliases; matching is case-insensitive by default.

Preview accepted papers matching a text query:

```bash
ordl accepted --list --search diffusion --head 2 --venue-id NeurIPS.cc/2025/Conference
```

Example output:

```
Fetching accepted submissions for NeurIPS.cc/2025/Conference...
Accepted submissions: 5286
Matched papers: 710
Showing first: 2
Text hits shown: 4
---
29119 [accepted] CADGrasp: Learning Contact and Collision Aware General Dexterous Grasping in Cluttered Scenes
  authors: Jiyao Zhang, Zhiyuan Ma, Tianhao Wu, Zeyuan Chen, Hao Dong
  id: CB8jwNE2vV
  pdf: downloads/neurips2025/accepted/29119_CADGrasp_Learning_Contact_and_Collision_Aware_General_Dexterous_Grasping_in_Cluttered_Scenes.pdf
  match: abstract / diffusion: ... high-dimensional representation, we introduce an occupancy-[diffusion] model with voxel-level conditional guidance and force closu...
29103 [accepted] KLASS: KL-Guided Fast Inference in Masked Diffusion Models
  authors: Seo Hyun Kim, Sunwoo Hong, Hojung Jung, Youngrok Park, Se-Young Yun
  id: gOG9Zoyn4R
  pdf: downloads/neurips2025/accepted/29103_KLASS_KL-Guided_Fast_Inference_in_Masked_Diffusion_Models.pdf
  match: title / diffusion: KLASS: KL-Guided Fast Inference in Masked [Diffusion] Models
```

Preview regex matches and show snippets plus counts:

```bash
ordl accepted --list --regex 'diffusion|transformer' --head 2 --venue-id NeurIPS.cc/2025/Conference
```

Download the same selection by rerunning the same query without `--list`:

```bash
ordl accepted --search diffusion --venue-id NeurIPS.cc/2025/Conference
```

Download only the first 10 matches:

```bash
ordl accepted --search diffusion --head 10 --venue-id NeurIPS.cc/2025/Conference
```

Require multiple terms or patterns by repeating the flags:

```bash
ordl accepted --list --grep diffusion --grep protein --venue-id NeurIPS.cc/2025/Conference
```

For scripts, agents, and crawlbots, use JSON Lines output while listing:

```bash
ordl accepted --list --search diffusion --head 2 --format jsonl --venue-id NeurIPS.cc/2025/Conference
```

The first JSON line is a summary with the number of matched and shown papers; each following line is one paper record with stable fields such as `id`, `number`, `decision`, `title`, `authors`, `pdf_path`, `match_count`, and `matches`.

JSONL keeps progress logs on stderr so stdout can be piped directly into tools:

```json
{"decisions": ["accepted"], "head": 2, "matched_papers": 710, "shown_papers": 2, "type": "summary", "venue_id": "NeurIPS.cc/2025/Conference"}
{"authors": "Jiyao Zhang, Zhiyuan Ma, Tianhao Wu, Zeyuan Chen, Hao Dong", "decision": "accepted", "id": "CB8jwNE2vV", "match_count": 1, "matches": [{"count": 1, "field": "abstract", "query": "diffusion", "snippet": "... high-dimensional representation, we introduce an occupancy-[diffusion] model with voxel-level conditional guidance and force closu..."}], "number": 29119, "pdf_path": "downloads/neurips2025/accepted/29119_CADGrasp_Learning_Contact_and_Collision_Aware_General_Dexterous_Grasping_in_Cluttered_Scenes.pdf", "title": "CADGrasp: Learning Contact and Collision Aware General Dexterous Grasping in Cluttered Scenes", "type": "paper", "venue": "NeurIPS 2025 poster", "venueid": "NeurIPS.cc/2025/Conference"}
```

### Other Conferences (ICLR, ICML, etc.)

Just change the `--venue-id` to the appropriate OpenReview handle.

**ICLR 2025 orals only:**

```bash
ordl oral --venue-id ICLR.cc/2025/Conference
```

**ICLR 2025 accepted papers (all formats):**

```bash
ordl accepted --venue-id ICLR.cc/2025/Conference
```

**ICML 2025 oral + spotlight:**

```bash
ordl oral,spotlight --venue-id ICML.cc/2025/Conference
```

You can use any other OpenReview venue ID in the same way.


### CLI Options

- **`DECISIONS`** (positional) – Comma-separated list of decisions to select (`oral`, `spotlight`, `accepted`, `rejected`, `all`)
- **`--venue-id`** – OpenReview venue ID (default: `NeurIPS.cc/2025/Conference` or env `VENUE_ID`)
- **`--out-dir`** – Custom output directory (default: `downloads/<venue>/`)
- **`--no-skip-existing`** – Re-download even if the PDF is already present
- **`--info`** – Print decision counts for the venue and exit
- **`--list`** – List selected papers and exit without downloading
- **`--head N`** – Limit the selection to the first `N` papers; useful for previews or small downloads
- **`--search TEXT` / `--grep TEXT`** – Text search across paper metadata; repeat to require multiple terms
- **`--regex PATTERN`** – Regex search across paper metadata; repeat to require multiple patterns
- **`--case-sensitive`** – Make search and regex matching case-sensitive
- **`--format text|jsonl`** – Output format for `--list`; `jsonl` is convenient for automation

## Development

Install in editable mode with development dependencies:

```bash
pip install -e '.[dev]'
```

Run the tests:

```bash
python -m unittest discover -s tests
```

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.
