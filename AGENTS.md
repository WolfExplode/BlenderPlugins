# Agent guide: Blender references and tooling

This repository contains Blender add-ons and scripts. Read the relevant add-on's
README before changing it. For Blender API questions, check the version used by
that add-on and prefer version-matched documentation over assumptions from source.

## Local Blender references

On the maintainer's Windows machine, a sibling checkout at `../blender-mcp`
provides the following. These paths are outside this repository and may be
absent in other environments; check that they exist before using them.

| Reference | Path relative to this repo | Use |
| --- | --- | --- |
| Offline Blender Python API and manual | `../blender-mcp/docs/Blender Documentation/` | Confirm API names, signatures, enum values, and user-facing behavior. The installed copy is for Blender 5.1. |
| Blender source checkout | `../blender-mcp/reference/blender/` | Investigate implementation details after checking the versioned docs. Currently tracks Blender `main` (5.3 alpha), so APIs found here may not exist in 5.1. |
| Blender Dev MCP server | `../blender-mcp/` | Tool implementation, setup notes, and headless Blender runner. Start with its `README.md`. |

Useful source locations under `../blender-mcp/reference/blender/`:

- `scripts/startup/bl_ui/` for Blender's panels and menus.
- `scripts/startup/bl_operators/` and `scripts/modules/bpy_extras/` for Python operator and helper examples.
- `source/blender/makesrna/intern/` for RNA definitions, and `source/blender/editors/` for native operator behavior.
- `tests/python/` for executable API examples.

Search a relevant subtree rather than the entire Blender source tree. If the
sibling checkout is unavailable, use the official Blender Python API and manual
for the target release: <https://docs.blender.org/api/> and
<https://docs.blender.org/manual/en/latest/>.

## MCP tools

When the Blender MCP server is connected, look for tools named `mcp__blender__*`
(some clients display them as `blender.*`). Check the tools actually exposed in
the current session; a repository file cannot enable an MCP server.

1. Use `blender_docs` first for version-specific API and manual lookups. It
   reads the offline docs and does not require Blender to be running.
2. Use `execute_blender_code` to inspect live `bpy` values in the current scene;
   `get_scene_info`, `get_object_info`, and `get_stderr_log` can answer common
   questions without custom code.
3. Use `get_viewport_screenshot` when a visual check is needed. For edits to a
   live `.blend`, inspect the tool's write and undo behavior in the sibling
   MCP README before acting on unsaved work.

For isolated tests, the sibling MCP repo also provides `tools/headless.py` to
run a script in a separate Blender process. The local Blender 5.1 installation
is at `C:/Program Files/Blender Foundation/Blender 5.1/`; verify the executable
path and version before relying on it.
