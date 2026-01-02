## Export Geometry Nodes to Text

**File**: `ExportGeoNodesTxt.py`

**Purpose**: Export a Geometry Nodes tree to a human-readable `.txt` file listing all nodes, their inputs/outputs, and connections.

**Key features**
- **Node listing**: Writes each node’s type and name.
- **Input values**: For every input socket, stores either its default value or marks it as `Linked`.
- **Outputs**: Lists all output sockets.
- **Connections**: Records links in the form `FromNode → ToNode (InputName)`.
- **Per-tree export**: Exports only the selected `GeometryNodeTree`.

**UI location**
- `Geometry Node Editor` → Sidebar (`N`) → `Export` tab → **Export Geometry Nodes** panel.

**Basic usage**
1. In the Geometry Node Editor, choose a `Geometry Node Tree` in **Export Geo Tree**.
2. Set **Export Path** to a folder (can be relative to the blend file).
3. Click **Export Geometry Nodes**.
4. A text file named `<TreeName>_nodes.txt` will be created in the chosen directory with the node graph details.


