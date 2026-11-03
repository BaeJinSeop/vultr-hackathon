"""
Docker-based sandbox. Every agent-generated script runs in a fresh, throwaway
container with no network, strict resource caps, a read-only root filesystem,
a non-root user, and all Linux capabilities dropped.

This is the "Blast Radius Zero" boundary: the orchestrator never runs untrusted
code itself and holds no secrets inside the sandbox.
"""
import tempfile
import time
from pathlib import Path

import docker
from docker.errors import ContainerError, ImageNotFound, NotFound
from docker.types import Ulimit

from .config import get_settings
from .models import ExecResult


class Sandbox:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = docker.from_env()

    def ensure_image(self) -> None:
        """Fail fast with a clear message if the sandbox image isn't built."""
        try:
            self.client.images.get(self.settings.sandbox_image)
        except ImageNotFound as exc:
            raise RuntimeError(
                f"Sandbox image '{self.settings.sandbox_image}' not found. "
                f"Build it first:  docker build -t {self.settings.sandbox_image} ./sandbox"
            ) from exc

    def run(self, code: str) -> ExecResult:
        """Run `code` as /work/main.py inside a locked-down container."""
        s = self.settings

        # Write the script to a host temp dir, mounted read-only into the container.
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "main.py"
            script.write_text(code, encoding="utf-8")

            container = None
            started = time.monotonic()
            timed_out = False
            try:
                container = self.client.containers.run(
                    image=s.sandbox_image,
                    command=["/work/main.py"],
                    detach=True,
                    # ── Containment ──
                    network_disabled=True,          # no exfiltration, no SSRF
                    mem_limit=s.sandbox_memory,      # OOM-kill instead of eating host RAM
                    memswap_limit=s.sandbox_memory,  # disallow swap escape
                    nano_cpus=int(s.sandbox_cpus * 1e9),
                    pids_limit=s.sandbox_pids_limit,  # neutralize fork bombs
                    read_only=True,                   # immutable root FS
                    cap_drop=["ALL"],                 # no Linux capabilities
                    security_opt=["no-new-privileges"],
                    user="10001",                     # non-root
                    # /work holds the script (ro); /tmp is a small writable scratch tmpfs.
                    volumes={tmp: {"bind": "/work", "mode": "ro"}},
                    tmpfs={"/tmp": "rw,size=64m,noexec,nosuid"},
                    working_dir="/work",
                    ulimits=[Ulimit(name="fsize", soft=16_000_000, hard=16_000_000)],
                    environment={},                   # secret hygiene: empty env
                )

                try:
                    res = container.wait(timeout=s.sandbox_timeout_seconds)
                    exit_code = res.get("StatusCode", -1)
                except Exception:
                    # wait() timed out → runaway/infinite loop. Kill it.
                    timed_out = True
                    exit_code = -1
                    try:
                        container.kill()
                    except NotFound:
                        pass

                duration_ms = int((time.monotonic() - started) * 1000)

                stdout = _safe_logs(container, stdout=True, stderr=False)
                stderr = _safe_logs(container, stdout=False, stderr=True)

                killed_oom = False
                try:
                    container.reload()
                    killed_oom = bool(container.attrs.get("State", {}).get("OOMKilled"))
                except Exception:
                    pass

                if timed_out:
                    stderr = (stderr + "\n" if stderr else "") + (
                        f"[sandbox] Killed after {s.sandbox_timeout_seconds}s "
                        f"timeout (possible infinite loop)."
                    )
                if killed_oom:
                    stderr = (stderr + "\n" if stderr else "") + (
                        f"[sandbox] Killed by OOM (exceeded {s.sandbox_memory} memory cap)."
                    )

                return ExecResult(
                    exit_code=exit_code,
                    stdout=_truncate(stdout),
                    stderr=_truncate(stderr),
                    timed_out=timed_out,
                    killed_oom=killed_oom,
                    duration_ms=duration_ms,
                )
            except ContainerError as exc:
                return ExecResult(
                    exit_code=exc.exit_status,
                    stdout="",
                    stderr=_truncate(str(exc.stderr or exc)),
                    timed_out=False,
                    killed_oom=False,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            finally:
                if container is not None:
                    try:
                        container.remove(force=True)  # lifecycle: destroy, always
                    except NotFound:
                        pass


def _safe_logs(container, *, stdout: bool, stderr: bool) -> str:
    try:
        return container.logs(stdout=stdout, stderr=stderr).decode(
            "utf-8", errors="replace"
        )
    except Exception:
        return ""


def _truncate(text: str, limit: int = 6000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]"
