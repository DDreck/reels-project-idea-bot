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
    """Send a Wake-on-LAN magic packet to the dreck host.

    Args:
        config: Configuration with dreck_mac.
        sender: Callable that sends the magic packet (test seam).
    """
    sender(config.dreck_mac)


def wait_for_ssh(config: Config, *, timeout: int = 180, interval: int = 5,
                 runner=subprocess.run, sleep=time.sleep) -> bool:
    """Poll SSH until the dreck host responds or the timeout expires.

    Args:
        config: Configuration with dreck host/user.
        timeout: Maximum seconds to wait before giving up.
        interval: Seconds between probe attempts.
        runner: Subprocess runner (test seam).
        sleep: Sleep callable (test seam).

    Returns:
        True if SSH became reachable, False if timeout expired.
    """
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
    """Copy local files to the dreck scratch directory via scp.

    Args:
        config: Configuration with dreck host/user/scratch_dir.
        local_files: Paths to copy.
        runner: Subprocess runner (test seam).

    Raises:
        RuntimeError: If any scp transfer exits non-zero.
    """
    dest = f"{_target(config)}:{config.dreck_scratch_dir}/"
    for path in local_files:
        proc = runner(["scp", str(path), dest], capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"scp push failed for {path}: {proc.stderr}")


def run_transcription(config: Config, *, runner=subprocess.run) -> None:
    """Run transcribe_ocr.py on the dreck host over SSH.

    Args:
        config: Configuration with dreck host/user/scratch_dir/whisper_model.
        runner: Subprocess runner (test seam).

    Raises:
        RuntimeError: If the remote command exits non-zero.
    """
    remote = (
        f'"{config.dreck_python}" "{config.dreck_scratch_dir}/transcribe_ocr.py" '
        f'"{config.dreck_scratch_dir}" --model "{config.whisper_model}"'
    )
    proc = runner(["ssh", _target(config), remote], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"remote transcription failed: {proc.stderr}")


def pull_results(config: Config, local_dir: Path, *, runner=subprocess.run) -> None:
    """Download JSON results from dreck's scratch dir to local_dir via scp.

    Args:
        config: Configuration with dreck host/user/scratch_dir.
        local_dir: Local directory to receive the JSON files.
        runner: Subprocess runner (test seam).

    Raises:
        RuntimeError: If scp exits non-zero.
    """
    local_dir.mkdir(parents=True, exist_ok=True)
    src = f"{_target(config)}:{config.dreck_scratch_dir}/*.json"
    proc = runner(["scp", src, str(local_dir)], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"scp pull failed: {proc.stderr}")


def sleep_host(config: Config, *, runner=subprocess.run) -> None:
    """Send the sleep command to the dreck host over SSH.

    Args:
        config: Configuration with dreck host/user/sleep_cmd.
        runner: Subprocess runner (test seam).
    """
    runner(["ssh", _target(config), config.dreck_sleep_cmd],
           capture_output=True, text=True)


def clear_scratch(config: Config, *, runner=subprocess.run) -> None:
    """Remove leftover JSON and MP4 files from dreck's scratch directory.

    Args:
        config: Configuration with dreck host/user/scratch_dir.
        runner: Subprocess runner (test seam). Non-zero exit is ignored
            (del on an empty dir is benign).
    """
    scratch = config.dreck_scratch_dir.replace("/", "\\")
    cmd = f'del /q "{scratch}\\*.json" "{scratch}\\*.mp4"'
    runner(["ssh", _target(config), cmd], capture_output=True, text=True)
