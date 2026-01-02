## HairTools Sculpting Keymap Activator

**File**: `HairTools_Keymap_Fixer.py`

**Purpose**: Ensure the `sculpt_curves.brush_stroke` keymap stays enabled for Hair Tools / curves sculpting, even if another addon disables it.

**Key features**
- **Keymap repair**:
  - Looks up the **Sculpt Curves** keymap in the user keyconfig.
  - Ensures every `sculpt_curves.brush_stroke` entry is active.
- **Automatic repair on mode change**:
  - A depsgraph update handler tracks mode changes.
  - Whenever you enter `SCULPT_CURVES` mode, the script re-enables the stroke keymap.
- **Manual repair operator**:
  - Operator `object.restore_all_keymaps` can be called to fix the keymap on demand.

**UI / access**
- No dedicated panel; it runs automatically once installed and enabled.
- Manual operator is available via the F3 search menu:
  - Search for **Restore Sculpt Curves Keymap**.

**Basic usage**
1. Install and enable the addon.
2. Whenever you switch into **Sculpt Curves** mode, the addon ensures `sculpt_curves.brush_stroke` is active.
3. If brush strokes ever stop working, run **Restore Sculpt Curves Keymap** from the search menu to force a repair.


