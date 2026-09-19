## World-Space Brush Radius for Texture Painting

**File**: `world-space brush.py`

**Purpose**: Keep the texture paint brush size consistent in **world units** (BU) instead of screen pixels, using the 3D cursor depth as reference.

**Key features**
- **World-space brush radius**
  - Computes how many pixels correspond to 1 Blender Unit at the 3D cursor.
  - Adjusts the brush pixel size so the on-mesh footprint remains constant when zooming in/out.
  - Respects **Unified Size** if enabled.
- **Cursor-based depth**
  - Uses the 3D cursor position as the depth reference for size calculations.
  - Optional operator to move the 3D cursor to the paint surface on left mouse.
- **Interactive adjustment**
  - Press **F** in texture paint mode to change the brush size as usual.
  - On release/confirm, the addon updates the stored world-space diameter to match your chosen size.
- **Debug overlay**
  - Optional viewport overlay showing:
    - Pixels-per-unit at cursor.
    - Desired and applied brush radii in pixels.
  - Logs details to the console when enabled.

**Additional operator**
- `paint.cursor_on_lmb`:
  - In `Texture Paint` mode, intercepts **Left Mouse** and calls the same action as Shift+RMB:
    - Snaps the 3D cursor to the clicked surface.
  - Ensures the cursor (and thus the world-size reference) tracks where you are painting.

**UI location**
- `Texture Paint` mode → 3D Viewport Sidebar → `Tool` tab → Brush settings area:
  - Under the brush radius controls:
    - **Scene Radius** toggle (enable world-space sizing).
    - **Debug Overlay** icon toggle (console + overlay).
- Scene properties:
  - `Scene.wltp` – main settings.
  - `Scene.wltp_dbg` – debug overlay settings.

**Basic workflow**
1. Enter **Texture Paint** mode and select a paint brush.
2. Enable **Scene Radius** in the brush settings UI.
3. Place the 3D cursor at the typical painting depth (use LMB with the addon’s cursor operator, or Shift+RMB).
4. Optionally press **F**, pick a brush size you like, and release – this redefines the world-space diameter.
5. Zoom in/out and keep painting: the visible brush footprint on the surface will stay approximately constant in world units.


