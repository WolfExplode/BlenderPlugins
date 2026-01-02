## ScreenshotNodes – High-Quality Node Tree Screenshots

**File**: `ScreenshotNodes.py`

**Purpose**: Capture high-quality screenshots of a node tree (entire tree or only selected nodes), auto-stitched from multiple tiles using OpenImageIO.

**Key features**
- **Whole-tree or selection capture**:
  - Screenshot the entire active node tree.
  - Or only the currently selected nodes.
- **Tilized capture & stitching**:
  - Uses a modal timer to pan the node editor and capture tiles.
  - Tiles are stitched into a single high-resolution image via OpenImageIO.
- **Automatic cropping & styling**:
  - Temporarily adjusts theme settings (grid, scrollbars, wire color, selection color) for clean output.
  - Restores user theme and view settings afterwards.
- **Configurable save location & color**:
  - Defaults to a `NodesShots` subfolder next to the `.blend` file.
  - Fallback/secondary directory configurable in add-on preferences.
  - Custom **Node Outline Color** for selected/active nodes in the screenshot.

**UI location**
- **Context Menu** in the Node Editor:
  - Right-click in the Node Editor → `PrintNodes` menu:
    - **Take Screenshot Of Whole Tree**
    - **Take Screenshot Of Selected Nodes**
- **Preferences**:
  - `Edit` → `Preferences` → `Add-ons` → find **ScreenshotNodes** to configure:
    - Secondary Directory
    - Always Use Secondary Directory
    - Node Outline Color

**Basic usage**
1. Open the desired node editor (Shader, Geometry, etc.) and set up your node tree.
2. Optionally select a subset of nodes if you only want a partial screenshot.
3. Right-click in the node editor and choose:
   - **Take Screenshot Of Whole Tree**, or  
   - **Take Screenshot Of Selected Nodes**.
4. Wait for the modal capture to finish (you can cancel with Right Mouse or `Esc`).
5. The stitched screenshot is saved as `NodeTreeShotYYMMDD-HHMMSS.jpg` in:
   - The `NodesShots` folder next to your blend file, or
   - The secondary directory specified in add-on preferences.


