"""Status report generator for eSim Tool Manager."""

import sys
from datetime import datetime, timezone
from pathlib import Path

from esim_tool_manager import __version__
from esim_tool_manager.config import ConfigManager
from esim_tool_manager.deps import DependencyChecker
from esim_tool_manager.detector import ToolDetector
from esim_tool_manager.doctor import SystemDoctor
from esim_tool_manager.logger import read_logs
from esim_tool_manager.platform_win import get_user_path
from esim_tool_manager.registry import ToolRegistry


class ReportGenerator:
    """Generates comprehensive Markdown status and audit reports."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        detector: ToolDetector | None = None,
        config_mgr: ConfigManager | None = None,
    ):
        self.config = config_mgr or ConfigManager()
        self.registry = registry or ToolRegistry()
        self.detector = detector or ToolDetector(registry=self.registry, config=self.config)
        self.doctor = SystemDoctor(
            registry=self.registry, detector=self.detector, config_mgr=self.config
        )
        self.dep_checker = DependencyChecker(registry=self.registry, detector=self.detector)

    def generate_markdown(self) -> str:
        """Produce markdown string detailing full application state and audit."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        statuses = self.detector.detect_all()
        checks = self.doctor.run_all_checks()
        logs = read_logs(tail=15, log_dir=self.config.logs_dir)
        user_paths = get_user_path()
        esim_path = self.config.get("esim_path", "Default")

        md = []
        md.append("# eSim Automated Tool Manager — System Audit Report")
        md.append(
            f"**Generated:** {now} | **Version:** `v{__version__}` | **OS:** `{sys.platform}`\n"
        )
        md.append("## 1. Executive Summary")
        total_tools = len(statuses)
        ok_tools = sum(1 for s in statuses.values() if s.status == "OK")
        outdated_tools = sum(1 for s in statuses.values() if s.status == "OUTDATED")
        missing_tools = sum(1 for s in statuses.values() if s.status == "MISSING")
        incomp_tools = sum(1 for s in statuses.values() if s.status == "INCOMPATIBLE")

        md.append(f"- **Total Managed Tools:** {total_tools}")
        md.append(f"- **Fully Compliant (OK):** {ok_tools}")
        md.append(f"- **Outdated (Functional, but updates available):** {outdated_tools}")
        md.append(f"- **Missing / Incompatible:** {missing_tools + incomp_tools}")
        md.append(f"- **eSim Path:** `{esim_path}`\n")

        md.append("## 2. Managed Tools Compliance Status")
        md.append(
            "| Tool | Installed Version | Required (Min) | Pinned Version | Status | Binary Path |"
        )
        md.append("|---|---|---|---|---|---|")
        for name, st in sorted(statuses.items()):
            inst = st.installed_version or "None"
            bin_p = f"`{st.binary_path}`" if st.binary_path else "Not found"
            md.append(
                f"| {st.display_name} | {inst} | {st.required_version} | {st.pinned_version} | **{st.status}** | {bin_p} |"
            )
        md.append("")

        md.append("## 3. System Health & Doctor Diagnostics")
        md.append("| Check | Category | Status | Details | Suggested Fix |")
        md.append("|---|---|---|---|---|")
        for c in checks:
            fix = c.fix_suggestion or "None"
            md.append(f"| {c.name} | {c.category} | **{c.status}** | {c.message} | {fix} |")
        md.append("")

        md.append("## 4. User Environment & Registry PATH (HKCU)")
        md.append(f"Total entries in HKCU User PATH: `{len(user_paths)}`")
        md.append("```text")
        for p in user_paths[:10]:
            md.append(f"  {p}")
        if len(user_paths) > 10:
            md.append(f"  ... (+{len(user_paths) - 10} more)")
        md.append("```\n")

        md.append("## 5. Recent Action Logs (Last 15 Events)")
        md.append("| Timestamp (UTC) | Command | Tool | Action | Result | Details |")
        md.append("|---|---|---|---|---|---|")
        for entry in logs:
            if "raw" in entry:
                md.append(f"| - | - | - | raw | - | `{entry['raw'][:60]}` |")
            else:
                md.append(
                    f"| {entry.get('timestamp', '')[:19]} | `{entry.get('command')}` | {entry.get('tool')} | "
                    f"{entry.get('action')} | **{entry.get('result')}** | {entry.get('details', '')[:50]} |"
                )
        md.append("\n---\n*Report generated automatically by `esim-tool-manager`.*")

        return "\n".join(md)

    def write_report(self, target_path: Path | None = None) -> Path:
        """Generate and save the report to disk."""
        out_path = target_path or Path.cwd() / "esim_tool_manager_report.md"
        content = self.generate_markdown()
        out_path.write_text(content, encoding="utf-8")
        return out_path.resolve()
