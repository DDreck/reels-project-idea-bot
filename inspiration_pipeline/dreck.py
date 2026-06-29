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
