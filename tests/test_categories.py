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
