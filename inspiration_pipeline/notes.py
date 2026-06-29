"""Pure rendering of a reel into a vault atomic note."""
import re

from inspiration_pipeline.models import Classification, ReelMeta

_CROSSLINK = {"Health": "[[Health]]", "Projects": "[[Projects]]"}


def _slug(text: str) -> str:
    text = re.sub(r"[^a-z0-9\s-]", "", text.lower())
    return re.sub(r"[\s_-]+", "-", text).strip("-")


def note_filename(reel: ReelMeta) -> str:
    """Return the vault filename for a reel note.

    Args:
        reel: Reel metadata used to build the filename.

    Returns:
        A string like ``<date>-<slug>-<shortcode>.md``.
    """
    return f"{reel.taken_at}-{_slug(reel.title_or_caption())}-{reel.shortcode}.md"


def _yaml_tags(cls: Classification) -> str:
    tags = ["inspiration", cls.category]
    return "[" + ", ".join(f'"{t}"' for t in tags) + "]"


def render_note(
    reel: ReelMeta, transcript: str, ocr: str, cls: Classification, filed_date: str
) -> str:
    """Render a reel into a Markdown vault note.

    Args:
        reel: Reel metadata (URL, author, date, etc.).
        transcript: Speech-to-text output for the reel.
        ocr: On-screen text extracted from the reel.
        cls: Classification produced by Claude.
        filed_date: ISO date the note was filed.

    Returns:
        A Markdown string with YAML front-matter ready to write to disk.
    """
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
