"""Command-line interface for eSim Automated Tool Manager."""

import argparse
import sys
import traceback
from pathlib import Path

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    HAVE_RICH = True
    console = Console()
except ImportError:
    HAVE_RICH = False
    console = None  # type: ignore

from esim_tool_manager import __version__
from esim_tool_manager.config import ConfigManager
from esim_tool_manager.configurator import ToolConfigurator
from esim_tool_manager.deps import DependencyChecker
from esim_tool_manager.detector import ToolDetector
from esim_tool_manager.doctor import SystemDoctor
from esim_tool_manager.downloader import Downloader
from esim_tool_manager.errors import (
    ConfigError,
    EsimToolManagerError,
    PlatformError,
)
from esim_tool_manager.installer import ToolInstaller
from esim_tool_manager.logger import log_action, read_logs, setup_logger
from esim_tool_manager.platform_win import check_git_installed, check_winget_installed
from esim_tool_manager.registry import ToolRegistry
from esim_tool_manager.report import ReportGenerator
from esim_tool_manager.updater import ToolUpdater


def print_info(message: str) -> None:
    """Print an informational message."""
    if HAVE_RICH and console:
        console.print(f"[bold cyan]INFO:[/bold cyan] {message}")
    else:
        print(f"INFO: {message}")


def print_success(message: str) -> None:
    """Print a success message."""
    if HAVE_RICH and console:
        console.print(f"[bold green]SUCCESS:[/bold green] {message}")
    else:
        print(f"SUCCESS: {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    if HAVE_RICH and console:
        console.print(f"[bold yellow]WARNING:[/bold yellow] {message}")
    else:
        print(f"WARNING: {message}")


def print_error(message: str, fix_suggestion: str | None = None) -> None:
    """Print a structured, actionable error message."""
    if HAVE_RICH and console:
        err_text = f"[bold red]ERROR:[/bold red] {message}"
        if fix_suggestion:
            err_text += f"\n[bold yellow]Suggested Fix:[/bold yellow] {fix_suggestion}"
        console.print(Panel(err_text, title="Action Required", border_style="red"))
    else:
        print(f"\nERROR: {message}")
        if fix_suggestion:
            print(f"Suggested Fix: {fix_suggestion}")


def cmd_init(args: argparse.Namespace, config_mgr: ConfigManager) -> int:
    """Initialize configuration and data directories; check prerequisites."""
    print_info("Initializing eSim Tool Manager environment...")
    if args.dry_run:
        print_info("[DRY RUN] Would initialize directories and config file.")
        return 0

    config_mgr.initialize_directories()
    print_success(f"Directories initialized at: {config_mgr.base_dir}")

    # Check Winget
    try:
        winget_ver = check_winget_installed()
        print_success(f"Windows Package Manager (winget) found: v{winget_ver}")
    except PlatformError as exc:
        print_warning(f"Winget check: {exc.message}")
        if exc.fix_suggestion:
            print_info(f"Note: {exc.fix_suggestion}")

    # Check Git
    try:
        git_ver = check_git_installed()
        print_success(f"Git found: {git_ver}")
    except PlatformError as exc:
        print_warning(f"Git check: {exc.message}")
        if exc.fix_suggestion:
            print_info(f"Note: {exc.fix_suggestion}")

    log_action("init", action="initialize", result="SUCCESS", details=str(config_mgr.base_dir))
    return 0


def cmd_list(args: argparse.Namespace, detector: ToolDetector) -> int:
    """Display tabular status of all managed tools."""
    statuses = detector.detect_all()

    if HAVE_RICH and console:
        table = Table(
            title="eSim Managed Tools Status", show_header=True, header_style="bold magenta"
        )
        table.add_column("Tool", style="cyan", width=12)
        table.add_column("Installed Version", width=18)
        table.add_column("Required (Min)", width=15)
        table.add_column("Pinned Version", width=15)
        table.add_column("Status", width=14)
        table.add_column("Binary Path", style="dim")

        for name, st in sorted(statuses.items()):
            status_style = (
                "green" if st.status == "OK" else ("yellow" if st.status == "OUTDATED" else "red")
            )
            table.add_row(
                st.display_name,
                st.installed_version or "Not installed",
                st.required_version,
                st.pinned_version,
                f"[{status_style}]{st.status}[/{status_style}]",
                st.binary_path or "Not found",
            )
        console.print(table)
    else:
        header = f"{'Tool':<12} {'Installed':<18} {'Required':<15} {'Pinned':<15} {'Status':<14} {'Binary Path'}"
        print(header)
        print("-" * len(header))
        for name, st in sorted(statuses.items()):
            inst = st.installed_version or "Not installed"
            p = st.binary_path or "Not found"
            print(
                f"{st.display_name:<12} {inst:<18} {st.required_version:<15} {st.pinned_version:<15} {st.status:<14} {p}"
            )

    log_action("list", action="list_tools", result="SUCCESS")
    return 0


def cmd_check(
    args: argparse.Namespace,
    detector: ToolDetector,
    dep_checker: DependencyChecker,
) -> int:
    """Check binary availability, version compatibility, and dependencies."""
    print_info("Running dependency and version compliance checks...")
    statuses = detector.detect_all()
    dep_results = dep_checker.check_all_dependencies()

    has_issues = False

    for name, st in sorted(statuses.items()):
        dep_res = dep_results.get(name)
        deps_ok = dep_res.is_valid if dep_res else True

        if st.status == "OK" and deps_ok:
            print_success(
                f"{st.display_name}: OK (version {st.installed_version} at {st.binary_path})"
            )
        elif st.status == "OUTDATED" and deps_ok:
            print_warning(
                f"{st.display_name}: OUTDATED (version {st.installed_version} meets minimum {st.required_version}, "
                f"recommended pinned is {st.pinned_version})."
            )
            if st.fix_suggestion:
                print_info(f"  Fix: {st.fix_suggestion}")
        else:
            has_issues = True
            print_error(
                f"{st.display_name}: {st.status} (Installed: {st.installed_version or 'None'}, Required: {st.required_version})",
                fix_suggestion=st.fix_suggestion,
            )
            if dep_res and not dep_res.is_valid:
                for d_err in dep_res.details:
                    print_warning(f"  Dependency Issue: {d_err}")

    result_str = "FAILED" if has_issues else "SUCCESS"
    log_action("check", action="check_dependencies", result=result_str)

    if has_issues:
        print_warning("\nOne or more tools are missing, incompatible, or have unmet dependencies.")
        return 2

    print_success("\nAll managed tools and prerequisites are satisfied.")
    return 0


def cmd_install(args: argparse.Namespace, installer: ToolInstaller) -> int:
    """Install a specific tool or all tools."""
    target = args.tool.lower().strip()

    # Prompt confirmation unless --yes or --dry-run
    if not args.yes and not args.dry_run:
        prompt_target = "all managed tools" if target == "all" else target
        print_info(f"Preparing to install: {prompt_target}")
        try:
            choice = input("Proceed with installation? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt, OSError):
            print_warning(
                "\nInstallation cancelled by user or running in non-interactive environment."
            )
            log_action("install", tool=target, action="cancel", result="CANCELLED")
            return 3
        if choice not in ("y", "yes"):
            print_warning("Installation cancelled by user.")
            log_action("install", tool=target, action="cancel", result="CANCELLED")
            return 3

    if target == "all":
        print_info("Installing all tools in dependency sequence...")
        results = installer.install_all(dry_run=args.dry_run)
        has_error = False
        for t_name, (ok, msg) in results.items():
            if ok:
                print_success(f"{t_name}: {msg}")
            else:
                has_error = True
                print_error(f"{t_name}: {msg}")
        return 1 if has_error else 0

    try:
        ok, msg = installer.install_tool(target, dry_run=args.dry_run)
        if ok:
            print_success(msg)
            return 0
        print_error(msg)
        return 1
    except EsimToolManagerError as exc:
        print_error(exc.message, fix_suggestion=exc.fix_suggestion)
        return 1


def cmd_update(args: argparse.Namespace, updater: ToolUpdater, config_mgr: ConfigManager) -> int:
    """Check for updates or upgrade installed tools."""
    target = args.target.lower().strip()

    if target == "check":
        print_info("Checking for tool updates...")
        results = updater.check_updates()
        last_check = config_mgr.get("last_update_check")

        if HAVE_RICH and console:
            table = Table(
                title="eSim Tool Updates Check", show_header=True, header_style="bold blue"
            )
            table.add_column("Tool", style="cyan", width=12)
            table.add_column("Installed Version", width=18)
            table.add_column("Available Version", width=18)
            table.add_column("Status", width=16)

            for name, info in sorted(results.items()):
                style = (
                    "green"
                    if info["status"] == "UP_TO_DATE"
                    else ("yellow" if info["status"] == "UPDATE_AVAILABLE" else "red")
                )
                table.add_row(
                    info["display_name"],
                    info["installed_version"] or "Not installed",
                    info["available_version"],
                    f"[{style}]{info['status']}[/{style}]",
                )
            console.print(table)
            if last_check:
                console.print(f"[dim]Last update check timestamp: {last_check}[/dim]")
        else:
            header = f"{'Tool':<12} {'Installed':<18} {'Available':<18} {'Status'}"
            print(header)
            print("-" * len(header))
            for name, info in sorted(results.items()):
                inst = info["installed_version"] or "Not installed"
                print(
                    f"{info['display_name']:<12} {inst:<18} {info['available_version']:<18} {info['status']}"
                )
            if last_check:
                print(f"Last update check timestamp: {last_check}")

        log_action("update", action="check", result="SUCCESS")
        return 0

    # User requested upgrade
    if not args.yes and not args.dry_run:
        prompt_target = "all managed tools" if target == "all" else target
        print_info(f"Preparing to update: {prompt_target}")
        try:
            choice = input("Proceed with update? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt, OSError):
            print_warning("\nUpdate cancelled by user.")
            log_action("update", tool=target, action="cancel", result="CANCELLED")
            return 3
        if choice not in ("y", "yes"):
            print_warning("Update cancelled by user.")
            log_action("update", tool=target, action="cancel", result="CANCELLED")
            return 3

    if target == "all":
        print_info("Updating all tools...")
        results_all = updater.update_all(dry_run=args.dry_run)
        has_error = False
        for t_name, (ok, msg) in results_all.items():
            if ok:
                print_success(f"{t_name}: {msg}")
            else:
                has_error = True
                print_error(f"{t_name}: {msg}")
        return 1 if has_error else 0

    try:
        ok, msg = updater.update_tool(target, dry_run=args.dry_run)
        if ok:
            print_success(msg)
            return 0
        print_error(msg)
        return 1
    except EsimToolManagerError as exc:
        print_error(exc.message, fix_suggestion=exc.fix_suggestion)
        return 1


def cmd_rollback(args: argparse.Namespace, updater: ToolUpdater) -> int:
    """Roll back a tool to its previously recorded version."""
    target = args.tool.lower().strip()
    try:
        ok, msg = updater.rollback_tool(target, dry_run=args.dry_run)
        if ok:
            print_success(msg)
            return 0
        print_error(msg)
        return 1
    except EsimToolManagerError as exc:
        print_error(exc.message, fix_suggestion=exc.fix_suggestion)
        return 1


def cmd_configure(args: argparse.Namespace, configurator: ToolConfigurator) -> int:
    """Configure HKCU user PATH entries and eSim configuration file with diffs and revert."""
    if args.revert:
        try:
            preview = configurator.preview_revert()
        except ConfigError as exc:
            print_error(exc.message, fix_suggestion=exc.fix_suggestion)
            return 1

        print_info("Configuration Revert Preview:")
        to_remove = preview.get("added_entries_to_remove", [])
        if to_remove:
            print_warning(f"PATH entries to be removed ({len(to_remove)}):")
            for entry in to_remove:
                print(f"  [-] {entry}")
        else:
            print_info("No PATH entries need to be removed.")

        cfg_diff = preview.get("cfg_diff", "")
        if cfg_diff:
            print_info(f"Diff for {preview['esim_config_path']}:")
            for line in cfg_diff.splitlines():
                if line.startswith("+"):
                    if HAVE_RICH and console:
                        console.print(f"[green]{line}[/green]")
                    else:
                        print(line)
                elif line.startswith("-"):
                    if HAVE_RICH and console:
                        console.print(f"[red]{line}[/red]")
                    else:
                        print(line)
                else:
                    print(line)

        if not args.yes and not args.dry_run:
            try:
                choice = input("Proceed with configuration revert? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt, OSError):
                print_warning("\nRevert cancelled by user.")
                return 3
            if choice not in ("y", "yes"):
                print_warning("Revert cancelled by user.")
                return 3

        ok, msg = configurator.apply_revert(dry_run=args.dry_run)
        if ok:
            print_success(msg)
            return 0
        print_error(msg)
        return 1

    # Standard configuration
    preview = configurator.preview_configure()
    added_paths = preview.get("added_path_entries", [])
    if added_paths:
        print_info(f"New entries to append to HKCU user PATH ({len(added_paths)}):")
        for p in added_paths:
            print(f"  [+] {p}")
    else:
        print_info("All managed tool directories are already present in user PATH.")

    cfg_diff = preview.get("cfg_diff", "")
    target_cfg = preview.get("target_esim_cfg", "")
    print_info(f"Target eSim configuration file: {target_cfg}")
    if cfg_diff:
        print_info("Configuration File Changes (Diff):")
        for line in cfg_diff.splitlines():
            if line.startswith("+"):
                if HAVE_RICH and console:
                    console.print(f"[green]{line}[/green]")
                else:
                    print(line)
            elif line.startswith("-"):
                if HAVE_RICH and console:
                    console.print(f"[red]{line}[/red]")
                else:
                    print(line)
            else:
                print(line)
    else:
        print_info("eSim configuration file is already up to date.")

    if not args.yes and not args.dry_run:
        try:
            choice = input("Apply these configuration changes? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt, OSError):
            print_warning("\nConfiguration cancelled by user.")
            return 3
        if choice not in ("y", "yes"):
            print_warning("Configuration cancelled by user.")
            return 3

    ok, msg = configurator.apply_configure(dry_run=args.dry_run)
    if ok:
        print_success(msg)
        return 0
    print_error(msg)
    return 1


def cmd_doctor(args: argparse.Namespace, doctor: SystemDoctor) -> int:
    """Run full system health and diagnostic checks."""
    print_info("Executing comprehensive diagnostic battery...")
    checks = doctor.run_all_checks()

    has_failures = any(c.status == "FAIL" for c in checks)

    if HAVE_RICH and console:
        table = Table(
            title="eSim System Doctor Diagnostics", show_header=True, header_style="bold cyan"
        )
        table.add_column("Category", style="dim", width=14)
        table.add_column("Check", width=22)
        table.add_column("Status", width=10)
        table.add_column("Details", width=36)
        table.add_column("Suggested Fix", style="yellow")

        for c in checks:
            status_style = (
                "green" if c.status == "PASS" else ("yellow" if c.status == "WARN" else "bold red")
            )
            table.add_row(
                c.category,
                c.name,
                f"[{status_style}]{c.status}[/{status_style}]",
                c.message,
                c.fix_suggestion or "",
            )
        console.print(table)
    else:
        for c in checks:
            print(f"[{c.status}] {c.category} - {c.name}: {c.message}")
            if c.fix_suggestion:
                print(f"       Fix: {c.fix_suggestion}")

    result_str = "FAILED" if has_failures else "SUCCESS"
    log_action("doctor", action="run_checks", result=result_str)

    if has_failures:
        print_warning("\nOne or more diagnostic checks reported issues requiring remediation.")
        return 1

    print_success("\nAll core diagnostic checks passed successfully.")
    return 0


def cmd_cache(args: argparse.Namespace, downloader: Downloader) -> int:
    """Manage local installer downloads cache."""
    action = args.cache_action or "list"

    if action == "list":
        items = downloader.list_cached_files()
        if not items:
            print_info(f"Installer cache is empty ({downloader.cache_dir}).")
            return 0

        if HAVE_RICH and console:
            table = Table(
                title="eSim Cached Installer Files", show_header=True, header_style="bold blue"
            )
            table.add_column("File", style="cyan", width=30)
            table.add_column("Size (MB)", width=12)
            table.add_column("Local Path", style="dim")

            for item in items:
                table.add_row(item["filename"], str(item["size_mb"]), item["path"])
            console.print(table)
        else:
            for item in items:
                print(f"{item['filename']:<30} {item['size_mb']} MB   {item['path']}")
        return 0

    elif action == "clear":
        if not args.yes and not args.dry_run:
            try:
                choice = (
                    input("Are you sure you want to clear all cached installers? [y/N]: ")
                    .strip()
                    .lower()
                )
            except (EOFError, KeyboardInterrupt, OSError):
                print_warning("\nOperation cancelled.")
                return 3
            if choice not in ("y", "yes"):
                print_warning("Operation cancelled.")
                return 3

        if args.dry_run:
            items = downloader.list_cached_files()
            print_info(
                f"[DRY RUN] Would delete {len(items)} cached files from {downloader.cache_dir}."
            )
            return 0

        count = downloader.clear_cache()
        print_success(f"Successfully cleared {count} cached installer file(s).")
        log_action("cache", action="clear", result="SUCCESS", details=f"Cleared {count} files")
        return 0

    return 0


def cmd_logs(args: argparse.Namespace, config_mgr: ConfigManager) -> int:
    """Display recent structured action log entries."""
    tail = getattr(args, "tail", 30) or 30
    entries = read_logs(tail=tail, log_dir=config_mgr.logs_dir)
    if not entries:
        print_info("No action log entries found.")
        return 0

    if HAVE_RICH and console:
        table = Table(
            title=f"Recent Action Log (Last {len(entries)} events)",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Timestamp (UTC)", width=20, style="dim")
        table.add_column("Command", width=12, style="cyan")
        table.add_column("Tool", width=10)
        table.add_column("Action", width=18)
        table.add_column("Result", width=10)
        table.add_column("Details", style="dim")

        for entry in entries:
            if "raw" in entry:
                table.add_row("-", "-", "-", "raw", "-", entry["raw"][:60])
            else:
                res = entry.get("result", "")
                res_style = (
                    "green" if res == "SUCCESS" else ("yellow" if res == "CANCELLED" else "red")
                )
                table.add_row(
                    entry.get("timestamp", "")[:19],
                    entry.get("command", ""),
                    entry.get("tool", ""),
                    entry.get("action", ""),
                    f"[{res_style}]{res}[/{res_style}]",
                    entry.get("details", "")[:60],
                )
        console.print(table)
    else:
        for entry in entries:
            if "raw" in entry:
                print(entry["raw"])
            else:
                ts = entry.get("timestamp", "")[:19]
                print(
                    f"{ts} | {entry.get('command'):<8} | {entry.get('action'):<15} | {entry.get('result'):<10} | {entry.get('details')}"
                )

    return 0


def cmd_report(args: argparse.Namespace, report_gen: ReportGenerator) -> int:
    """Generate and export a Markdown status report."""
    target_path = Path(args.output) if args.output else Path.cwd() / "esim_tool_manager_report.md"
    print_info(f"Generating system audit report to: {target_path} ...")
    out_file = report_gen.write_report(target_path)
    print_success(f"Audit report exported successfully to: {out_file}")
    log_action("report", action="export", result="SUCCESS", details=str(out_file))
    return 0


def cmd_config(args: argparse.Namespace, config_mgr: ConfigManager) -> int:
    """Get or set user configuration values."""
    if args.config_action == "get":
        val = config_mgr.get(args.key)
        print(f"{args.key} = {val}")
        return 0
    elif args.config_action == "set":
        if args.dry_run:
            print_info(f"[DRY RUN] Would set '{args.key}' = '{args.value}'")
            return 0
        config_mgr.set(args.key, args.value)
        print_success(f"Configuration updated: {args.key} = {args.value}")
        log_action("config", action="set", result="SUCCESS", details=f"{args.key}={args.value}")
        return 0
    elif args.config_action == "show":
        cfg = config_mgr.load_config()
        for k, v in cfg.items():
            print(f"{k}: {v}")
        return 0
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser with all subcommands."""
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Simulate actions without applying system changes",
    )
    common_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Enable verbose execution output",
    )
    common_parser.add_argument(
        "--debug",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Display full tracebacks upon failure",
    )

    parser = argparse.ArgumentParser(
        prog="esim-tool-manager",
        description="Automated External Tool Manager for FOSSEE eSim (EDA)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Simulate actions without applying system changes",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Enable verbose execution output",
    )
    parser.add_argument(
        "--debug", action="store_true", default=False, help="Display full tracebacks upon failure"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # init
    subparsers.add_parser(
        "init",
        parents=[common_parser],
        help="Initialize user directories, configuration, and verify prerequisites",
    )

    # list
    subparsers.add_parser(
        "list", parents=[common_parser], help="List all managed tools and their current status"
    )

    # check
    subparsers.add_parser(
        "check",
        parents=[common_parser],
        help="Run dependency and version compliance checks (Exit code 2 if unmet)",
    )

    # config
    config_parser = subparsers.add_parser(
        "config", parents=[common_parser], help="Manage configuration settings (e.g. esim_path)"
    )
    config_sub = config_parser.add_subparsers(dest="config_action")
    config_get = config_sub.add_parser(
        "get", parents=[common_parser], help="Get a configuration value"
    )
    config_get.add_argument("key", help="Key name to inspect")
    config_set = config_sub.add_parser(
        "set", parents=[common_parser], help="Set a configuration value"
    )
    config_set.add_argument("key", help="Key name to update (e.g. esim_path)")
    config_set.add_argument("value", help="Value to set")
    config_sub.add_parser("show", parents=[common_parser], help="Show full configuration")

    # install
    install_parser = subparsers.add_parser(
        "install", parents=[common_parser], help="Install a tool or all tools"
    )
    install_parser.add_argument(
        "tool", help="Tool name ('ngspice', 'kicad', 'python', 'git') or 'all'"
    )
    install_parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    # update
    update_parser = subparsers.add_parser(
        "update", parents=[common_parser], help="Update tools or check for available updates"
    )
    update_parser.add_argument("target", help="Tool name or 'check' or 'all'")
    update_parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    # rollback
    rollback_parser = subparsers.add_parser(
        "rollback",
        parents=[common_parser],
        help="Roll back a tool to its previously recorded version",
    )
    rollback_parser.add_argument("tool", help="Tool name to roll back")

    # configure
    configure_parser = subparsers.add_parser(
        "configure", parents=[common_parser], help="Configure PATH and eSim configuration file"
    )
    configure_parser.add_argument(
        "--revert", action="store_true", help="Revert all configuration changes"
    )
    configure_parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip confirmation prompt"
    )

    # doctor
    subparsers.add_parser(
        "doctor", parents=[common_parser], help="Run comprehensive system health checks"
    )

    # cache
    cache_parser = subparsers.add_parser(
        "cache", parents=[common_parser], help="Manage installer download cache"
    )
    cache_sub = cache_parser.add_subparsers(dest="cache_action")
    cache_sub.add_parser("list", parents=[common_parser], help="List cached installers")
    cache_clear = cache_sub.add_parser("clear", parents=[common_parser], help="Clear cached installers")
    cache_clear.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    # logs
    logs_parser = subparsers.add_parser(
        "logs", parents=[common_parser], help="Display recent action logs"
    )
    logs_parser.add_argument("--tail", type=int, default=30, help="Number of log entries to show")

    # report
    report_parser = subparsers.add_parser(
        "report", parents=[common_parser], help="Export system status report as Markdown"
    )
    report_parser.add_argument("--output", "-o", help="Target output file path")

    # version
    subparsers.add_parser(
        "version", parents=[common_parser], help="Print eSim Tool Manager version"
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "version":
        print(f"esim-tool-manager v{__version__}")
        return 0

    config_mgr = ConfigManager()
    setup_logger(log_dir=config_mgr.logs_dir, debug_mode=args.debug)

    try:
        registry = ToolRegistry()
        detector = ToolDetector(registry=registry, config=config_mgr)
        dep_checker = DependencyChecker(registry=registry, detector=detector)
        installer = ToolInstaller(registry=registry, detector=detector, config_mgr=config_mgr)
        updater = ToolUpdater(
            registry=registry,
            detector=detector,
            installer=installer,
            config_mgr=config_mgr,
        )
        configurator = ToolConfigurator(
            registry=registry,
            detector=detector,
            config_mgr=config_mgr,
        )
        doctor = SystemDoctor(
            registry=registry,
            detector=detector,
            dep_checker=dep_checker,
            config_mgr=config_mgr,
        )
        downloader = Downloader(config_mgr=config_mgr)
        report_gen = ReportGenerator(
            registry=registry,
            detector=detector,
            config_mgr=config_mgr,
        )

        if args.command == "init":
            return cmd_init(args, config_mgr)
        elif args.command == "list":
            return cmd_list(args, detector)
        elif args.command == "check":
            return cmd_check(args, detector, dep_checker)
        elif args.command == "install":
            return cmd_install(args, installer)
        elif args.command == "update":
            return cmd_update(args, updater, config_mgr)
        elif args.command == "rollback":
            return cmd_rollback(args, updater)
        elif args.command == "configure":
            return cmd_configure(args, configurator)
        elif args.command == "doctor":
            return cmd_doctor(args, doctor)
        elif args.command == "cache":
            return cmd_cache(args, downloader)
        elif args.command == "logs":
            return cmd_logs(args, config_mgr)
        elif args.command == "report":
            return cmd_report(args, report_gen)
        elif args.command == "config":
            return cmd_config(args, config_mgr)
        else:
            # Stubs for subsequent milestones
            print_error(
                f"Command '{args.command}' is planned for upcoming milestones (M2-M5).",
                fix_suggestion="Use 'esim-tool-manager list' or 'esim-tool-manager check' in M1.",
            )
            return 1

    except EsimToolManagerError as exc:
        print_error(exc.message, fix_suggestion=exc.fix_suggestion)
        log_action(args.command, action="error", result="FAILED", details=exc.message)
        if args.debug:
            traceback.print_exc()
        return 1
    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user.")
        log_action(args.command or "unknown", action="cancel", result="CANCELLED")
        return 3
    except Exception as exc:  # noqa: BLE001
        print_error(f"Unexpected error: {exc}", fix_suggestion="Run with --debug for stack trace.")
        log_action(
            args.command or "unknown", action="unexpected_error", result="FAILED", details=str(exc)
        )
        if args.debug:
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
