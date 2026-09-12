"""Draw Things gRPC plugin for Hermes Agent."""

from __future__ import annotations

from pathlib import Path

if __package__:
    from . import schemas, tools
else:  # Allows direct execution from the plugin root.
    import schemas  # type: ignore
    import tools  # type: ignore

_TOOLSET = "drawthings"


def register(ctx):
    ctx.register_tool(
        name="drawthings_list",
        toolset=_TOOLSET,
        schema=schemas.DRAWTINGS_LIST,
        handler=tools.drawthings_list,
        check_fn=lambda: True,
        requires_env=[],
        description="List Draw Things models/LoRAs/ControlNets",
        emoji="🎨",
    )
    ctx.register_tool(
        name="drawthings_generate",
        toolset=_TOOLSET,
        schema=schemas.DRAWTINGS_GENERATE,
        handler=tools.drawthings_generate,
        check_fn=lambda: True,
        requires_env=[],
        description="Generate via Draw Things gRPC",
        emoji="🖼️",
    )

    skills_dir = Path(__file__).parent / "skills"
    if skills_dir.exists():
        for child in sorted(skills_dir.iterdir()):
            skill_md = child / "SKILL.md"
            if child.is_dir() and skill_md.exists():
                ctx.register_skill(child.name, skill_md)
