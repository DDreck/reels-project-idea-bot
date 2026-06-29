from inspiration_pipeline.models import Classification, ReelMeta
from inspiration_pipeline.notes import note_filename, render_note


def _reel():
    return ReelMeta(pk="1", shortcode="sc1", url="http://x/1", author="@a",
                    caption="Print In Place Hinge", taken_at="2026-06-25", collection="3d prints")


def _cls(domain="Projects"):
    return Classification(category="3d-print", title="Print In Place Hinge",
                          summary="A hinge.", key_points=["no supports", "PLA"],
                          domain=domain)


def test_render_note_contains_frontmatter_and_sections():
    note = render_note(_reel(), "spoken words", "ON SCREEN", _cls(), "2026-06-28")
    assert "source: instagram-reel" in note
    assert 'url: "http://x/1"' in note
    assert 'category: "3d-print"' in note
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
