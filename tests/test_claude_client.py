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


def test_classify_reel_malformed_output_raises(dummy_config):
    def runner(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="not json", stderr="")
    with pytest.raises(cc.ClaudeError):
        cc.classify_reel(dummy_config, _reel(), "t", "o", {}, runner=runner)
