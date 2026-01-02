## Viewport Object Display Tools

**File**: `Viewport Display Objects.py`

**Purpose**: Quickly control object name/bounds visibility and simple color-tagging in the viewport based on collections and name fragments.

**Key features**
- **Collection-based display toggles**
  - Pick a **Main Collection** and:
    - Show/hide **object names**.
    - Show/hide **bounding boxes**.
- **Color collection & tagging**
  - Choose a **Color Collection** whose objects should receive display colors.
  - Define a list of **tag–color pairs**:
    - If a tag appears in an object’s name (case-insensitive), that object gets the associated color.
  - Works recursively through child collections of the color collection.
- **Collection picker**
  - Operator that picks the **deepest collection** of the currently active object and assigns it as the Main Collection.
- **Copy/paste color mappings**
  - Serialize the list of tag–color pairs to JSON and put it on the clipboard.
  - Paste mappings back from the clipboard into another scene or file.

**UI location**
- `3D Viewport` → Sidebar (`N`) → `Tool` tab → **Object Display Tools** panel.

**Main controls**
- **Main Collection**
  - Pick a collection or use the eyedropper button to grab it from the active object.
  - Toggles:
    - **Names** – show/hide `show_name` on objects in the Main Collection.
    - **Bounds** – show/hide `show_bounds` on objects in the Main Collection.
    - **Colors** – enable/disable applying per-object display colors.
- **Color Mapping Settings**
  - **Color Collection**: collection used as the target for color tagging.
  - **Tag-Color Mapping** list:
    - Each entry has a **Tag** string and a color picker.
    - Use `+` and `-` buttons to add/remove entries.
    - Use **Copy Color Mappings** / **Paste Color Mappings** to share mappings via clipboard.

**Basic usage**
1. Open the **Object Display Tools** panel in the 3D Viewport sidebar.
2. Set **Main Collection** and toggle:
   - **Names** to see object names.
   - **Bounds** to show their bounding boxes.
3. Set a **Color Collection** (often a parent collection for logical groups).
4. Create tag–color pairs like:
   - `wall` → grey
   - `glass` → light blue
   - `char_` → distinct color for characters
5. Enable **Colors** to apply the display colors based on those tags across the Color Collection and its children.


