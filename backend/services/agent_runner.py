import asyncio
import io
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Callable, Awaitable
from uuid import UUID

import structlog

from services.storage_service import download_bundle

log = structlog.get_logger()

# Persistent venv directory per agent slug
_VENVS_DIR = Path(tempfile.gettempdir()) / "agentshub_venvs"
_VENVS_DIR.mkdir(exist_ok=True)

# Cache: slug → requirements hash
_installed_deps_cache: dict[str, str] = {}

# SDK source file path
_SDK_FILE = Path(__file__).parent.parent / "sdk" / "agentshub.py"


def _requires_playwright(req_file: str) -> bool:
    try:
        with open(req_file) as f:
            return any("playwright" in line.lower() for line in f if not line.strip().startswith("#"))
    except Exception:
        return False


def _hash_file(path: str) -> str:
    import hashlib
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception:
        return ""


def _venv_python(venv_dir: Path) -> str:
    return str(venv_dir / "bin" / "python")


async def _ensure_venv(agent_slug: str) -> Path:
    safe_name = agent_slug.replace("/", "__")
    venv_dir = _VENVS_DIR / safe_name
    if venv_dir.exists() and (venv_dir / "bin" / "python").exists():
        return venv_dir

    log.info("agent_creating_venv", slug=agent_slug)
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "venv", str(venv_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await asyncio.wait_for(proc.communicate(), timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to create venv: {err.decode()[:300]}")
    return venv_dir


async def _install_deps(exec_dir: str, agent_slug: str, venv_dir: Path) -> None:
    req_file = os.path.join(exec_dir, "requirements.txt")
    if not os.path.exists(req_file):
        return

    with open(req_file) as f:
        real_deps = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
    if not real_deps:
        return

    req_hash = _hash_file(req_file)
    if _installed_deps_cache.get(agent_slug) == req_hash:
        log.debug("agent_deps_cached", slug=agent_slug)
        return

    python = _venv_python(venv_dir)
    log.info("agent_installing_deps", slug=agent_slug, count=len(real_deps))
    pip = await asyncio.create_subprocess_exec(
        python, "-m", "pip", "install", "-r", req_file,
        "--quiet", "--disable-pip-version-check",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=exec_dir,
    )
    _, pip_err = await asyncio.wait_for(pip.communicate(), timeout=120)
    if pip.returncode != 0:
        err_text = pip_err.decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"pip install failed: {err_text}")

    if _requires_playwright(req_file):
        log.info("agent_checking_playwright", slug=agent_slug)
        check = await asyncio.create_subprocess_exec(
            python, "-c", "from playwright.sync_api import sync_playwright",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await check.communicate()
        if check.returncode != 0:
            log.info("agent_installing_playwright_browser", slug=agent_slug)
            pw = await asyncio.create_subprocess_exec(
                python, "-m", "playwright", "install", "chromium",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(pw.communicate(), timeout=180)

    _installed_deps_cache[agent_slug] = req_hash


async def run_agent_in_sandbox(
    agent_slug: str,
    owner_wallet: str,
    input_data: dict,
    execution_id: UUID,
    timeout_seconds: int = 30,
    user_secrets: dict | None = None,
    log_callback: Callable[[str], Awaitable[None]] | None = None,
    call_depth: int = 0,
) -> dict:
    """
    Скачивает zip, создаёт venv, ставит deps, запускает агента.
    Стримит stderr через log_callback для live-консоли.
    """
    exec_dir = tempfile.mkdtemp(prefix=f"exec_{execution_id}_")
    try:
        # 1. Скачиваем бандл
        if log_callback:
            await log_callback("[system] Downloading agent bundle...")
        zip_bytes = await download_bundle(owner_wallet, agent_slug)

        # 2. Распаковываем
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            zf.extractall(exec_dir)

        # 3. Инжектим SDK
        if _SDK_FILE.exists():
            shutil.copy(_SDK_FILE, os.path.join(exec_dir, "agentshub.py"))

        # 4. Читаем manifest
        manifest_path = os.path.join(exec_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            raise RuntimeError("manifest.json не найден в бандле")
        with open(manifest_path) as f:
            manifest = json.load(f)
        entrypoint = manifest.get("entrypoint", "agent.py")
        agent_file = os.path.join(exec_dir, entrypoint)

        if not os.path.exists(agent_file):
            raise RuntimeError(f"entrypoint '{entrypoint}' не найден в бандле")

        # 5. Создаём venv и ставим зависимости
        if log_callback:
            await log_callback("[system] Setting up environment...")
        venv_dir = await _ensure_venv(agent_slug)
        await _install_deps(exec_dir, agent_slug, venv_dir)

        python = _venv_python(venv_dir)

        # 6. Формируем env
        env = {
            **os.environ,
            "HIVEMIND_EXECUTION_ID": str(execution_id),
            "HIVEMIND_AGENT_SLUG": agent_slug,
            "HIVEMIND_API_URL": os.environ.get("HIVEMIND_API_URL", "http://localhost:8001"),
            "HIVEMIND_CALL_DEPTH": str(call_depth),
            "PYTHONDONTWRITEBYTECODE": "1",
            "VIRTUAL_ENV": str(venv_dir),
            "PATH": f"{venv_dir / 'bin'}:{os.environ.get('PATH', '')}",
            **(user_secrets or {}),
        }

        if log_callback:
            await log_callback(f"[system] Starting agent: {entrypoint}")

        # 7. Запускаем агента — стримим stderr
        proc = await asyncio.create_subprocess_exec(
            python, agent_file,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=exec_dir,
            env=env,
        )

        # Отправляем input в stdin и закрываем
        proc.stdin.write(json.dumps(input_data).encode())
        await proc.stdin.drain()
        proc.stdin.close()

        # Читаем stderr построчно (live streaming)
        stderr_lines: list[str] = []

        async def read_stderr():
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                stderr_lines.append(text)
                if log_callback:
                    await log_callback(text)

        try:
            await asyncio.wait_for(read_stderr(), timeout=timeout_seconds)
            stdout = await proc.stdout.read()
            await proc.wait()
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise TimeoutError(f"Timeout: agent exceeded {timeout_seconds}s limit")

        if proc.returncode != 0:
            stderr_text = "\n".join(stderr_lines[-10:])
            raise RuntimeError(f"Agent failed (exit {proc.returncode}): {stderr_text[:500]}")

        # 8. Парсим вывод
        output_str = stdout.decode("utf-8", errors="replace").strip()
        if log_callback:
            await log_callback(f"[system] Agent finished (exit 0)")

        if not output_str:
            return {"result": "ok", "note": "Agent produced no output"}
        try:
            return json.loads(output_str)
        except json.JSONDecodeError:
            return {"output": output_str}

    finally:
        shutil.rmtree(exec_dir, ignore_errors=True)
