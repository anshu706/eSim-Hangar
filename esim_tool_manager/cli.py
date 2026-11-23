"""Command-line interface for eSim Automated Tool Manager."""

import argparse
import sys
import traceback

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
from esim_tool_manager.deps import DependencyChecker
from esim_tool_manager.detector import ToolDetector
from esim_tool_manager.errors import (
    EsimToolManagerError,
    PlatformError,
)
from esim_tool_manager.installer import ToolInstaller
from esim_tool_manager.logger import log_action, setup_logger
from esim_tool_manager.platform_win import check_git_installed, check_winget_installed
from esim_tool_manager.registry import ToolRegistry


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
            print_warning("\nInstallation cancelled by user or running in non-interactive environment.")
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
        "--dry-run", action="store_true", default=False, help="Simulate actions without applying system changes"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", default=False, help="Enable verbose execution output"
    )
    parser.add_argument("--debug", action="store_true", default=False, help="Display full tracebacks upon failure")

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # init
    subparsers.add_parser(
        "init",
        parents=[common_parser],
        help="Initialize user directories, configuration, and verify prerequisites",
    )

    # list
    subparsers.add_parser("list", parents=[common_parser], help="List all managed tools and their current status")

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
    config_get = config_sub.add_parser("get", parents=[common_parser], help="Get a configuration value")
    config_get.add_argument("key", help="Key name to inspect")
    config_set = config_sub.add_parser("set", parents=[common_parser], help="Set a configuration value")
    config_set.add_argument("key", help="Key name to update (e.g. esim_path)")
    config_set.add_argument("value", help="Value to set")
    config_sub.add_parser("show", parents=[common_parser], help="Show full configuration")

    # install
    install_parser = subparsers.add_parser("install", parents=[common_parser], help="Install a tool or all tools")
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
        "rollback", parents=[common_parser], help="Roll back a tool to its previously recorded version"
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
    subparsers.add_parser("doctor", parents=[common_parser], help="Run comprehensive system health checks")

    # cache
    cache_parser = subparsers.add_parser("cache", parents=[common_parser], help="Manage installer download cache")
    cache_sub = cache_parser.add_subparsers(dest="cache_action")
    cache_sub.add_parser("list", parents=[common_parser], help="List cached installers")
    cache_sub.add_parser("clear", parents=[common_parser], help="Clear cached installers")

    # logs
    logs_parser = subparsers.add_parser("logs", parents=[common_parser], help="Display recent action logs")
    logs_parser.add_argument("--tail", type=int, default=30, help="Number of log entries to show")

    # report
    report_parser = subparsers.add_parser(
        "report", parents=[common_parser], help="Export system status report as Markdown"
    )
    report_parser.add_argument("--output", "-o", help="Target output file path")

    # version
    subparsers.add_parser("version", parents=[common_parser], help="Print eSim Tool Manager version")

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

        if args.command == "init":
            return cmd_init(args, config_mgr)
        elif args.command == "list":
            return cmd_list(args, detector)
        elif args.command == "check":
            return cmd_check(args, detector, dep_checker)
        elif args.command == "install":
            return cmd_install(args, installer)
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
