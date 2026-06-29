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
