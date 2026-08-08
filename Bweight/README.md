## Bweight

**File**: `__init__.py` (+ `ops.py`, `normalize.py`, `keymap.py`)

**Purpose**: Keyboard-driven weight painting — smooth/sharpen and grow/shrink the active vertex group's weights without leaving the brush, plus scoped auto-normalize across selected bones.

**Key features**
- **Smooth / sharpen**: `Ctrl+Shift+=` / `Ctrl+Shift+-` blur or sharpen weights on the active vertex group.
- **Grow / shrink**: `Ctrl+=` / `Ctrl+-` expand or contract the weighted region.
- **Ctrl-inverted weight gradient**: holding Ctrl while painting inverts the gradient direction.
- **Scoped auto-normalize**: normalizes weights across the selected bones/vertex groups only, instead of all groups on the mesh.

**UI location**
- `Weight Paint` mode → keymap-driven, no panel.

**Basic usage**
1. Enter Weight Paint mode on a mesh with an active vertex group.
2. Use the smooth/sharpen and grow/shrink hotkeys to adjust weights interactively.
3. Enable auto-normalize scoping when working with a specific bone selection to avoid disturbing unrelated groups.
