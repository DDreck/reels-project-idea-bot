# Inspiration Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-ingest Instagram reels saved across multiple collections into a markdown vault as classified, summarized, atomic notes — collector on a Pi, GPU transcription + Claude reasoning batched off-hours.

**Architecture:** Two decoupled stages joined by a sqlite queue. The *collector* (pi4, all day) polls IG collections via instagrapi, diffs against a seen-set, downloads new reels with yt-dlp, and enqueues them. The *processor* (nightly 04:00 or manual) wakes dreck (RTX 5090), transcribes + OCRs videos there via SSH, pulls results back, then has headless Claude Code classify/summarize each reel (returning JSON) while Python deterministically renders the note, updates the category registry, writes to the output dir, and purges the video.

**Tech Stack:** Python 3.12, instagrapi, yt-dlp, wakeonlan, system ssh/scp, stdlib sqlite3 + tomllib, python-dotenv, pytest. On dreck only: faster-whisper, pytesseract, opencv-python.

## Global Constraints

- Python **3.12** (matches existing homelab projects).
- Public **MIT** repo; code must be reusable via config — no hardcoded personal paths.
- **No secrets, no vault content, no media, no sqlite db committed.** `.gitignore` from day one covers: `.env`, IG session file, `*.db`, `queue/`, `__pycache__/`.
- Secrets only via gitignored `.env`; non-secret config via `config.toml`. `.env.example` and `config.example.toml` committed.
- Line length ≤100, functions ≤100 lines / complexity ≤8, ≤5 positional params, absolute imports only.
- Mock only boundaries (Instagram, SSH/dreck, Whisper, the `claude` subprocess). Never mock rendering/filing/db logic.
- Frequent commits: one per task minimum.

---

## File Structure

```
inspiration-pipeline/
├── pyproject.toml
├── README.md
├── LICENSE                          # MIT
├── .gitignore
├── .env.example
├── config.example.toml
├── inspiration_pipeline/
│   ├── __init__.py
│   ├── config.py                    # Config dataclass; load from toml + env
│   ├── models.py                    # ReelMeta, Classification dataclasses
│   ├── db.py                        # sqlite schema + queue operations
│   ├── categories.py                # _categories.md read/append
│   ├── notes.py                     # pure note rendering
│   ├── claude_client.py             # invoke `claude -p`, parse JSON (boundary)
│   ├── filing.py                    # classify→render→write→purge→mark for one reel
│   ├── collector.py                 # instagrapi + yt-dlp + diff + enqueue
│   ├── dreck.py                     # WoL / ssh-wait / scp / remote run / sleep
│   ├── processor.py                 # batch: transcribe + file
│   └── cli.py                       # argparse: collect / process
├── remote/
│   ├── transcribe_ocr.py            # runs ON dreck: faster-whisper + frame OCR → json
│   └── requirements-dreck.txt       # faster-whisper, pytesseract, opencv-python
├── deploy/
│   ├── inspiration-collector.service
│   ├── inspiration-collector.timer
│   ├── inspiration-processor.service
│   └── inspiration-processor.timer
└── tests/
    ├── conftest.py
    ├── test_config.py
    ├── test_db.py
    ├── test_categories.py
    ├── test_notes.py
    ├── test_claude_client.py
    ├── test_filing.py
    ├── test_collector.py
    ├── test_dreck.py
    ├── test_processor.py
    ├── test_cli.py
    └── test_remote_transcribe_ocr.py
```

---

## Task 1: Scaffolding + config loader

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `LICENSE`, `.env.example`, `config.example.toml`, `inspiration_pipeline/__init__.py`, `inspiration_pipeline/config.py`
- Test: `tests/test_config.py`, `tests/conftest.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Config` dataclass and `load_config(config_path: Path, env_path: Path | None = None) -> Config`. Fields: `collections: list[str]`, `output_dir: Path`, `queue_dir: Path`, `db_path: Path`, `poll_interval_hours: float`, `whisper_model: str`, `batch_size: int`, `keep_originals: bool`, `max_attempts: int`, `dreck_host: str`, `dreck_user: str`, `dreck_mac: str`, `dreck_scratch_dir: str`, `dreck_sleep_cmd: str`, `claude_bin: str`, `ig_username: str`, `ig_password: str`, `ig_session_path: Path`. Raises `ConfigError` on missing required secret.

- [ ] **Step 1: Write `pyproject.toml`, `.gitignore`, `LICENSE`, examples**

`pyproject.toml`:
```toml
[project]
name = "inspiration-pipeline"
version = "0.1.0"
description = "Auto-ingest saved Instagram reels into a markdown knowledge vault"
requires-python = ">=3.12"
dependencies = [
    "instagrapi>=2.1.2",
    "yt-dlp>=2025.6.9",
    "wakeonlan>=3.1.0",
    "python-dotenv>=1.0.1",
]

[project.optional-dependencies]
dev = ["pytest>=8.2.0"]

[project.scripts]
inspiration = "inspiration_pipeline.cli:main"

[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
testpaths = ["tests"]
```
> Verify current stable versions with `pip index versions <pkg>` before pinning; bump if newer stable exists.

`.gitignore`:
```gitignore
__pycache__/
*.pyc
.env
*.db
queue/
session.json
.venv/
*.egg-info/
```

`LICENSE`: standard MIT text, copyright `2026 drew`.

`.env.example`:
```dotenv
IG_USERNAME=throwaway_bot_account
IG_PASSWORD=changeme
```

`config.example.toml`:
```toml
collections = ["projects", "looksmax", "3d prints"]
output_dir = "/home/youruser/second-brain-vault/wiki/inspiration"
queue_dir = "./queue"
db_path = "./inspiration.db"
ig_session_path = "./session.json"
poll_interval_hours = 4.0
whisper_model = "large-v3"
batch_size = 50
keep_originals = false
max_attempts = 3
claude_bin = "claude"

[dreck]
host = "your-dreck-host"
user = "drew"
mac = "AA-BB-CC-DD-EE-FF"
scratch_dir = "C:/Users/youruser/insp_scratch"
sleep_cmd = "rundll32.exe powrprof.dll,SetSuspendState 0,1,0"
```

- [ ] **Step 2: Write the failing test**

`tests/conftest.py`:
```python
from pathlib import Path

import pytest


@pytest.fixture
def config_files(tmp_path: Path) -> tuple[Path, Path]:
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'collections = ["projects", "looksmax"]\n'
        f'output_dir = "{tmp_path / "out"}"\n'
        f'queue_dir = "{tmp_path / "queue"}"\n'
        f'db_path = "{tmp_path / "insp.db"}"\n'
        f'ig_session_path = "{tmp_path / "session.json"}"\n'
        "poll_interval_hours = 4.0\n"
        'whisper_model = "large-v3"\n'
        "batch_size = 50\n"
        "keep_originals = false\n"
        "max_attempts = 3\n"
        'claude_bin = "claude"\n'
        "[dreck]\n"
        'host = "your-dreck-host"\n'
        'user = "drew"\n'
        'mac = "AA-BB-CC-DD-EE-FF"\n'
        'scratch_dir = "C:/scratch"\n'
        'sleep_cmd = "sleepnow"\n',
        encoding="utf-8",
    )
    env = tmp_path / ".env"
    env.write_text("IG_USERNAME=bot\nIG_PASSWORD=pw\n", encoding="utf-8")
    return cfg, env
```

`tests/test_config.py`:
```python
import pytest

from inspiration_pipeline.config import ConfigError, load_config


def test_load_config_reads_toml_and_env(config_files):
    cfg_path, env_path = config_files
    cfg = load_config(cfg_path, env_path)
    assert cfg.collections == ["projects", "looksmax"]
    assert cfg.batch_size == 50
    assert cfg.keep_originals is False
    assert cfg.dreck_mac == "AA-BB-CC-DD-EE-FF"
    assert cfg.ig_username == "bot"
    assert cfg.ig_password == "pw"


def test_load_config_missing_secret_raises(config_files):
    cfg_path, env_path = config_files
    env_path.write_text("IG_USERNAME=bot\n", encoding="utf-8")  # no password
    with pytest.raises(ConfigError, match="IG_PASSWORD"):
        load_config(cfg_path, env_path)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: inspiration_pipeline.config`

- [ ] **Step 4: Implement `inspiration_pipeline/config.py`**

`inspiration_pipeline/__init__.py`: empty file.

```python
"""Configuration loading for the inspiration pipeline."""
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


class ConfigError(Exception):
    """Raised when configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    collections: list[str]
    output_dir: Path
    queue_dir: Path
    db_path: Path
    poll_interval_hours: float
    whisper_model: str
    batch_size: int
    keep_originals: bool
    max_attempts: int
    dreck_host: str
    dreck_user: str
    dreck_mac: str
    dreck_scratch_dir: str
    dreck_sleep_cmd: str
    claude_bin: str
    ig_username: str
    ig_password: str
    ig_session_path: Path


def _require(env: dict[str, str | None], key: str) -> str:
    value = env.get(key)
    if not value:
        raise ConfigError(f"Missing required secret {key} in .env")
    return value


def load_config(config_path: Path, env_path: Path | None = None) -> Config:
    """Load non-secret config from TOML and secrets from .env.

    Args:
        config_path: Path to config.toml.
        env_path: Path to .env; defaults to .env beside config_path.

    Returns:
        A populated, frozen Config.

    Raises:
        ConfigError: If a required secret is missing.
    """
    with open(config_path, "rb") as handle:
        raw = tomllib.load(handle)
    env_file = env_path or config_path.parent / ".env"
    env = {**dotenv_values(env_file), **os.environ}
    dreck = raw["dreck"]
    return Config(
        collections=list(raw["collections"]),
        output_dir=Path(raw["output_dir"]),
        queue_dir=Path(raw["queue_dir"]),
        db_path=Path(raw["db_path"]),
        poll_interval_hours=float(raw["poll_interval_hours"]),
        whisper_model=str(raw["whisper_model"]),
        batch_size=int(raw["batch_size"]),
        keep_originals=bool(raw["keep_originals"]),
        max_attempts=int(raw["max_attempts"]),
        dreck_host=str(dreck["host"]),
        dreck_user=str(dreck["user"]),
        dreck_mac=str(dreck["mac"]),
        dreck_scratch_dir=str(dreck["scratch_dir"]),
        dreck_sleep_cmd=str(dreck["sleep_cmd"]),
        claude_bin=str(raw["claude_bin"]),
        ig_username=_require(env, "IG_USERNAME"),
        ig_password=_require(env, "IG_PASSWORD"),
        ig_session_path=Path(raw["ig_session_path"]),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore LICENSE .env.example config.example.toml \
  inspiration_pipeline/__init__.py inspiration_pipeline/config.py \
  tests/conftest.py tests/test_config.py
git commit -m "feat: project scaffolding and config loader"
```

---

## Task 2: Data models

**Files:**
- Create: `inspiration_pipeline/models.py`
- Test: `tests/test_models.py` (trivial; folded — see below)

**Interfaces:**
- Produces: `ReelMeta(pk, shortcode, url, author, caption, taken_at, collection)` and `Classification(category, title, summary, key_points, domain, is_new_category, category_description)`. `domain ∈ {"Health", "Projects", "none"}`. `Classification.from_json(data: dict) -> Classification`.

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
from inspiration_pipeline.models import Classification


def test_classification_from_json():
    data = {
        "category": "3d-print",
        "title": "Print-in-place hinge",
        "summary": "A clever hinge.",
        "key_points": ["no supports", "PLA"],
        "domain": "Projects",
        "is_new_category": False,
        "category_description": "",
    }
    cls = Classification.from_json(data)
    assert cls.category == "3d-print"
    assert cls.domain == "Projects"
    assert cls.key_points == ["no supports", "PLA"]


def test_classification_from_json_defaults_missing_optional():
    cls = Classification.from_json(
        {"category": "workout", "title": "T", "summary": "S",
         "key_points": [], "domain": "Health"}
    )
    assert cls.is_new_category is False
    assert cls.category_description == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: inspiration_pipeline.models`

- [ ] **Step 3: Implement `inspiration_pipeline/models.py`**

```python
"""Domain dataclasses for the inspiration pipeline."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ReelMeta:
    pk: str
    shortcode: str
    url: str
    author: str
    caption: str
    taken_at: str  # ISO date, e.g. "2026-06-25"
    collection: str


@dataclass(frozen=True)
class Classification:
    category: str
    title: str
    summary: str
    key_points: list[str]
    domain: str  # "Health" | "Projects" | "none"
    is_new_category: bool = False
    category_description: str = ""

    @classmethod
    def from_json(cls, data: dict) -> "Classification":
        return cls(
            category=str(data["category"]),
            title=str(data["title"]),
            summary=str(data["summary"]),
            key_points=list(data["key_points"]),
            domain=str(data["domain"]),
            is_new_category=bool(data.get("is_new_category", False)),
            category_description=str(data.get("category_description", "")),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add inspiration_pipeline/models.py tests/test_models.py
git commit -m "feat: ReelMeta and Classification models"
```

---

## Task 3: sqlite queue layer

**Files:**
- Create: `inspiration_pipeline/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `ReelMeta` from Task 2.
- Produces:
  - `connect(db_path: Path) -> sqlite3.Connection` (Row factory, `init_db` applied)
  - `seen_pks(conn) -> set[str]`
  - `enqueue(conn, reel: ReelMeta) -> bool` (False if pk already present)
  - `records_by_status(conn, status: str) -> list[sqlite3.Row]`
  - `mark_transcribed(conn, pk: str) -> None` (sets `transcribed_at`, `ocr_at`, status=`transcribed`)
  - `mark_filed(conn, pk: str) -> None` (sets `filed_at`, status=`filed`)
  - `record_failure(conn, pk: str, error: str, max_attempts: int) -> None` (increments `attempts`; status=`failed` when attempts ≥ max)
  - Statuses: `"downloaded" → "transcribed" → "filed"`, plus `"failed"`.

- [ ] **Step 1: Write the failing test**

`tests/test_db.py`:
```python
from inspiration_pipeline import db
from inspiration_pipeline.models import ReelMeta


def _reel(pk="1"):
    return ReelMeta(pk=pk, shortcode=f"sc{pk}", url=f"http://x/{pk}",
                    author="@a", caption="cap", taken_at="2026-06-25",
                    collection="projects")


def test_enqueue_and_dedup(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    assert db.enqueue(conn, _reel("1")) is True
    assert db.enqueue(conn, _reel("1")) is False  # duplicate pk
    assert db.seen_pks(conn) == {"1"}


def test_status_transitions_set_timestamps(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.enqueue(conn, _reel("1"))
    assert [r["pk"] for r in db.records_by_status(conn, "downloaded")] == ["1"]
    db.mark_transcribed(conn, "1")
    row = db.records_by_status(conn, "transcribed")[0]
    assert row["transcribed_at"] is not None and row["ocr_at"] is not None
    db.mark_filed(conn, "1")
    row = db.records_by_status(conn, "filed")[0]
    assert row["filed_at"] is not None


def test_record_failure_marks_failed_at_max(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.enqueue(conn, _reel("1"))
    db.record_failure(conn, "1", "boom", max_attempts=2)
    assert db.records_by_status(conn, "failed") == []  # attempts=1 < 2
    db.record_failure(conn, "1", "boom", max_attempts=2)
    failed = db.records_by_status(conn, "failed")
    assert len(failed) == 1 and failed[0]["attempts"] == 2
    assert failed[0]["error"] == "boom"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: inspiration_pipeline.db`

- [ ] **Step 3: Implement `inspiration_pipeline/db.py`**

```python
"""sqlite-backed work queue for reels."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from inspiration_pipeline.models import ReelMeta

_SCHEMA = """
CREATE TABLE IF NOT EXISTS media (
    pk TEXT PRIMARY KEY,
    shortcode TEXT NOT NULL,
    url TEXT NOT NULL,
    author TEXT NOT NULL,
    caption TEXT NOT NULL,
    taken_at TEXT NOT NULL,
    collection TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'downloaded',
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    downloaded_at TEXT,
    transcribed_at TEXT,
    ocr_at TEXT,
    filed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def seen_pks(conn: sqlite3.Connection) -> set[str]:
    return {row["pk"] for row in conn.execute("SELECT pk FROM media")}


def enqueue(conn: sqlite3.Connection, reel: ReelMeta) -> bool:
    """Insert a downloaded reel. Returns False if pk already exists."""
    now = _now()
    try:
        conn.execute(
            "INSERT INTO media (pk, shortcode, url, author, caption, taken_at,"
            " collection, status, downloaded_at, created_at, updated_at) VALUES"
            " (?,?,?,?,?,?,?, 'downloaded', ?, ?, ?)",
            (reel.pk, reel.shortcode, reel.url, reel.author, reel.caption,
             reel.taken_at, reel.collection, now, now, now),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def records_by_status(conn: sqlite3.Connection, status: str) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM media WHERE status = ? ORDER BY created_at", (status,)
        )
    )


def _set(conn: sqlite3.Connection, pk: str, assignments: str, params: tuple) -> None:
    conn.execute(
        f"UPDATE media SET {assignments}, updated_at = ? WHERE pk = ?",
        (*params, _now(), pk),
    )
    conn.commit()


def mark_transcribed(conn: sqlite3.Connection, pk: str) -> None:
    now = _now()
    _set(conn, pk, "status='transcribed', transcribed_at=?, ocr_at=?", (now, now))


def mark_filed(conn: sqlite3.Connection, pk: str) -> None:
    _set(conn, pk, "status='filed', filed_at=?", (_now(),))


def record_failure(
    conn: sqlite3.Connection, pk: str, error: str, max_attempts: int
) -> None:
    row = conn.execute("SELECT attempts FROM media WHERE pk = ?", (pk,)).fetchone()
    attempts = (row["attempts"] if row else 0) + 1
    status = "failed" if attempts >= max_attempts else None
    if status:
        _set(conn, pk, "attempts=?, error=?, status='failed'", (attempts, error))
    else:
        _set(conn, pk, "attempts=?, error=?", (attempts, error))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_db.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add inspiration_pipeline/db.py tests/test_db.py
git commit -m "feat: sqlite queue layer with per-stage timestamps"
```

---

## Task 4: Category registry

**Files:**
- Create: `inspiration_pipeline/categories.py`
- Test: `tests/test_categories.py`

**Interfaces:**
- Produces:
  - `read_categories(path: Path) -> dict[str, str]` (name → description; `{}` if file missing)
  - `append_category(path: Path, name: str, description: str) -> None` (creates file with header if missing; no-op if name already present)

- [ ] **Step 1: Write the failing test**

`tests/test_categories.py`:
```python
from inspiration_pipeline import categories


def test_read_missing_returns_empty(tmp_path):
    assert categories.read_categories(tmp_path / "_categories.md") == {}


def test_append_then_read_roundtrip(tmp_path):
    path = tmp_path / "_categories.md"
    categories.append_category(path, "workout", "Exercise and training reels")
    categories.append_category(path, "3d-print", "3D printing builds")
    cats = categories.read_categories(path)
    assert cats == {
        "workout": "Exercise and training reels",
        "3d-print": "3D printing builds",
    }


def test_append_existing_is_noop(tmp_path):
    path = tmp_path / "_categories.md"
    categories.append_category(path, "workout", "first")
    categories.append_category(path, "workout", "second")
    assert categories.read_categories(path) == {"workout": "first"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_categories.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `inspiration_pipeline/categories.py`**

Format: a markdown table line per category, `| name | description |`.

```python
"""Read/append the Claude-managed category registry (_categories.md)."""
import re
from pathlib import Path

_HEADER = (
    "# Inspiration Categories\n\n"
    "Claude-managed. New categories are appended automatically.\n\n"
    "| category | description |\n| --- | --- |\n"
)
_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|\s*$")
_SKIP = {"category", "--- "}


def read_categories(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _ROW.match(line)
        if not match:
            continue
        name, desc = match.group(1), match.group(2)
        if name == "category" or set(name) <= {"-", " "}:
            continue
        result[name] = desc
    return result


def append_category(path: Path, name: str, description: str) -> None:
    existing = read_categories(path)
    if name in existing:
        return
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_HEADER, encoding="utf-8")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"| {name} | {description} |\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_categories.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add inspiration_pipeline/categories.py tests/test_categories.py
git commit -m "feat: Claude-managed category registry"
```

---

## Task 5: Note rendering

**Files:**
- Create: `inspiration_pipeline/notes.py`
- Test: `tests/test_notes.py`

**Interfaces:**
- Consumes: `ReelMeta`, `Classification`.
- Produces:
  - `render_note(reel: ReelMeta, transcript: str, ocr: str, cls: Classification, filed_date: str) -> str`
  - `note_filename(reel: ReelMeta) -> str` (e.g. `2026-06-25-print-in-place-hinge-sc1.md`; slugified title + shortcode for uniqueness)

- [ ] **Step 1: Write the failing test**

`tests/test_notes.py`:
```python
from inspiration_pipeline.models import Classification, ReelMeta
from inspiration_pipeline.notes import note_filename, render_note


def _reel():
    return ReelMeta(pk="1", shortcode="sc1", url="http://x/1", author="@a",
                    caption="cap", taken_at="2026-06-25", collection="3d prints")


def _cls(domain="Projects"):
    return Classification(category="3d-print", title="Print In Place Hinge",
                          summary="A hinge.", key_points=["no supports", "PLA"],
                          domain=domain)


def test_render_note_contains_frontmatter_and_sections():
    note = render_note(_reel(), "spoken words", "ON SCREEN", _cls(), "2026-06-28")
    assert "source: instagram-reel" in note
    assert 'url: "http://x/1"' in note
    assert "category: 3d-print" in note
    assert "captured: 2026-06-25" in note
    assert "filed: 2026-06-28" in note
    assert "[[Projects]]" in note
    assert "## Transcript\nspoken words" in note
    assert "## On-screen text\nON SCREEN" in note


def test_render_note_health_crosslink():
    note = render_note(_reel(), "t", "o", _cls(domain="Health"), "2026-06-28")
    assert "[[Health]]" in note


def test_render_note_no_domain_omits_crosslink():
    note = render_note(_reel(), "t", "o", _cls(domain="none"), "2026-06-28")
    assert "[[Projects]]" not in note and "[[Health]]" not in note


def test_note_filename_slugifies():
    assert note_filename(_reel()) == "2026-06-25-print-in-place-hinge-sc1.md"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_notes.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `inspiration_pipeline/notes.py`**

> Title comes from Claude (`Classification.title`); we slugify it for the filename.

```python
"""Pure rendering of a reel into a vault atomic note."""
import re

from inspiration_pipeline.models import Classification, ReelMeta

_CROSSLINK = {"Health": "[[Health]]", "Projects": "[[Projects]]"}


def _slug(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_-]+", "-", text).strip("-")


def note_filename(reel: ReelMeta) -> str:
    return f"{reel.taken_at}-{_slug(reel.title_or_caption())}-{reel.shortcode}.md"


def _yaml_tags(cls: Classification) -> str:
    tags = ["inspiration", cls.category]
    return "[" + ", ".join(tags) + "]"


def render_note(
    reel: ReelMeta, transcript: str, ocr: str, cls: Classification, filed_date: str
) -> str:
    crosslink = _CROSSLINK.get(cls.domain, "")
    points = "\n".join(f"- {p}" for p in cls.key_points)
    crosslink_block = f"\n> Cross-linked to {crosslink}\n" if crosslink else "\n"
    return (
        "---\n"
        "type: source\n"
        "source: instagram-reel\n"
        f'url: "{reel.url}"\n'
        f'author: "{reel.author}"\n'
        f'collection: "{reel.collection}"\n'
        f"category: {cls.category}\n"
        f"captured: {reel.taken_at}\n"
        f"filed: {filed_date}\n"
        "status: inbox\n"
        f"tags: {_yaml_tags(cls)}\n"
        "---\n\n"
        f"# {cls.title}\n\n"
        f"**Summary:** {cls.summary}\n\n"
        f"**Key points:**\n{points}\n"
        f"{crosslink_block}\n"
        f"## Transcript\n{transcript}\n\n"
        f"## On-screen text\n{ocr}\n"
    )
```

Add to `models.py` `ReelMeta` (referenced by `note_filename`):
```python
    def title_or_caption(self) -> str:
        return (self.caption.strip().splitlines() or ["reel"])[0][:60] or "reel"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_notes.py tests/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add inspiration_pipeline/notes.py inspiration_pipeline/models.py tests/test_notes.py
git commit -m "feat: render reels into vault atomic notes"
```

---

## Task 6: Claude client (boundary)

**Files:**
- Create: `inspiration_pipeline/claude_client.py`
- Test: `tests/test_claude_client.py`

**Interfaces:**
- Consumes: `Config`, `ReelMeta`, `Classification`.
- Produces:
  - `build_prompt(reel: ReelMeta, transcript: str, ocr: str, categories: dict[str,str]) -> str`
  - `classify_reel(config: Config, reel, transcript, ocr, categories, *, runner=subprocess.run) -> Classification` — invokes `[claude_bin, "-p", prompt, "--output-format", "json"]`, parses Claude Code's JSON envelope `{"result": "<text>"}`, extracts the inner JSON object, returns `Classification`. Raises `ClaudeError` on non-zero exit or unparseable output. `runner` param is the injection seam for tests.

- [ ] **Step 1: Write the failing test**

`tests/test_claude_client.py`:
```python
import json
import subprocess

import pytest

from inspiration_pipeline import claude_client as cc
from inspiration_pipeline.models import ReelMeta


def _reel():
    return ReelMeta(pk="1", shortcode="sc1", url="u", author="@a", caption="c",
                    taken_at="2026-06-25", collection="projects")


def _fake_runner(payload, returncode=0):
    def runner(cmd, **kwargs):
        envelope = json.dumps({"result": json.dumps(payload)})
        return subprocess.CompletedProcess(cmd, returncode, stdout=envelope, stderr="")
    return runner


def test_classify_reel_parses_classification(dummy_config):
    payload = {"category": "3d-print", "title": "T", "summary": "S",
               "key_points": ["a"], "domain": "Projects",
               "is_new_category": True, "category_description": "prints"}
    cls = cc.classify_reel(dummy_config, _reel(), "t", "o", {},
                           runner=_fake_runner(payload))
    assert cls.category == "3d-print" and cls.is_new_category is True


def test_classify_reel_nonzero_exit_raises(dummy_config):
    def runner(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")
    with pytest.raises(cc.ClaudeError):
        cc.classify_reel(dummy_config, _reel(), "t", "o", {}, runner=runner)


def test_build_prompt_lists_known_categories():
    prompt = cc.build_prompt(_reel(), "trans", "ocr", {"workout": "exercise"})
    assert "workout" in prompt and "exercise" in prompt and "trans" in prompt
```

Add to `tests/conftest.py`:
```python
from inspiration_pipeline.config import Config


@pytest.fixture
def dummy_config(tmp_path) -> Config:
    return Config(
        collections=["projects"], output_dir=tmp_path / "out",
        queue_dir=tmp_path / "q", db_path=tmp_path / "db.db",
        poll_interval_hours=4.0, whisper_model="large-v3", batch_size=50,
        keep_originals=False, max_attempts=3, dreck_host="h", dreck_user="u",
        dreck_mac="m", dreck_scratch_dir="C:/s", dreck_sleep_cmd="s",
        claude_bin="claude", ig_username="bot", ig_password="pw",
        ig_session_path=tmp_path / "session.json",
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_claude_client.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `inspiration_pipeline/claude_client.py`**

```python
"""Boundary: invoke headless Claude Code to classify a reel."""
import json
import subprocess

from inspiration_pipeline.config import Config
from inspiration_pipeline.models import Classification, ReelMeta

_INSTRUCTIONS = (
    "You classify a saved Instagram reel for a personal knowledge vault.\n"
    "Choose the best category from the known list, or invent a new concise "
    "kebab-case one if none fit (set is_new_category true and give a one-line "
    "category_description). Pick domain: 'Health' for fitness/workout/posture/"
    "physique, 'Projects' for builds/3d-prints/engineering, else 'none'.\n"
    "Respond with ONLY a JSON object: {category, title, summary, key_points "
    "(array of strings), domain, is_new_category, category_description}."
)


class ClaudeError(Exception):
    """Raised when the claude invocation fails or returns unparseable output."""


def build_prompt(
    reel: ReelMeta, transcript: str, ocr: str, categories: dict[str, str]
) -> str:
    known = "\n".join(f"- {n}: {d}" for n, d in categories.items()) or "(none yet)"
    return (
        f"{_INSTRUCTIONS}\n\nKnown categories:\n{known}\n\n"
        f"Reel collection: {reel.collection}\n"
        f"Author: {reel.author}\nCaption: {reel.caption}\n\n"
        f"Transcript:\n{transcript}\n\nOn-screen text:\n{ocr}\n"
    )


def _extract_object(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ClaudeError(f"No JSON object in Claude output: {text!r}")
    return json.loads(text[start : end + 1])


def classify_reel(
    config: Config,
    reel: ReelMeta,
    transcript: str,
    ocr: str,
    categories: dict[str, str],
    *,
    runner=subprocess.run,
) -> Classification:
    """Classify one reel via `claude -p`. `runner` is the test seam."""
    prompt = build_prompt(reel, transcript, ocr, categories)
    cmd = [config.claude_bin, "-p", prompt, "--output-format", "json"]
    proc = runner(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise ClaudeError(f"claude exited {proc.returncode}: {proc.stderr}")
    try:
        envelope = json.loads(proc.stdout)
        inner = envelope["result"] if isinstance(envelope, dict) else proc.stdout
        return Classification.from_json(_extract_object(inner))
    except (json.JSONDecodeError, KeyError) as exc:
        raise ClaudeError(f"Unparseable claude output: {exc}") from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_claude_client.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add inspiration_pipeline/claude_client.py tests/test_claude_client.py tests/conftest.py
git commit -m "feat: claude client for reel classification"
```

---

## Task 7: Filing orchestration

**Files:**
- Create: `inspiration_pipeline/filing.py`
- Test: `tests/test_filing.py`

**Interfaces:**
- Consumes: `Config`, `ReelMeta`, db, categories, notes, claude_client.
- Produces:
  - `file_reel(conn, config, reel, transcript, ocr, video_path: Path, *, classifier=claude_client.classify_reel) -> Path` — reads registry, classifies, appends new category if `is_new_category`, renders + writes the note to `config.output_dir`, purges `video_path` unless `keep_originals`, marks reel filed, returns note path. `classifier` is the test seam.

- [ ] **Step 1: Write the failing test**

`tests/test_filing.py`:
```python
from pathlib import Path

from inspiration_pipeline import db, filing
from inspiration_pipeline.models import Classification, ReelMeta


def _reel(pk="1"):
    return ReelMeta(pk=pk, shortcode=f"sc{pk}", url="u", author="@a",
                    caption="cap", taken_at="2026-06-25", collection="3d prints")


def _classifier(cls):
    def fn(config, reel, transcript, ocr, categories, **kw):
        return cls
    return fn


def test_file_reel_writes_note_purges_video_marks_filed(tmp_path, dummy_config):
    config = dummy_config
    config.output_dir.mkdir(parents=True)
    conn = db.connect(config.db_path)
    db.enqueue(conn, _reel())
    db.mark_transcribed(conn, "1")
    video = tmp_path / "1.mp4"
    video.write_bytes(b"x")
    cls = Classification("3d-print", "Hinge", "s", ["p"], "Projects",
                         is_new_category=True, category_description="prints")
    note_path = filing.file_reel(conn, config, _reel(), "trans", "ocr", video,
                                 classifier=_classifier(cls))
    assert note_path.exists()
    assert "[[Projects]]" in note_path.read_text(encoding="utf-8")
    assert not video.exists()  # purged
    assert db.records_by_status(conn, "filed")[0]["pk"] == "1"
    cats = (config.output_dir / "_categories.md").read_text(encoding="utf-8")
    assert "3d-print" in cats  # new category registered


def test_file_reel_keep_originals(tmp_path, dummy_config):
    config = dummy_config
    object.__setattr__(config, "keep_originals", True)
    config.output_dir.mkdir(parents=True)
    conn = db.connect(config.db_path)
    db.enqueue(conn, _reel())
    video = tmp_path / "1.mp4"
    video.write_bytes(b"x")
    cls = Classification("workout", "W", "s", [], "Health")
    filing.file_reel(conn, config, _reel(), "t", "o", video,
                     classifier=_classifier(cls))
    assert video.exists()  # kept
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_filing.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `inspiration_pipeline/filing.py`**

```python
"""Classify, render, write, and finalize one transcribed reel."""
from datetime import date
from pathlib import Path

from inspiration_pipeline import categories, claude_client, db, notes
from inspiration_pipeline.config import Config
from inspiration_pipeline.models import ReelMeta


def file_reel(
    conn,
    config: Config,
    reel: ReelMeta,
    transcript: str,
    ocr: str,
    video_path: Path,
    *,
    classifier=claude_client.classify_reel,
) -> Path:
    """Turn a transcribed reel into a filed vault note. Returns the note path."""
    registry = config.output_dir / "_categories.md"
    known = categories.read_categories(registry)
    cls = classifier(config, reel, transcript, ocr, known)
    if cls.is_new_category:
        categories.append_category(registry, cls.category, cls.category_description)
    note = notes.render_note(reel, transcript, ocr, cls, date.today().isoformat())
    config.output_dir.mkdir(parents=True, exist_ok=True)
    note_path = config.output_dir / notes.note_filename(reel)
    note_path.write_text(note, encoding="utf-8")
    if not config.keep_originals and video_path.exists():
        video_path.unlink()
    db.mark_filed(conn, reel.pk)
    return note_path
```

> Note: `notes.note_filename` uses `reel.title_or_caption()`; the rendered `# title`
> uses `cls.title`. Filename stays stable (caption-based) even if Claude's title varies.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_filing.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add inspiration_pipeline/filing.py tests/test_filing.py
git commit -m "feat: filing orchestration for a transcribed reel"
```

---

## Task 8: Collector (instagrapi + yt-dlp)

**Files:**
- Create: `inspiration_pipeline/collector.py`
- Test: `tests/test_collector.py`

**Interfaces:**
- Consumes: `Config`, `ReelMeta`, db.
- Produces:
  - `class InstagramSource` with `login()` (session persistence) and `collection_medias(name: str) -> list[ReelMeta]`. Wraps instagrapi; only this class touches instagrapi.
  - `download_reel(url: str, dest_dir: Path, shortcode: str, *, downloader=_ytdlp_download) -> Path`
  - `collect(conn, config, source, *, backlog=False, downloader=...) -> int` — for each configured collection, fetch medias; for each not in `seen_pks` (always, in backlog mode it's the same since seen-set covers it), download + enqueue; returns count enqueued.

- [ ] **Step 1: Write the failing test**

`tests/test_collector.py`:
```python
from pathlib import Path

from inspiration_pipeline import collector, db
from inspiration_pipeline.models import ReelMeta


class FakeSource:
    def __init__(self, by_collection):
        self.by_collection = by_collection

    def collection_medias(self, name):
        return self.by_collection.get(name, [])


def _reel(pk):
    return ReelMeta(pk=pk, shortcode=f"sc{pk}", url=f"u{pk}", author="@a",
                    caption="c", taken_at="2026-06-25", collection="projects")


def test_collect_enqueues_new_and_skips_seen(tmp_path, dummy_config):
    config = dummy_config
    object.__setattr__(config, "collections", ["projects"])
    object.__setattr__(config, "queue_dir", tmp_path / "q")
    conn = db.connect(config.db_path)
    db.enqueue(conn, _reel("1"))  # already seen
    source = FakeSource({"projects": [_reel("1"), _reel("2")]})
    calls = []

    def fake_dl(url, dest_dir, shortcode, **kw):
        calls.append(shortcode)
        p = Path(dest_dir) / f"{shortcode}.mp4"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        return p

    n = collector.collect(conn, config, source, downloader=fake_dl)
    assert n == 1  # only pk 2
    assert calls == ["sc2"]
    assert db.seen_pks(conn) == {"1", "2"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_collector.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `inspiration_pipeline/collector.py`**

```python
"""Poll Instagram collections, download new reels, enqueue them."""
import subprocess
from pathlib import Path

from inspiration_pipeline import db
from inspiration_pipeline.config import Config
from inspiration_pipeline.models import ReelMeta


class InstagramSource:
    """instagrapi wrapper. The only module that imports instagrapi."""

    def __init__(self, config: Config) -> None:
        from instagrapi import Client

        self._config = config
        self._client = Client()

    def login(self) -> None:
        cfg = self._config
        if cfg.ig_session_path.exists():
            self._client.load_settings(cfg.ig_session_path)
        self._client.login(cfg.ig_username, cfg.ig_password)
        self._client.dump_settings(cfg.ig_session_path)

    def collection_medias(self, name: str) -> list[ReelMeta]:
        collections = self._client.collections()
        match = next((c for c in collections if c.name == name), None)
        if match is None:
            return []
        medias = self._client.collection_medias(match.id)
        return [
            ReelMeta(
                pk=str(m.pk), shortcode=m.code,
                url=f"https://www.instagram.com/reel/{m.code}/",
                author=m.user.username, caption=m.caption_text or "",
                taken_at=m.taken_at.date().isoformat(), collection=name,
            )
            for m in medias
        ]


def _ytdlp_download(url: str, dest_dir: Path, shortcode: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"{shortcode}.mp4"
    subprocess.run(
        ["yt-dlp", "-o", str(out), "-f", "mp4", url], check=True,
        capture_output=True, text=True,
    )
    return out


def download_reel(
    url: str, dest_dir: Path, shortcode: str, *, downloader=_ytdlp_download
) -> Path:
    return downloader(url, dest_dir, shortcode)


def collect(conn, config: Config, source, *, backlog: bool = False,
            downloader=_ytdlp_download) -> int:
    """Fetch configured collections, download+enqueue unseen reels.

    backlog only changes intent/logging; the seen-set already makes both
    incremental and full passes idempotent.
    """
    seen = db.seen_pks(conn)
    enqueued = 0
    for name in config.collections:
        for reel in source.collection_medias(name):
            if reel.pk in seen:
                continue
            download_reel(reel.url, config.queue_dir, reel.shortcode,
                          downloader=downloader)
            if db.enqueue(conn, reel):
                enqueued += 1
                seen.add(reel.pk)
    return enqueued
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_collector.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add inspiration_pipeline/collector.py tests/test_collector.py
git commit -m "feat: collector polls collections and enqueues reels"
```

---

## Task 9: dreck remote control

**Files:**
- Create: `inspiration_pipeline/dreck.py`
- Test: `tests/test_dreck.py`

**Interfaces:**
- Consumes: `Config`.
- Produces:
  - `wake(config, *, sender=...) -> None` (magic packet to `dreck_mac`)
  - `wait_for_ssh(config, *, timeout=180, interval=5, runner=subprocess.run, sleep=time.sleep) -> bool`
  - `push(config, local_files: list[Path], *, runner=subprocess.run) -> None` (scp to `dreck_scratch_dir`)
  - `run_transcription(config, *, runner=subprocess.run) -> None` (ssh runs remote `transcribe_ocr.py` over scratch dir)
  - `pull_results(config, local_dir: Path, *, runner=subprocess.run) -> None` (scp `*.json` back)
  - `sleep_host(config, *, runner=subprocess.run) -> None` (ssh runs `dreck_sleep_cmd`)
- All shell out to system `ssh`/`scp`; `runner`/`sender`/`sleep` are the test seams.

- [ ] **Step 1: Write the failing test**

`tests/test_dreck.py`:
```python
import subprocess
from pathlib import Path

from inspiration_pipeline import dreck


def _ok(cmd, **kw):
    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


def test_wake_sends_magic_packet(dummy_config):
    sent = []
    dreck.wake(dummy_config, sender=lambda mac: sent.append(mac))
    assert sent == [dummy_config.dreck_mac]


def test_wait_for_ssh_returns_true_when_reachable(dummy_config):
    runner = lambda cmd, **kw: _ok(cmd)
    assert dreck.wait_for_ssh(dummy_config, timeout=10, runner=runner,
                              sleep=lambda s: None) is True


def test_wait_for_ssh_times_out(dummy_config):
    def fail(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 255, stdout="", stderr="no")
    assert dreck.wait_for_ssh(dummy_config, timeout=0, runner=fail,
                              sleep=lambda s: None) is False


def test_push_builds_scp_command(dummy_config, tmp_path):
    calls = []
    f = tmp_path / "a.mp4"
    f.write_bytes(b"x")
    dreck.push(dummy_config, [f], runner=lambda cmd, **kw: calls.append(cmd) or _ok(cmd))
    assert calls[0][0] == "scp"
    assert f"{dummy_config.dreck_user}@{dummy_config.dreck_host}" in calls[0][-1]


def test_sleep_host_runs_sleep_cmd(dummy_config):
    calls = []
    dreck.sleep_host(dummy_config, runner=lambda cmd, **kw: calls.append(cmd) or _ok(cmd))
    assert dummy_config.dreck_sleep_cmd in " ".join(calls[0])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dreck.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `inspiration_pipeline/dreck.py`**

```python
"""Wake-on-LAN + SSH/SCP control of the dreck GPU box."""
import subprocess
import time
from pathlib import Path

from inspiration_pipeline.config import Config


def _default_sender(mac: str) -> None:
    from wakeonlan import send_magic_packet

    send_magic_packet(mac)


def _target(config: Config) -> str:
    return f"{config.dreck_user}@{config.dreck_host}"


def wake(config: Config, *, sender=_default_sender) -> None:
    sender(config.dreck_mac)


def wait_for_ssh(config: Config, *, timeout: int = 180, interval: int = 5,
                 runner=subprocess.run, sleep=time.sleep) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        proc = runner(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
             _target(config), "echo ok"],
            capture_output=True, text=True,
        )
        if proc.returncode == 0:
            return True
        if time.monotonic() >= deadline:
            return False
        sleep(interval)


def push(config: Config, local_files: list[Path], *, runner=subprocess.run) -> None:
    dest = f"{_target(config)}:{config.dreck_scratch_dir}/"
    for path in local_files:
        proc = runner(["scp", str(path), dest], capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"scp push failed for {path}: {proc.stderr}")


def run_transcription(config: Config, *, runner=subprocess.run) -> None:
    remote = (
        f"python {config.dreck_scratch_dir}/transcribe_ocr.py "
        f"{config.dreck_scratch_dir} --model {config.whisper_model}"
    )
    proc = runner(["ssh", _target(config), remote], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"remote transcription failed: {proc.stderr}")


def pull_results(config: Config, local_dir: Path, *, runner=subprocess.run) -> None:
    local_dir.mkdir(parents=True, exist_ok=True)
    src = f"{_target(config)}:{config.dreck_scratch_dir}/*.json"
    proc = runner(["scp", src, str(local_dir)], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"scp pull failed: {proc.stderr}")


def sleep_host(config: Config, *, runner=subprocess.run) -> None:
    runner(["ssh", _target(config), config.dreck_sleep_cmd],
           capture_output=True, text=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dreck.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add inspiration_pipeline/dreck.py tests/test_dreck.py
git commit -m "feat: dreck WoL/ssh/scp remote control"
```

---

## Task 10: Remote transcribe + OCR script

**Files:**
- Create: `remote/transcribe_ocr.py`, `remote/requirements-dreck.txt`
- Test: `tests/test_remote_transcribe_ocr.py`

**Interfaces:**
- Runs standalone on dreck. Produces `<video_stem>.json` = `{"transcript": str, "ocr": str}` beside each `.mp4` in the scratch dir.
- Testable pure helpers: `dedup_lines(lines: list[str]) -> str`; `process_video(path, transcriber, ocr_fn) -> dict` (transcriber/ocr_fn are the GPU boundaries).

- [ ] **Step 1: Write the failing test**

`tests/test_remote_transcribe_ocr.py`:
```python
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "transcribe_ocr", Path(__file__).parent.parent / "remote" / "transcribe_ocr.py"
)
tx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tx)


def test_dedup_lines_preserves_order_drops_repeats():
    assert tx.dedup_lines(["a", "a", "b", "", "b", "c"]) == "a\nb\nc"


def test_process_video_combines_transcript_and_ocr(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")
    result = tx.process_video(
        video, transcriber=lambda p: "spoken text",
        ocr_fn=lambda p: ["LINE ONE", "LINE ONE", "LINE TWO"],
    )
    assert result == {"transcript": "spoken text", "ocr": "LINE ONE\nLINE TWO"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_remote_transcribe_ocr.py -v`
Expected: FAIL with `FileNotFoundError` / module load error

- [ ] **Step 3: Implement `remote/transcribe_ocr.py` and `remote/requirements-dreck.txt`**

`remote/requirements-dreck.txt`:
```text
faster-whisper>=1.1.0
opencv-python>=4.10.0
pytesseract>=0.3.13
```

`remote/transcribe_ocr.py`:
```python
"""Runs ON dreck (RTX 5090). Transcribe + OCR each mp4 in a dir to <stem>.json."""
import argparse
import json
import sys
from pathlib import Path


def dedup_lines(lines: list[str]) -> str:
    seen: set[str] = set()
    kept: list[str] = []
    for line in lines:
        text = line.strip()
        if text and text not in seen:
            seen.add(text)
            kept.append(text)
    return "\n".join(kept)


def _whisper_transcribe(model_name: str):
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device="cuda", compute_type="float16")

    def transcribe(path: Path) -> str:
        segments, _ = model.transcribe(str(path))
        return " ".join(seg.text.strip() for seg in segments).strip()

    return transcribe


def _frame_ocr(fps: float = 1.0):
    import cv2
    import pytesseract

    def ocr(path: Path) -> list[str]:
        cap = cv2.VideoCapture(str(path))
        native = cap.get(cv2.CAP_PROP_FPS) or 30.0
        step = max(int(native / fps), 1)
        lines: list[str] = []
        idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % step == 0:
                text = pytesseract.image_to_string(frame)
                lines.extend(text.splitlines())
            idx += 1
        cap.release()
        return lines

    return ocr


def process_video(path: Path, transcriber, ocr_fn) -> dict:
    return {"transcript": transcriber(path), "ocr": dedup_lines(ocr_fn(path))}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scratch_dir")
    parser.add_argument("--model", default="large-v3")
    args = parser.parse_args(argv)
    transcriber = _whisper_transcribe(args.model)
    ocr_fn = _frame_ocr()
    scratch = Path(args.scratch_dir)
    for video in scratch.glob("*.mp4"):
        result = process_video(video, transcriber, ocr_fn)
        (scratch / f"{video.stem}.json").write_text(
            json.dumps(result), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_remote_transcribe_ocr.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add remote/transcribe_ocr.py remote/requirements-dreck.txt \
  tests/test_remote_transcribe_ocr.py
git commit -m "feat: remote whisper+ocr transcription script"
```

---

## Task 11: Processor (batch orchestration)

**Files:**
- Create: `inspiration_pipeline/processor.py`
- Test: `tests/test_processor.py`

**Interfaces:**
- Consumes: `Config`, db, dreck, filing.
- Produces:
  - `process(conn, config, *, dreck_mod=dreck, file_fn=filing.file_reel, classifier=None) -> int` — pulls up to `batch_size` `downloaded` records; if none, returns 0. Wakes dreck, waits for SSH (returns 0 on failure, leaving reels queued), pushes videos, runs transcription, pulls JSON, sleeps dreck, then per reel: read JSON → `mark_transcribed` → `file_reel`; on per-reel error `record_failure`. Returns count filed.

- [ ] **Step 1: Write the failing test**

`tests/test_processor.py`:
```python
import json
from pathlib import Path

from inspiration_pipeline import db, processor
from inspiration_pipeline.models import Classification, ReelMeta


def _reel(pk):
    return ReelMeta(pk=pk, shortcode=f"sc{pk}", url="u", author="@a", caption="c",
                    taken_at="2026-06-25", collection="projects")


class FakeDreck:
    def __init__(self, scratch: Path, reachable=True):
        self.scratch = scratch
        self.reachable = reachable

    def wake(self, config):  # noqa: D401
        pass

    def wait_for_ssh(self, config):
        return self.reachable

    def push(self, config, files):
        pass

    def run_transcription(self, config):
        pass

    def pull_results(self, config, local_dir):
        # simulate dreck returning <stem>.json for each queued video
        for video in Path(config.queue_dir).glob("*.mp4"):
            (local_dir / f"{video.stem}.json").write_text(
                json.dumps({"transcript": "T", "ocr": "O"}), encoding="utf-8"
            )

    def sleep_host(self, config):
        pass


def _seed(config):
    config.queue_dir.mkdir(parents=True, exist_ok=True)
    conn = db.connect(config.db_path)
    for pk in ("1", "2"):
        db.enqueue(conn, _reel(pk))
        (config.queue_dir / f"sc{pk}.mp4").write_bytes(b"x")
    return conn


def test_process_files_all_reels(tmp_path, dummy_config):
    config = dummy_config
    object.__setattr__(config, "queue_dir", tmp_path / "q")
    object.__setattr__(config, "output_dir", tmp_path / "out")
    conn = _seed(config)
    cls = Classification("c", "T", "s", [], "Projects")
    n = processor.process(conn, config, dreck_mod=FakeDreck(config.queue_dir),
                          classifier=lambda *a, **k: cls)
    assert n == 2
    assert len(db.records_by_status(conn, "filed")) == 2


def test_process_empty_queue_noop(tmp_path, dummy_config):
    object.__setattr__(dummy_config, "queue_dir", tmp_path / "q")
    conn = db.connect(dummy_config.db_path)
    assert processor.process(conn, dummy_config, dreck_mod=FakeDreck(tmp_path)) == 0


def test_process_dreck_unreachable_leaves_queued(tmp_path, dummy_config):
    config = dummy_config
    object.__setattr__(config, "queue_dir", tmp_path / "q")
    conn = _seed(config)
    n = processor.process(conn, config,
                          dreck_mod=FakeDreck(config.queue_dir, reachable=False))
    assert n == 0
    assert len(db.records_by_status(conn, "downloaded")) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_processor.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `inspiration_pipeline/processor.py`**

```python
"""Batch processor: wake dreck, transcribe, file reels."""
import json
from pathlib import Path

from inspiration_pipeline import db, dreck as dreck_default, filing
from inspiration_pipeline.config import Config
from inspiration_pipeline.models import ReelMeta


def _reel_from_row(row) -> ReelMeta:
    return ReelMeta(
        pk=row["pk"], shortcode=row["shortcode"], url=row["url"],
        author=row["author"], caption=row["caption"],
        taken_at=row["taken_at"], collection=row["collection"],
    )


def process(conn, config: Config, *, dreck_mod=dreck_default,
            file_fn=filing.file_reel, classifier=None) -> int:
    """Transcribe + file up to batch_size queued reels. Returns count filed."""
    rows = db.records_by_status(conn, "downloaded")[: config.batch_size]
    if not rows:
        return 0
    dreck_mod.wake(config)
    if not dreck_mod.wait_for_ssh(config):
        return 0  # leave everything queued; retry next batch
    videos = [config.queue_dir / f"{r['shortcode']}.mp4" for r in rows]
    dreck_mod.push(config, [v for v in videos if v.exists()])
    dreck_mod.run_transcription(config)
    dreck_mod.pull_results(config, config.queue_dir)
    dreck_mod.sleep_host(config)
    filed = 0
    for row in rows:
        reel = _reel_from_row(row)
        try:
            result = _load_result(config.queue_dir / f"{reel.shortcode}.json")
            db.mark_transcribed(conn, reel.pk)
            kwargs = {"classifier": classifier} if classifier else {}
            file_fn(conn, config, reel, result["transcript"], result["ocr"],
                    config.queue_dir / f"{reel.shortcode}.mp4", **kwargs)
            filed += 1
        except Exception as exc:  # noqa: BLE001 - per-reel isolation
            db.record_failure(conn, reel.pk, str(exc), config.max_attempts)
    return filed


def _load_result(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_processor.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add inspiration_pipeline/processor.py tests/test_processor.py
git commit -m "feat: batch processor wires transcription and filing"
```

---

## Task 12: CLI

**Files:**
- Create: `inspiration_pipeline/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_config`, collector, processor, db.
- Produces: `main(argv=None) -> int` with subcommands:
  - `collect [--backlog] [--config PATH]`
  - `process [--config PATH]`
  - Dispatch is injectable via module-level `collect_fn` / `process_fn` for tests, defaulting to the real ones.

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
from inspiration_pipeline import cli


def test_collect_dispatches(monkeypatch, config_files):
    cfg_path, _ = config_files
    called = {}
    monkeypatch.setattr(cli, "_run_collect",
                        lambda config, backlog: called.update(backlog=backlog) or 3)
    rc = cli.main(["collect", "--backlog", "--config", str(cfg_path)])
    assert rc == 0 and called["backlog"] is True


def test_process_dispatches(monkeypatch, config_files):
    cfg_path, _ = config_files
    called = {}
    monkeypatch.setattr(cli, "_run_process",
                        lambda config: called.setdefault("ran", True) or 2)
    rc = cli.main(["process", "--config", str(cfg_path)])
    assert rc == 0 and called["ran"] is True
```

> Note: `config_files` writes `.env` beside the toml, so `load_config` finds secrets.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `inspiration_pipeline/cli.py`**

```python
"""Command-line entrypoints: collect and process."""
import argparse
from pathlib import Path

from inspiration_pipeline import collector, db, processor
from inspiration_pipeline.config import Config, load_config


def _run_collect(config: Config, backlog: bool) -> int:
    conn = db.connect(config.db_path)
    source = collector.InstagramSource(config)
    source.login()
    return collector.collect(conn, config, source, backlog=backlog)


def _run_process(config: Config) -> int:
    conn = db.connect(config.db_path)
    return processor.process(conn, config)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="inspiration")
    parser.add_argument("--config", default="config.toml", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    collect_p = sub.add_parser("collect", help="Poll collections and enqueue reels")
    collect_p.add_argument("--backlog", action="store_true")
    sub.add_parser("process", help="Transcribe and file queued reels")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.command == "collect":
        count = _run_collect(config, args.backlog)
        print(f"Enqueued {count} reel(s)")
    else:
        count = _run_process(config)
        print(f"Filed {count} reel(s)")
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add inspiration_pipeline/cli.py tests/test_cli.py
git commit -m "feat: collect and process CLI"
```

---

## Task 13: Deploy artifacts + README

**Files:**
- Create: `deploy/inspiration-collector.service`, `deploy/inspiration-collector.timer`, `deploy/inspiration-processor.service`, `deploy/inspiration-processor.timer`, `README.md`

**Interfaces:** none (ops + docs). Verification is manual.

- [ ] **Step 1: Write the systemd units (pi4)**

`deploy/inspiration-collector.service`:
```ini
[Unit]
Description=Inspiration Pipeline collector (poll IG collections)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/home/youruser/inspiration-pipeline
ExecStart=/home/youruser/inspiration-pipeline/.venv/bin/inspiration collect
```

`deploy/inspiration-collector.timer`:
```ini
[Unit]
Description=Run inspiration collector every 4h

[Timer]
OnBootSec=10min
OnUnitActiveSec=4h
RandomizedDelaySec=30min

[Install]
WantedBy=timers.target
```

`deploy/inspiration-processor.service`:
```ini
[Unit]
Description=Inspiration Pipeline processor (transcribe + file)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/home/youruser/inspiration-pipeline
ExecStart=/home/youruser/inspiration-pipeline/.venv/bin/inspiration process
```

`deploy/inspiration-processor.timer`:
```ini
[Unit]
Description=Run inspiration processor nightly at 04:00

[Timer]
OnCalendar=*-*-* 04:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 2: Verify unit syntax**

Run: `systemd-analyze verify deploy/inspiration-processor.timer deploy/inspiration-collector.timer`
Expected: no output (valid). (Run on pi4; harmless warnings about `[Install]` in oneshot service are acceptable.)

- [ ] **Step 3: Write `README.md`**

Include: one-paragraph description; the architecture diagram from the spec; **instagrapi/ToS caveat** ("Use a throwaway Instagram account — this uses the unofficial instagrapi API and may get the account actioned. Never your main."); setup steps:
```text
# pi4 (collector + processor + Claude Code)
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e .
cp config.example.toml config.toml   # edit paths/collections/dreck
cp .env.example .env                  # add throwaway IG creds
# ensure `claude` CLI is installed and logged in (subscription) on pi4

# dreck (one-time): copy the remote script + install GPU deps
scp remote/transcribe_ocr.py youruser@your-dreck-host:C:/Users/youruser/insp_scratch/
pip install -r remote/requirements-dreck.txt   # on dreck, with CUDA torch + tesseract

# manual run ("update my reel vault")
inspiration process

# enable schedules
sudo cp deploy/*.service deploy/*.timer /etc/systemd/system/
sudo systemctl enable --now inspiration-collector.timer inspiration-processor.timer
```
Document the `--backlog` first run: `inspiration collect --backlog` then `inspiration process` (repeat nightly; `batch_size` bounds disk).

- [ ] **Step 4: Commit**

```bash
git add deploy/ README.md
git commit -m "docs: deploy units and README with ToS caveat"
```

---

## Self-Review

**Spec coverage:**
- Collector / instagrapi / multi-collection / diff / yt-dlp / backlog → Tasks 8, 12.
- sqlite queue + per-stage timestamps + logging → Task 3.
- Claude-managed categories → Tasks 4, 6, 7.
- Per-reel atomic notes / configurable output dir / cross-links → Tasks 5, 7.
- Transcription + OCR on dreck (5090, off-hours) → Tasks 9, 10, 11, 13 (timer).
- Headless Claude reasoning, no per-token cost → Task 6.
- Delete-after-filing + keep_originals flag + bounded backlog batches → Tasks 7, 11 (batch_size), 13.
- Manual run wakes dreck → Tasks 11, 13 (`inspiration process`).
- Secrets/public-repo safety / MIT / README ToS caveat → Tasks 1, 13.
- Error handling (dreck won't wake, per-reel retry, IG challenge) → Tasks 11 (wake/retry), 3 (record_failure); IG challenge surfaces as a login exception in Task 8's `login()` (logged by the systemd run).
- Testing (unit + one integration on a local sample) → every task's tests; Task 10 covers the local-sample transcription helper end-to-end with boundaries injected.

**Placeholder scan:** none — every step has full code or exact commands.

**Type consistency:** `ReelMeta`/`Classification` fields are consistent across tasks; `file_reel`/`classify_reel`/`collect`/`process` signatures match their consumers; db function names (`mark_transcribed`, `mark_filed`, `record_failure`, `records_by_status`, `seen_pks`, `enqueue`) are used consistently.

**Note:** `notes.note_filename` depends on `ReelMeta.title_or_caption()` added in Task 5 — both live in the same task, so no ordering gap.
