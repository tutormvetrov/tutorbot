from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_root() -> Path:
    raw_root = str(os.getenv("TUTORBOT_ROOT", "")).strip()
    if raw_root:
        return Path(raw_root).expanduser().resolve()
    return PROJECT_ROOT


def load_project_env(root: Path | None = None) -> Path:
    root = root or resolve_root()
    env_file = root / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    os.environ.setdefault("TUTORBOT_ROOT", str(root))
    return root


def resolve_path(raw_path: str | Path, root: Path) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (root / path).resolve()


def require_env(name: str) -> str:
    value = str(os.getenv(name, "")).strip()
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def get_service_name() -> str:
    return str(os.getenv("TUTORBOT_SERVICE_NAME", "tutorbot")).strip() or "tutorbot"


def get_systemd_scope() -> str:
    return str(os.getenv("TUTORBOT_SYSTEMD_SCOPE", "system")).strip() or "system"


def get_systemctl_scope_args(scope: str | None = None) -> list[str]:
    return ["--user"] if (scope or get_systemd_scope()) == "user" else ["--system"]


def find_venv_python(root: Path, env_name: str = ".venv") -> Path:
    candidates = (
        root / env_name / "bin" / "python",
        root / env_name / "Scripts" / "python.exe",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path(sys.executable)


def resolve_command(command: str) -> str | None:
    return shutil.which(command)


def command_exists(command: str) -> bool:
    return resolve_command(command) is not None


def prepare_command(command: list[str]) -> list[str]:
    resolved = resolve_command(command[0]) or command[0]
    suffix = Path(resolved).suffix.lower()
    if os.name == "nt" and suffix in {".cmd", ".bat"}:
        comspec = os.environ.get("ComSpec") or str(Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32" / "cmd.exe")
        return [comspec, "/c", resolved, *command[1:]]
    return [resolved, *command[1:]]


def run_command(command: list[str], **kwargs):
    return subprocess.run(prepare_command(command), **kwargs)


def popen_command(command: list[str], **kwargs):
    return subprocess.Popen(prepare_command(command), **kwargs)


def is_bot_running(root: Path, *, service_name: str | None = None, systemd_scope: str | None = None) -> bool:
    resolved_service_name = service_name or get_service_name()
    resolved_scope = systemd_scope or get_systemd_scope()

    if command_exists("systemctl"):
        result = run_command(
            [
                "systemctl",
                *get_systemctl_scope_args(resolved_scope),
                "is-active",
                "--quiet",
                f"{resolved_service_name}.service",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True

    if command_exists("pgrep"):
        app_marker = str(root / "app.py")
        result = run_command(
            ["pgrep", "-af", app_marker],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and app_marker in result.stdout:
            return True

    return False
