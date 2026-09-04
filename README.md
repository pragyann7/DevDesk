# DevDesk — High-Performance Universal Development TUI

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-39%20passed-brightgreen.svg)]()

> **One terminal. All your services. Clean isolated output. Full process control.**

**DevDesk** is a modern, lightweight, technology-agnostic Terminal User Interface (TUI) designed to orchestrate and monitor multi-service development stacks. It replaces cluttered terminal windows, messy tmux panes, and tangled logs with a unified, high-FPS developer workspace right in your console.

Whether running a React/Vite frontend, a Django or FastAPI backend, background workers, or microservices, DevDesk gives you complete control over your application stack from a single terminal.

---

## 📸 Overview

- **Dual-Pane Real-Time Dashboard**: Monitor frontend and backend services simultaneously in isolated, high-performance log viewports.
- **Reverse-Chronological Log Streaming**: Newest log lines are pinned at the top (Line 0) and flow downwards, keeping critical output instantly visible without manual scrolling.
- **Intelligent Error-Aware Highlighting**: Normal log output glows in a clean accent blue (`#173151`), while HTTP `4xx`/`5xx` error codes and unhandled exceptions are automatically highlighted in soft red (`#321418`).
- **Interactive In-App Config Editor**: Edit and validate your project's `.devdesk/config.toml` directly inside the TUI with TOML syntax validation and live hot-reloading (`Ctrl+S`).
- **Real-Time API Monitor & Live Response Fetcher**: Inspect incoming HTTP requests, extract URL query parameters, view parsed request/response JSON, or test endpoints directly with the built-in **Fetch Live Response (`f`)** tool.
- **Zero-Lag `SmoothLog` Engine**: Optimized 25 FPS batched rendering engine that isolates child process streams (`stdin = /dev/null`), strips corrupting ANSI sequences, and prevents terminal input hijacking.
- **Context-Aware Keyboard Navigation**: Seamless navigation with arrow keys, `Enter`/`Right`, and `Esc` (which acts as a smart Back button / Sidebar toggle).

---

## 💻 Installation & Setup

DevDesk requires **Python 3.11 or newer** and works on **macOS**, **Linux**, and **Windows (WSL2 or PowerShell)**.

### Option 1: Local Setup from Source (Recommended)

1. **Clone the repository**:
   ```bash
   git clone https://github.com/pragyann7/DevDesk.git
   cd DevDesk
   ```

2. **Create and activate a virtual environment**:
   - **macOS / Linux**:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```
   - **Windows (PowerShell)**:
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```

3. **Install dependencies in editable mode**:
   ```bash
   pip install --upgrade pip
   pip install -e .
   ```

4. **Launch DevDesk**:
   ```bash
   devdesk
   ```
   *(Or run via `python -m devdesk`)*

---

### Option 2: Global Installation via `pipx`

To make the `devdesk` command accessible globally from any terminal directory:

```bash
# Install pipx if not already installed
pip install pipx
pipx ensurepath

# Install DevDesk directly from source directory
pipx install /path/to/DevDesk
```

---

## 🚀 Quick Start Guide

### 1. Initialize a Project

Navigate to your existing application root directory (where your frontend, backend, or repositories reside):

```bash
cd /path/to/my-project
devdesk init
```

DevDesk automatically scans your directory structure for project indicators (`manage.py`, `package.json`, `pyproject.toml`, virtual environments) and generates a tailored `.devdesk/config.toml` configuration.

### 2. Launch DevDesk

From your project root, start the dashboard:

```bash
devdesk
```

You will enter the interactive dashboard. Press **`A`** to start all services, or press **`Esc`** to focus the sidebar and navigate with your arrow keys.

---

## ⚙️ Project Configuration (`.devdesk/config.toml`)

Every DevDesk project is defined by a simple TOML configuration file located at `.devdesk/config.toml`:

```toml
[project]
name = "Fullstack Storefront"

[services.backend]
command = ["../.venv/bin/python", "manage.py", "runserver", "8000"]
directory = "./backend"
port = 8000
auto_start = true

[services.frontend]
command = ["npm", "run", "dev"]
directory = "./frontend"
port = 5173
auto_start = true

[services.worker]
command = ["celery", "-A", "core", "worker", "-l", "info"]
directory = "./backend"
auto_start = false
```

### Configuration Options

| Field | Type | Description |
|---|---|---|
| `[project].name` | `string` | Human-readable name of your project. |
| `command` | `list[string]` | The exact command arguments to execute (e.g. `["npm", "run", "dev"]`). |
| `directory` | `string` | The working directory relative to the config file. |
| `port` | `integer` | *(Optional)* The service's network port (1–65535). DevDesk can also auto-detect this from runtime startup logs. |
| `auto_start` | `boolean` | If `true`, the service starts automatically when DevDesk launches. |

> **Tip**: You can edit this file at any time without leaving DevDesk! In the sidebar, select **Configure Project** (or press `Enter` on it) to open the built-in TOML editor, make changes, and press `Ctrl+S` to save and hot-reload.

---

## ⌨️ Keyboard & Mouse Controls

DevDesk is built for keyboard-first developers while remaining fully mouse-accessible.

| Key | Action | Context |
|---|---|---|
| **`Esc`** | **Back / Sidebar Toggle** | In a modal: closes it. In sub-views: returns to Dashboard. In Dashboard: toggles focus between Sidebar and Logs. |
| **`↑` / `↓`** | **Navigate Items** | Moves selection in the sidebar or scrolls log history. |
| **`Enter` / `→`** | **Open / Focus View** | Selects the highlighted sidebar item and shifts focus into its viewport. |
| **`A`** | **Start All** | Starts all configured services. |
| **`R`** | **Restart Selected** | Restarts the focused service process. |
| **`S`** | **Stop Selected** | Gracefully stops the focused service process. |
| **`C`** | **Clear Focused Log** | Clears the log display for the currently active panel. |
| **`Shift+C`** | **Clear All Logs** | Wipes log buffers across all services and resets all viewports. |
| **`P`** | **Pause / Resume** | Temporarily pauses incoming log output for careful inspection. |
| **`L`** | **Follow Logs** | Re-pins view to the top line to track incoming output. |
| **`[` / `]`** | **Cycle Panels** | Switches visible services on the dashboard when running 3+ services. |
| **`f`** | **Fetch Live Response** | *(Inside API Monitor Detail Modal)* Queries local backend and renders live JSON. |
| **`Ctrl+S`** | **Save & Reload** | *(Inside Project Config Editor)* Validates TOML, saves to disk, and reloads project state. |
| **`Q`** | **Quit DevDesk** | Gracefully shuts down all child processes and exits. |

---

## 🌐 API Monitor & Request Inspection

DevDesk includes an automated API traffic detector that parses HTTP logs:

1. **Traffic Table**: Automatically logs `TIME`, `SERVICE`, `METHOD`, `ENDPOINT`, `STATUS`, `DURATION`, and `DATA` indicators (`params`, `req`, `res`, `req+res`).
2. **Request Detail Modal**: Press `Enter` on any request row to view complete metadata, URL query parameters, request bodies, and response payloads.
3. **Fetch Live Response**: When inspecting a `GET` request, press **`f`** or click **`[Fetch Live Response (f)]`**. DevDesk will query your local running server (e.g. `http://127.0.0.1:8000/api/endpoint/`) and display the live, pretty-printed JSON response directly inside the modal.

---

## 🧪 Running the Test Suite

DevDesk includes a full automated test suite covering process lifecycle, high-volume log throughput, configuration schema, and UI navigation:

```bash
# Install development and testing dependencies
pip install -e ".[dev]"

# Run full test suite with pytest
pytest -v
```

---

## 📁 Global User Settings

DevDesk persists global user preferences across all projects in `~/.config/devdesk/settings.toml`:

```toml
log_buffer_size = 2000          # Number of lines retained in memory per service
auto_follow_logs = true         # Automatically pin view to the newest logs
confirm_before_stop = true      # Confirm before shutting down running services on exit
auto_start_on_open = false      # Start auto_start services immediately upon launch
default_project_directory = "~" # Starting folder for the project switcher
```

---

## 📄 License

This project is open-source and available under the **[MIT License](LICENSE)**.
