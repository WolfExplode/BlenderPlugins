# Blender Scripts Repository
A collection of Blender scripts for rigging, shape key management, and texture handling.

---

## 📁 Scripts Overview

### 1. **BoneRenamer_v1.2.py**  
**Description**: Renames armature bones between different naming conventions (e.g., MMD, XNALara, Rigify) and translates Japanese bone names to English.  
**Features**:  
- Supports 11 bone-naming formats (MMD, DAZ/Poser, Sims 2, etc.).  
- Option to include finger bones.  
- Japanese-to-English translation for bone names.  
- Toggle bone name visibility in the viewport.  

**How to Use**:  
1. **Installation**:  
   - Save the script in Blender's `Scripts` folder or install via *Edit > Preferences > Add-ons > Install*.  
   - Enable the add-on "Bone Renamer" in the add-ons list.  

2. **Usage**:  
   - Open the panel in the 3D View under the *Animation* tab (sidebar).  
   - Select an armature using the eyedropper tool.  
   - Choose **Source** and **Target** formats (e.g., "MMD English" to "Rigify").  
   - Click *Rename Bones* to apply.  
   - Use *Translate Japanese Names* for MMD Japanese bones.  

---

### 2. **Shapekey_Tools.py**  
**Description**: Tools for managing shape keys, including transferring, resetting, and modifying them.  
**Features**:  
1. Shapekey Transfer Tools
- 🔄 Copy Shapekeys
Transfer shape keys (including vertex data and value ranges) from a source object to multiple targets.
- 📤 Transfer Values
Copy shape key values (and min/max ranges) between objects, even if topology differs.
2. Shapekey Management
- 🔄 Swap with Basis
Exchange the position/coordinates of any shape key with the Basis shape key.
- 🗑️ Remove Zero-Value Keys
Delete all shape keys with a value of 0 across selected objects.
- 🚫 Remove All Drivers
Clear all drivers attached to shape keys on the active object.
3. Preset System
- 💾 Save Presets
Store current shape key values as named presets.
- 📥 Load Presets
Apply saved presets to any object with matching shape keys.
- 🗑️ Delete Presets
Manage and remove unused presets.

**How to Use**:  
1. **Installation**:  
   - Install like the BoneRenamer script.  
   - Requires Blender 4.1.0 or later.  

2. **Usage**:
Access the Tools
Navigate to the 3D Viewport Sidebar (N key) → Tool tab.

Key Operations
Transfer Shapekeys
Select a source object (must have shape keys).
Choose target type :
Single Object : Pick a specific target.
Multiple Objects : Use selected objects (excluding the source).
Click Copy Shapekeys or Transfer Values.
Swap Basis
Select an object with shape keys.
Choose a shape key from the dropdown.
Click Swap with Basis to exchange positions.
Presets
Save : Enter a preset name and click Save.
Load/Delete : Select a preset from the list and use the buttons.

---
### 3. **ReloadTextures.py**  
**Description**: Reloads all textures in the project to reflect external edits (e.g., updated image files).  

**How to Use**:  
1. **Installation**:  
   - Install via Blender's add-on manager.  

2. **Usage**:  
   - Open the *Image Editor* workspace.  
   - Go to the header menu (top bar) and click *Image > Reload Textures*.  
   - Alternatively, search for "Reload Textures" in the F3 search menu.  

---

## 🔧 Compatibility  
- Tested on Blender 4.1.0. BoneRenamer and Shapekey Tools may work on earlier 3.x versions.  
- Scripts are independent and can be used together.  

## 📝 Notes  
- Backup blends before using BoneRenamer to avoid irreversible bone name changes.  
- Shapekey Tools requires objects to have matching topology for accurate transfers.  
- ReloadTextures will not update textures if the file paths are broken.  
