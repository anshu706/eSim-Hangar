# eSim Automated Tool Manager: Execution & Operator Manual

## 1. Prerequisites & Environment Setup
- **Operating System**: Windows 10 (version 1809+) or Windows 11.
- **Python**: Python 3.10+ 64-bit installed with PATH enabled.
- **Windows Package Manager (`winget`)**: Pre-installed on modern Windows 10/11 via the Microsoft App Installer.
- **Git**: Git for Windows installed and accessible from terminal.

### Quick Verification:
```powershell
python --version
winget --version
git --version
```

---

## 2. Installation & Quickstart

Clone the repository and install dependencies in editable mode:
```powershell
git clone https://github.com/YourUsername/esim-tool-manager.git
cd esim-tool-manager
python -m pip install -e .
```

Initialize your user environment:
```powershell
esim-tool-manager init
```
This initializes `%LOCALAPPDATA%\esim-tool-manager`, sets default configurations, creates cache/state directories, and validates winget/git availability.

---

## 3. Command Reference Cheat-Sheet

| Subcommand | Syntax / Flags | Description | Exit Code |
| :--- | :--- | :--- | :--- |
| `init` | `esim-tool-manager init [--dry-run]` | Initializes environment, directories, and base configuration. | 0: Success, 1: Error |
| `list` | `esim-tool-manager list` | Displays table of managed tools, versions, paths, and status (`OK`, `MISSING`, `OUTDATED`, `INCOMPATIBLE`). | 0: Success |
| `check` | `esim-tool-manager check` | Validates installed versions and verifies dependency satisfaction. | 0: OK, 2: Missing/Incompatible |
| `install` | `esim-tool-manager install <tool \| all> [--yes] [--dry-run]` | Installs pinned versions of missing or outdated tools (idempotent). | 0: Success, 1: Error, 3: Cancelled |
| `update check` | `esim-tool-manager update check` | Queries package sources and reports available upstream updates. | 0: Success |
| `update` | `esim-tool-manager update <tool \| all> [--yes] [--dry-run]` | Safely upgrades tool while creating an immutable rollback snapshot. | 0: Success, 1: Error, 3: Cancelled |
| `rollback` | `esim-tool-manager rollback <tool> [--yes] [--dry-run]` | Restores the tool to its previously recorded version state. | 0: Success, 1: Error |
| `configure` | `esim-tool-manager configure [--yes] [--dry-run]` | Updates HKCU user PATH registry and writes `eSim.ini` with unified diff display. | 0: Success, 1: Error, 3: Cancelled |
| `configure --revert` | `esim-tool-manager configure --revert [--yes] [--dry-run]` | Restores user PATH and eSim INI settings using snapshot records. | 0: Success, 1: Error |
| `doctor` | `esim-tool-manager doctor` | Runs 6-category system health checks and provides actionable remedies. | 0: Success, 1: Issues found |
| `cache list` | `esim-tool-manager cache list` | Displays cached offline installers and their byte sizes. | 0: Success |
| `cache clear` | `esim-tool-manager cache clear [--yes]` | Safely removes downloaded installer packages to reclaim disk space. | 0: Success |
| `logs` | `esim-tool-manager logs [--tail N]` | Prints the latest structured JSON action log entries with secret redaction. | 0: Success |
| `report` | `esim-tool-manager report [--out PATH]` | Compiles a comprehensive Markdown system audit file. | 0: Success |
| `config get/set` | `esim-tool-manager config <get \| set> [key] [val]` | Manages user settings (e.g. `esim_path`). | 0: Success, 1: Error |
| `version` | `esim-tool-manager version` | Displays current CLI version. | 0: Success |

---

## 4. Offline Mode Operation

`esim-tool-manager` is designed for students with unstable weekday connections:
1. **Pre-caching on a stable network**: Run `esim-tool-manager install all` once while connected. All installer packages are saved to `%LOCALAPPDATA%\esim-tool-manager\cache`.
2. **Offline Re-runs / Restorations**: Subsequent installations or repairs read directly from cache without connecting to the internet.
3. **Resumed Downloads**: If a download drops mid-stream, running the command again uses HTTP Range requests to continue exactly where it stopped.

---

## 5. Troubleshooting & Diagnostics

- **`winget` not recognized**: Install the [App Installer from Microsoft Store](https://apps.microsoft.com/detail/9NBLGGH4NNS1) or install from the official GitHub release `microsoft/winget-cli`.
- **Permission Errors**: Verify you are running as a standard user. The tool targets `HKEY_CURRENT_USER\Environment` and `%LOCALAPPDATA%`, requiring zero administrator elevation.
- **Dependency Incompatibilities**: Run `esim-tool-manager check` to view specific minimum version discrepancies and recommended fixes.
