## Shapekey Tools

**File**: `Shapekey_Tools.py`

**Purpose**: A toolbox for managing, transferring, cleaning, and presetting shape keys across one or many mesh objects.

**Main panels**
- **Shapekey Tools** panel  
  `3D Viewport` → Sidebar (`N`) → `Tool` tab → **Shapekey Tools**
- **Shapekey Presets** panel  
  Same location, shown just below the main tools panel.

---

### Core features

- **Transfer shapekeys (geometry + ranges)**
  - Copy full shape key data (vertex positions, slider min/max, values) from a **source** object to:
    - A single **target** object, or
    - All selected objects (multi-mode).
  - Automatically adds missing shape keys to targets and matches them by name.

- **Transfer only values**
  - Copy just the **value** (and min/max) of matching shape keys from a source object to:
    - One target, or
    - All selected objects that already have shape keys.

- **Reset and clean**
  - **Reset Values**: Zero all non-basis shape keys on selected objects.
  - **Remove Zero Shapekeys**: Delete all keys whose current value is effectively 0, across selected objects.
  - **Remove All Drivers**: Remove all drivers attached to shape key values on the active object.

- **Swap with Basis**
  - Swap any non-basis shape key with the Basis:
    - Exchanges vertex coordinates between the selected key and the basis.
    - Swaps their names so your chosen expression/morph becomes the new basis.

- **Create Vertex Group from Shape Key**
  - Creates a vertex group that includes only vertices affected by the active shape key.
  - Uses a displacement threshold to detect changed vertices and names the group `sk_<sanitized_shape_key_name>`.

---

### Preset system

- **Text-based presets**
  - Stores presets in a Text datablock named `ShapekeyPresets` inside the .blend file.
  - Each preset is a section:
    - `[PresetName]`
    - `ShapeKeyName = value`

- **Save preset**
  - In **Shapekey Presets**:
    1. Enter a name in **Preset Name**.
    2. Click **Save Shapekey Preset**.
  - Saves all non-basis key values on the active object.

- **Load preset**
  - Choose a preset from the dropdown.
  - Click **Load Shapekey Preset**:
    - Applies stored values to matching shape keys on the active object.
    - Reports any keys that were missing on the object.

- **Delete preset**
  - Select a preset from the dropdown.
  - Click **Delete Shapekey Preset** to remove that section from the text block.

---

### Basic workflow

1. **Transfer shapekeys**
   - Select a **source** mesh with shape keys.
   - In **Shapekey Tools**, use the eyedropper or search to pick:
     - **Source Object**
     - **Target** (single) or choose **Multiple** and select additional objects.
   - Click **Transfer Shapekeys** to copy geometry, or **Transfer Values** to only copy values.

2. **Reset / clean**
   - Select one or more objects with shape keys.
   - Use:
     - **Reset Values**
     - **Remove Zero Value Shapekeys**
     - **Remove All Drivers**
   - to tidy up animation or presets.

3. **Presets**
   - Pose/tune shape keys on one object.
   - Save a preset, then recall it later or apply it to other meshes with matching keys.


