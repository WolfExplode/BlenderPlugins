## Guard Edit Mode for MACHIN3tools

**File**: `Guard Edit Mode for MACHIN3tools.py`

**Purpose**: Prevent entering Edit Mode on extremely heavy meshes by patching MACHIN3tools operators and `object.mode_set`, with optional debug logging.

**Key features**
- **Vertex-count guard**:
  - Checks the active mesh’s vertex count before allowing Edit Mode.
  - Blocks Edit Mode when the count exceeds a configurable threshold.
- **Operator patching**:
  - Wraps `machin3.edit_mode`, `machin3.mesh_mode`, and `object.mode_set` to enforce the guard.
  - Handles both `execute()` and `invoke()` where needed.
- **User preferences**:
  - `Vertex Threshold`: maximum allowed vertices before blocking.
  - `Enable debug logging`: print detailed events and errors to the system console.
- **Non-destructive**:
  - On unregister, restores original operator methods.

**UI location**
- `Edit` → `Preferences` → `Add-ons` → search for **Guard Edit Mode for MACHIN3tools (debug)**.

**Basic usage**
1. Install and enable the addon.
2. In the add-on preferences:
   - Set **Vertex Threshold** (e.g. `1,000,000`).
   - Optionally enable **debug logging** to see guard decisions in the console.
3. Use MACHIN3tools (or `Tab`/mode switching) as usual:
   - If the active mesh exceeds the threshold when attempting to enter Edit Mode, a popup warns you and the action is cancelled.
4. Disable or uninstall the addon to remove all patches and restore original behavior.


