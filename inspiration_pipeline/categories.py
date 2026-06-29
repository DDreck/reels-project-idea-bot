"""Read/append the Claude-managed category registry (_categories.md)."""
import re
from pathlib import Path

_HEADER = (
    "# Inspiration Categories\n\n"
    "Claude-managed. New categories are appended automatically.\n\n"
    "| category | description |\n| --- | --- |\n"
)
_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|\s*$")


def read_categories(path: Path) -> dict[str, str]:
    """Read the category registry from a markdown table.

    Args:
        path: Path to the _categories.md file.

    Returns:
        Dictionary mapping category name to description. Empty dict if file
        doesn't exist.
    """
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
    """Append a category to the registry, creating file if needed.

    Args:
        path: Path to the _categories.md file.
        name: Category name.
        description: Category description.

    If the category already exists, this is a no-op.
    """
    existing = read_categories(path)
    if name in existing:
        return
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_HEADER, encoding="utf-8")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"| {name} | {description} |\n")
