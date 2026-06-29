import subprocess
from pathlib import Path

import pytest

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


def test_run_transcription_raises_on_failure(dummy_config):
    def runner(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="fail")
    with pytest.raises(RuntimeError):
        dreck.run_transcription(dummy_config, runner=runner)


def test_pull_results_builds_scp_glob(dummy_config, tmp_path):
    calls = []
    dreck.pull_results(
        dummy_config, tmp_path,
        runner=lambda cmd, **kw: calls.append(cmd) or _ok(cmd),
    )
    assert calls[0][0] == "scp"
    assert "*.json" in calls[0][1]
    assert str(tmp_path) == calls[0][2]


def test_clear_scratch_removes_json_and_mp4(dummy_config):
    calls = []
    dreck.clear_scratch(
        dummy_config,
        runner=lambda cmd, **kw: calls.append(cmd) or _ok(cmd),
    )
    cmd_str = " ".join(calls[0])
    scratch = dummy_config.dreck_scratch_dir.replace("/", "\\")
    assert "*.json" in cmd_str
    assert "*.mp4" in cmd_str
    assert scratch in cmd_str
