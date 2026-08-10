## Import Export Geo Nodes

**File**: `ExportImportGeoNodes.py`

**Purpose**: Export a Geometry Nodes tree to JSON and rebuild it from JSON — useful for sharing node setups as text (e.g. with an LLM) instead of `.blend` files.

**Key features**
- **Export**: Serializes the active geometry node tree (nodes, sockets, links, and most node properties) to a JSON block.
- **Import**: Rebuilds a node tree from a JSON spec, resolving node types and socket references by index or name.
- **LLM-friendly parsing**: Accepts raw JSON, fenced ` ```json ` blocks, or JSON embedded in surrounding text.

**UI location**
- `Geometry Node Editor` → Sidebar (`N`) → `Import/Export` tab.

**Basic usage**
1. Open a Geometry Nodes tree in the Geometry Node Editor.
2. Use **Export** to copy the current tree as JSON.
3. Use **Import** and paste a JSON spec (or fenced JSON block) to rebuild a tree.
