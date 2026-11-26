# eSim Automated Tool Manager: Assessor Demonstration Script

This walkthrough script allows internship evaluators to test and verify every core requirement (R1-R5) and safety feature on Windows 10/11.

---

## Step 1: Environment Initialization
Run the initialization routine:
```powershell
esim-tool-manager init
```
**Expected Outcome**:
- Creates `%LOCALAPPDATA%\esim-tool-manager` with subdirectories (`cache`, `state`, `records`, `tools`).
- Verifies system prerequisites (`winget` and `git`).
- Returns exit code `0`.

---

## Step 2: System Status & Dependency Checking (R4)
Inspect current tool availability:
```powershell
esim-tool-manager list
```
**Expected Outcome**:
- Renders a clean Rich table showing all 4 managed tools: `Ngspice`, `KiCad`, `Python`, `Git`.
- Shows version criteria and status (`OK`, `MISSING`, `OUTDATED`).

Execute strict dependency validation:
```powershell
esim-tool-manager check
```
**Expected Outcome**:
- Verifies dependency graph (e.g. `kicad` and `ngspice` require `python`).
- If any tool is missing or below minimum, reports actionable remediation steps and exits with code `2`.

---

## Step 3: Tool Installation Management (R1)
Install tools with dry-run preview first:
```powershell
esim-tool-manager install ngspice --dry-run
```
Now perform idempotent installation:
```powershell
esim-tool-manager install ngspice --yes
```
**Expected Outcome**:
- Downloads the verified package with SHA256 integrity validation.
- Extracts into `%LOCALAPPDATA%\esim-tool-manager\tools\Spice64`.
- Re-running the command immediately skips installation cleanly (idempotence).

---

## Step 4: Configuration & Environment Setup (R3)
Configure user PATH and eSim INI integration:
```powershell
esim-tool-manager configure --yes
```
**Expected Outcome**:
- Shows diff of new PATH entries to be appended to `HKCU\Environment`.
- Generates/updates `eSim.ini` with verified binary paths.
- Records rollback snapshot in `records/path_record.json`.

---

## Step 5: Update Checking & Rollback Protection (R2)
Check upstream availability:
```powershell
esim-tool-manager update check
```
Test rollback mechanics:
```powershell
esim-tool-manager rollback ngspice --dry-run
```
**Expected Outcome**:
- Verifies previously installed version metadata from `state/ngspice.json`.

---

## Step 6: Full System Diagnostics (Doctor)
Run diagnostic sweep across 6 subsystem categories:
```powershell
esim-tool-manager doctor
```
**Expected Outcome**:
- Assesses binary reachability, PATH registry entries, eSim configuration file health, network reachability, filesystem permissions, and audit log rotation.

---

## Step 7: Reverting Changes (R3)
Demonstrate 1-click clean teardown:
```powershell
esim-tool-manager configure --revert --yes
```
**Expected Outcome**:
- Removes previously added PATH entries from HKCU.
- Reverts `eSim.ini` to its prior state.

---

## Step 8: Action Log Audit & Submission Report (R5)
Inspect the redacted rotating JSON action log:
```powershell
esim-tool-manager logs --tail 10
```
Generate the official Markdown submission report:
```powershell
esim-tool-manager report --out esim_audit_report.md
```
**Expected Outcome**:
- Formats recent log events showing timestamps, tools, and results.
- Exports a comprehensive markdown document detailing system compliance.
