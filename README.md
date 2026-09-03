# DevDesk — Universal Development TUI

**One terminal. Multiple services. Separate live output. Full process control.**

DevDesk is a lightweight, technology-agnostic Terminal User Interface (TUI) for managing and monitoring software projects. It replaces multiple open terminal windows with a single interactive dashboard.

Whether you are running a Django backend, a React frontend, or a FastAPI server, DevDesk orchestrates your entire stack from one unified view.

## 🚀 Key Features

- **Smart Initialization**: `devdesk init` automatically detects your project stack (Django, FastAPI, Node.js, venv) and generates a configuration instantly.
- **Role Detection**: Intelligently categorizes services into "Frontend" and "Backend" panels based on service names and hints.
- **Isolated Live Logs**: Completely separate, bounded log buffers for every service. No more merged frontend/backend output.
- **Technology Agnostic**: Works with any command, any language, and any folder structure.
- **Full Control**: Async start, stop, and restart with real-time status and exit code tracking.
- **API Monitor**: Automatically parses and lists API requests from generic service logs.

## 📦 Installation

DevDesk requires **Python 3.11+**.

### For Global Use (Recommended)
Install using `pipx` to make the `devdesk` command available everywhere:
```bash
pipx install .
```

### For Local Development
```bash
pip install -e .
```

For running tests:
```bash
pip install -e ".[dev]"
pytest
```

## 🛠️ Quick Start

1. **Initialize your project**:
   Go to your project root and run:
   ```bash
   devdesk init
   ```
   DevDesk will scan for `manage.py`, `package.json`, and virtual environments to create a custom `.devdesk/config.toml`.

2. **Launch the Dashboard**:
   ```bash
   devdesk
   ```

## ⚙️ Configuration

A project is recognized by the presence of a `.devdesk/config.toml` file. 

### Example Configuration
```toml
[project]
name = "My Fullstack App"

[services.backend]
command = ["../.venv/bin/python", "manage.py", "runserver"]
directory = "./backend-django"
port = 8000
auto_start = true

[services.frontend]
command = ["npm", "run", "dev"]
directory = "./frontend-react"
port = 3000
auto_start = false
```

- **`directory`**: The working directory for the service (relative to the config file).
- **`command`**: The command list to execute.
- **`auto_start`**: If true, the service starts immediately when the dashboard opens.

## ⌨️ Keyboard Shortcuts

| Key | Action |
| --- | --- |
| **↑ ↓** | Sidebar navigation |
| **Enter** | Select / Open |
| **Tab** | Switch focus between panels |
| **Esc / Backspace** | Back to Dashboard |
| **A** | Start all services |
| **R** | Restart the focused service |
| **S** | Stop the focused service |
| **C** | Clear logs for the focused panel |
| **P** | Pause / resume logs |
| **L** | Follow latest logs |
| **[ / ]** | Cycle dashboard panels across extra services |
| **Q** | Quit (gracefully stops all child processes) |

## 🏗️ Architecture

DevDesk follows a strict separation of concerns:
- **UI**: Textual-based dashboard and widgets.
- **Managers**: Orchestrate services, projects, and logs.
- **Process Layer**: Low-level asynchronous process control using `asyncio`.

Logs are kept in bounded buffers (default 2,000 lines) to ensure the application remains lightweight and responsive even with high-output services.

## 📁 Settings

Application settings are stored at `~/.config/devdesk/settings.toml`:
- `log_buffer_size`: Number of lines to keep per service.
- `auto_follow_logs`: Automatically scroll to the end on new output.
- `confirm_before_stop`: Prompt before stopping active services on exit.
- `auto_start_on_open`: Start services as soon as a project is loaded.
