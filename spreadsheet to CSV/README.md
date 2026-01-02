## Mesh Vertices to CSV

**File**: `spreadsheet to CSV.py`

**Purpose**: Export the vertices of the active mesh object to a simple CSV file next to the `.blend`, suitable for spreadsheet analysis.

**Key features**
- **Mesh vertex export**:
  - Uses the *evaluated* mesh (including modifiers) of the active object.
  - Writes each vertex coordinate as a row: `x, y, z`.
- **Clean numeric output**:
  - Coordinates are rounded to **3 decimal places** for readability.
- **Automatic file naming**:
  - CSV file is named `<ObjectName>.csv` (spaces replaced with underscores).
  - Saved in the same directory as the current `.blend` file.

**How to use**
1. Select a **mesh** object in Object Mode.
2. Run the script (e.g. from the Text Editor or as a one-off script).
3. The script:
   - Validates that the active object is a mesh.
   - Evaluates the mesh and iterates its vertices.
   - Appends rows to `<BlendFolder>/<ObjectName>.csv`, creating a header row (`x,y,z`) if the file doesn’t exist.
4. Open the resulting CSV in Excel, LibreOffice, or any spreadsheet tool for inspection or further processing.


