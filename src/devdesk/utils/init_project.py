"""Helper to initialize a new .devdesk/config.toml file with smart detection."""

from __future__ import annotations

from pathlib import Path


def init_project(root: Path) -> Path:
    """Create .devdesk/config.toml in the given directory if it doesn't exist."""
    devdesk_dir = root / ".devdesk"
    config_file = devdesk_dir / "config.toml"

    if config_file.exists():
        raise FileExistsError(f"DevDesk configuration already exists at {config_file}")

    devdesk_dir.mkdir(parents=True, exist_ok=True)

    project_name = root.resolve().name
    sections = [f'[project]\nname = "{project_name}"\n']

    # 1. Look for Backend (Django / Python)
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

    if backend_info and "python" in backend_info["cmd"] and "bin" not in backend_info["cmd"]:
        messages.append("  [!] No virtual environment (.venv/venv) detected. Using system 'python'.")
        messages.append("      Recommendation: Create a venv for better isolation.")

    return config_file, messages


def _detect_backend(root: Path) -> dict[str, str] | None:
    """Scan root and children for common backend indicators."""
    candidates = [root] + [d for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")]

    for path in candidates:
        # 1. Django
        if (path / "manage.py").is_file():
            rel = path.relative_to(root)
            venv = _find_venv(path, root)
            python_bin = f"{venv}/python" if venv else "python"
            return {
                "name": "backend",
                "dir": "." if rel == Path(".") else str(rel),
                "cmd": f'["{python_bin}", "manage.py", "runserver"]',
                "port": "8000"
            }

        # 2. FastAPI / Flask / Generic Python
        # Look for main.py or app.py
        for entry in ("main.py", "app.py", "server.py"):
            file_path = path / entry
            if file_path.is_file():
                content = file_path.read_text(errors="replace")
                rel = path.relative_to(root)
                venv = _find_venv(path, root)
                python_bin = f"{venv}/python" if venv else "python"

                if "FastAPI" in content:
                    # Likely FastAPI
                    app_name = "main:app" if entry == "main.py" else f"{entry[:-3]}:app"
                    return {
                        "name": "api",
                        "dir": "." if rel == Path(".") else str(rel),
                        "cmd": f'["{python_bin}", "-m", "uvicorn", "{app_name}", "--reload"]',
                        "port": "8000"
                    }
                elif "Flask" in content:
                    # Likely Flask
                    return {
                        "name": "backend",
                        "dir": "." if rel == Path(".") else str(rel),
                        "cmd": f'["{python_bin}", "-m", "flask", "run"]',
                        "port": "5000"
                    }

        # 3. Node.js Backend (if not already picked up by frontend detector)
        if (path / "package.json").is_file():
            # Check for backend indicators in package.json
            import json
            try:
                with (path / "package.json").open("r") as f:
                    pkg = json.load(f)

                deps = pkg.get("dependencies", {})
                dev_deps = pkg.get("devDependencies", {})
                scripts = pkg.get("scripts", {})

                is_backend = any(k in deps for k in ("express", "koa", "nest", "fastify", "hapi"))

                if is_backend:
                    rel = path.relative_to(root)
                    cmd = '["npm", "start"]'
                    if "dev" in scripts:
                        cmd = '["npm", "run", "dev"]'

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
        if path.name in ("venv", "env", "node_modules"):
            continue

        if (path / "package.json").is_file():
            import json
            try:
                with (path / "package.json").open("r") as f:
                    pkg = json.load(f)

                deps = pkg.get("dependencies", {})
                # If it has react, vue, svelte, next, nuxt, it's definitely frontend
                is_frontend = any(k in deps for k in ("react", "vue", "svelte", "next", "nuxt", "@angular/core"))

                # If it's NOT explicitly a backend-heavy node project, assume it's frontend
                # (or if it's in a folder named 'frontend', 'web', 'ui')
                if is_frontend or path.name.lower() in ("frontend", "web", "ui", "client"):
                    rel = path.relative_to(root)
                    return {
                        "name": "frontend",
                        "dir": "." if rel == Path(".") else str(rel),
                        "cmd": '["npm", "run", "dev"]' if "dev" in pkg.get("scripts", {}) else '["npm", "start"]',
                        "port": "3000"
                    }
            except Exception:
                pass

    return None


def _find_venv(base: Path, root: Path) -> str | None:
    """Look for .venv or venv in base or parent."""
    for name in (".venv", "venv", "env"):
        # Check inside the service folder
        if (base / name).is_dir():
            return f"./{name}/bin" if base == root else f"./{base.name}/{name}/bin"
        # Check in the root workspace
        if (root / name).is_dir():
            if base == root:
                return f"./{name}/bin"
            return f"../{name}/bin"
    return None


def _build_backend_section(info: dict[str, str]) -> str:
    return f"""[services.{info['name']}]
command = {info['cmd']}
directory = "{info['dir']}"
port = {info['port']}
auto_start = true
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
