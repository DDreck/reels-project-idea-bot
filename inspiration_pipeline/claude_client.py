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
    """Build a prompt for Claude to classify a reel.

    Args:
        reel: The reel metadata.
        transcript: The reel's transcript from speech-to-text.
        ocr: On-screen text extracted from the reel.
        categories: Known categories as {name: description}.

    Returns:
        A prompt string ready to pass to Claude.
    """
    known = "\n".join(f"- {n}: {d}" for n, d in categories.items()) or "(none yet)"
    return (
        f"{_INSTRUCTIONS}\n\nKnown categories:\n{known}\n\n"
        f"Reel collection: {reel.collection}\n"
        f"Author: {reel.author}\nCaption: {reel.caption}\n\n"
        f"Transcript:\n{transcript}\n\nOn-screen text:\n{ocr}\n"
    )


def _extract_object(text: str) -> dict:
    """Extract the first JSON object from text.

    Args:
        text: Text that may contain a JSON object.

    Returns:
        The parsed JSON object.

    Raises:
        ClaudeError: If no JSON object is found.
    """
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
    """Classify one reel via `claude -p`. `runner` is the test seam.

    Args:
        config: Configuration with claude_bin path.
        reel: The reel to classify.
        transcript: Speech-to-text output.
        ocr: On-screen text.
        categories: Known categories.
        runner: Callable for subprocess invocation (for testing).

    Returns:
        A Classification object.

    Raises:
        ClaudeError: If claude exited non-zero or output is unparseable.
    """
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
