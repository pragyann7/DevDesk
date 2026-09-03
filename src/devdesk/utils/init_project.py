"""Helper to initialize a new .devdesk/config.toml file with smart detection."""

from __future__ import annotations

from pathlib import Path


import sys

def init_project(root: Path) -> tuple[Path, list[str]]:
    """Create .devdesk/config.toml in the given directory if it doesn't exist."""
    devdesk_dir = root / ".devdesk"
    config_file = devdesk_dir / "config.toml"

    if config_file.exists():
        raise FileExistsError(f"DevDesk configuration already exists at {config_file}")

    devdesk_dir.mkdir(parents=True, exist_ok=True)

    project_name = root.resolve().name
    sections = [f'[project]\nname = "{project_name}"\n']

    # 1. Look for Backend (Django / Python / Node)
    backend_info = _detect_backend(root)
    if backend_info:
        sections.append(_build_backend_section(backend_info))

    # 2. Look for Frontend (Node / Package.json)
    frontend_info = _detect_frontend(root)
    if frontend_info:
        sections.append(_build_frontend_section(frontend_info))

    # Fallback if nothing detected
    if not backend_info and not frontend_info:
        sections.append(_build_generic_template())

    config_file.write_text("\n".join(sections), encoding="utf-8")

    # Final warnings/tips for the user
    messages = [f"Initialized DevDesk project at {config_file}"]

    if backend_info and "bin" not in backend_info["cmd"] and "Scripts" not in backend_info["cmd"] and "python" in backend_info["cmd"]:
        messages.append("  [!] No virtual environment (.venv/venv) detected. Using system 'python'.")
        messages.append("      Recommendation: Create a venv for better isolation.")

    return config_file, messages


def _detect_backend(root: Path) -> dict[str, str] | None:
    """Scan root and children for common backend indicators."""
    candidates = [root] + [d for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")]

    for path in candidates:
        rel = path.relative_to(root)
        python_bin = _find_python_in_venv(path, root) or "python"

        # 1. Django
        if (path / "manage.py").is_file():
            return {
                "name": "backend",
                "dir": "." if rel == Path(".") else str(rel),
                "cmd": f'["{python_bin}", "manage.py", "runserver"]',
                "port": "8000"
            }

        # 2. FastAPI / Flask
        for entry in ("main.py", "app.py", "server.py"):
            if (path / entry).is_file():
                content = (path / entry).read_text(errors="replace")
                if "FastAPI" in content:
                    app_name = "main:app" if entry == "main.py" else f"{entry[:-3]}:app"
                    return {
                        "name": "api",
                        "dir": "." if rel == Path(".") else str(rel),
                        "cmd": f'["{python_bin}", "-m", "uvicorn", "{app_name}", "--reload"]',
                        "port": "8000"
                    }
                elif "Flask" in content:
                    return {
                        "name": "backend",
                        "dir": "." if rel == Path(".") else str(rel),
                        "cmd": f'["{python_bin}", "-m", "flask", "run"]',
                        "port": "5000"
                    }

        # 3. Node.js Backend
        if (path / "package.json").is_file():
            import json
            try:
                with (path / "package.json").open("r") as f:
                    pkg = json.load(f)
                deps = pkg.get("dependencies", {})
                if any(k in deps for k in ("express", "koa", "nest", "fastify", "hapi")):
                    cmd = '["npm", "run", "dev"]' if "dev" in pkg.get("scripts", {}) else '["npm", "start"]'
                    return {
                        "name": "backend",
                        "dir": "." if rel == Path(".") else str(rel),
                        "cmd": cmd,
                        "port": "3000"
                    }
            except Exception:
                pass
    return None


def _detect_frontend(root: Path) -> dict[str, str] | None:
    """Scan root and children for package.json, avoiding duplicates with backend."""
    candidates = [root] + [d for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")]

    for path in candidates:
        if path.name in ("venv", "env", "node_modules"): continue
        if (path / "package.json").is_file():
            import json
            try:
                with (path / "package.json").open("r") as f:
                    pkg = json.load(f)
                deps = pkg.get("dependencies", {})
                dev_deps = pkg.get("devDependencies", {})
                is_frontend = any(k in deps for k in ("react", "vue", "svelte", "next", "nuxt", "@angular/core"))

                # Check for Vite to use correct default port
                port = "5173" if "vite" in deps or "vite" in dev_deps else "3000"

                if is_frontend or path.name.lower() in ("frontend", "web", "ui", "client"):
                    rel = path.relative_to(root)
                    cmd = '["npm", "run", "dev"]' if "dev" in pkg.get("scripts", {}) else '["npm", "start"]'
                    return {
                        "name": "frontend",
                        "dir": "." if rel == Path(".") else str(rel),
                        "cmd": cmd,
                        "port": port
                    }
            except Exception:
                pass
    return None


def _find_python_in_venv(base: Path, root: Path) -> str | None:
    """Look for python in .venv or venv, returning path relative to the service directory (base)."""
    bin_dir = "Scripts" if sys.platform == "win32" else "bin"
    exe_name = "python.exe" if sys.platform == "win32" else "python"

    for name in (".venv", "venv", "env"):
        # 1. Check in the service directory (e.g. backend/.venv)
        check_path = base / name / bin_dir / exe_name
        if check_path.is_file():
            return f"./{name}/{bin_dir}/{exe_name}"

        # 2. Check in the project root (common for shared venv)
        check_path = root / name / bin_dir / exe_name
        if check_path.is_file():
            if base == root:
                return f"./{name}/{bin_dir}/{exe_name}"
            # Need to go up from base to root
            return f"../{name}/{bin_dir}/{exe_name}"

    return None


def _build_backend_section(info: dict[str, str]) -> str:
    return f"""[services.{info['name']}]
command = {info['cmd']}
directory = "{info['dir']}"
port = {info['port']}
auto_start = false
"""


def _build_frontend_section(info: dict[str, str]) -> str:
    return f"""[services.{info['name']}]
command = {info['cmd']}
directory = "{info['dir']}"
port = {info['port']}
auto_start = false
"""


def _build_generic_template() -> str:
    return """# No services automatically detected.
# Adjust the examples below to match your project.

[services.backend]
command = ["echo", "Starting backend..."]
directory = "."
port = 8000
auto_start = true
"""
