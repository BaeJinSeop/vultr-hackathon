"""
Docker-based sandbox. Every agent-generated script runs in a fresh, throwaway
container with no network, strict resource caps, a read-only root filesystem,
a non-root user, and all Linux capabilities dropped.

This is the "Blast Radius Zero" boundary: the orchestrator never runs untrusted
code itself and holds no secrets inside the sandbox.
"""
import logging
import time
from functools import lru_cache

import docker
import requests
from docker.errors import ImageNotFound, NotFound
from docker.types import LogConfig, Ulimit

from .config import get_settings
from .models import ExecResult

log = logging.getLogger(__name__)

# Every sandbox container carries this label so leftovers can be found and
# destroyed (e.g. if the orchestrator crashed mid-run).
SANDBOX_LABEL = "brz.sandbox"


@lru_cache
def _docker_client() -> docker.DockerClient:
    # One shared client: creating one per request leaks connections.
    return docker.from_env()


def cleanup_leftovers() -> int:
    """Force-remove any sandbox containers left behind by a previous process."""
    client = _docker_client()
    removed = 0
    for c in client.containers.list(all=True, filters={"label": SANDBOX_LABEL}):
        try:
            c.remove(force=True)
            removed += 1
        except NotFound:
            pass
    return removed


class Sandbox:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = _docker_client()

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
        """Run `code` inside a locked-down container. Blocking; call via a thread."""
        s = self.settings

        if len(code.encode("utf-8")) > s.max_code_bytes:
            return ExecResult(
                exit_code=-1, stdout="",
                stderr=f"[sandbox] Refused: code exceeds {s.max_code_bytes} bytes.",
                timed_out=False, killed_oom=False, duration_ms=0,
            )

        container = None
        started = time.monotonic()
        timed_out = False
        try:
            container = self.client.containers.run(
                image=s.sandbox_image,
                # The code travels as an argv string, not a bind mount: when the
                # orchestrator itself runs in a container, bind-mount paths are
                # resolved on the *host* and would not exist there.
                command=["-c", code],
                detach=True,
                labels={SANDBOX_LABEL: "1"},
                runtime=s.sandbox_runtime or None,  # e.g. "runsc" for gVisor
                # ── Containment ──
                network_mode="none",              # no exfiltration, no SSRF
                mem_limit=s.sandbox_memory,       # OOM-kill instead of eating host RAM
                memswap_limit=s.sandbox_memory,   # disallow swap escape
                nano_cpus=int(s.sandbox_cpus * 1e9),
                pids_limit=s.sandbox_pids_limit,  # neutralize fork bombs
                read_only=True,                   # immutable root FS
                cap_drop=["ALL"],                 # no Linux capabilities
                security_opt=["no-new-privileges"],
                user="10001",                     # non-root
                tmpfs={"/tmp": "rw,size=64m,noexec,nosuid,nodev"},
                working_dir="/tmp",
                ulimits=[Ulimit(name="fsize", soft=16_000_000, hard=16_000_000)],
                # Cap host-side log storage: a print-flood must not fill the host disk.
                log_config=LogConfig(
                    type="json-file", config={"max-size": "1m", "max-file": "1"}
                ),
                # Secret hygiene: no credentials, only harmless runtime hints.
                environment={
                    "HOME": "/tmp",
                    "MPLCONFIGDIR": "/tmp/mpl",
                    "MPLBACKEND": "Agg",
                },
            )

            try:
                res = container.wait(timeout=s.sandbox_timeout_seconds)
                exit_code = res.get("StatusCode", -1)
            except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
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
            except NotFound:
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
        finally:
            if container is not None:
                try:
                    container.remove(force=True)  # lifecycle: destroy, always
                except NotFound:
                    pass
                except Exception:
                    log.exception("Failed to remove sandbox container %s", container.id)


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
