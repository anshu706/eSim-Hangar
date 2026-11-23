"""Dependency resolution and verification for managed tools."""

from dataclasses import dataclass

from esim_tool_manager.detector import ToolDetector, ToolStatus
from esim_tool_manager.registry import ToolRegistry


@dataclass
class DependencyCheckResult:
    """Result of checking a tool's prerequisites."""

    tool: str
    is_valid: bool
    missing_dependencies: list[str]
    incompatible_dependencies: list[str]
    details: list[str]


class DependencyChecker:
    """Evaluates inter-tool dependencies declared in tools.yaml."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        detector: ToolDetector | None = None,
    ):
        self.registry = registry or ToolRegistry()
        self.detector = detector or ToolDetector(registry=self.registry)

    def check_tool_dependencies(
        self, tool_name: str, cached_statuses: dict[str, ToolStatus] | None = None
    ) -> DependencyCheckResult:
        """Check all declared prerequisites for a given tool."""
        spec = self.registry.get_tool(tool_name)
        statuses = cached_statuses or self.detector.detect_all()

        missing: list[str] = []
        incompatible: list[str] = []
        details: list[str] = []

        for dep_name in spec.dependencies:
            dep_status = statuses.get(dep_name)
            if not dep_status or dep_status.status == "MISSING":
                missing.append(dep_name)
                details.append(
                    f"Required dependency '{dep_name}' is MISSING. Fix: esim-tool-manager install {dep_name}"
                )
            elif dep_status.status == "INCOMPATIBLE":
                incompatible.append(dep_name)
                details.append(
                    f"Required dependency '{dep_name}' version {dep_status.installed_version} "
                    f"is INCOMPATIBLE (minimum {dep_status.required_version})."
                )

        is_valid = len(missing) == 0 and len(incompatible) == 0
        return DependencyCheckResult(
            tool=tool_name,
            is_valid=is_valid,
            missing_dependencies=missing,
            incompatible_dependencies=incompatible,
            details=details,
        )

    def check_all_dependencies(self) -> dict[str, DependencyCheckResult]:
        """Check prerequisites for all registered tools."""
        statuses = self.detector.detect_all()
        results: dict[str, DependencyCheckResult] = {}
        for tool_name in self.registry.get_all_tools():
            results[tool_name] = self.check_tool_dependencies(tool_name, cached_statuses=statuses)
        return results
