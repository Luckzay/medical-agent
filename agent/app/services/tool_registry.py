from __future__ import annotations

from typing import Any

from app.models.tooling import SkillDefinition, ToolDefinition


class DuplicateToolError(ValueError):
    pass


class DuplicateSkillError(ValueError):
    pass


class UnknownToolReferenceError(ValueError):
    pass


class ToolRegistry:
    """In-process immutable-definition registry for tools and composed skills."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition[Any, Any]] = {}
        self._skills: dict[str, SkillDefinition] = {}

    def register_tool(self, definition: ToolDefinition[Any, Any]) -> None:
        if definition.name in self._tools:
            raise DuplicateToolError(f"Tool '{definition.name}' is already registered")
        self._tools[definition.name] = definition

    def register_skill(self, definition: SkillDefinition) -> None:
        if definition.name in self._skills:
            raise DuplicateSkillError(f"Skill '{definition.name}' is already registered")
        missing = sorted(set(definition.tool_names) - self._tools.keys())
        if missing:
            raise UnknownToolReferenceError(
                f"Skill '{definition.name}' references unknown tools: {', '.join(missing)}"
            )
        self._skills[definition.name] = definition

    def get_tool(self, name: str) -> ToolDefinition[Any, Any]:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool '{name}'") from exc

    def list_tools(self) -> list[dict[str, Any]]:
        return [self._tools[name].public_metadata() for name in sorted(self._tools)]

    def list_skills(self) -> list[dict[str, Any]]:
        return [self._skills[name].model_dump(mode="json") for name in sorted(self._skills)]
