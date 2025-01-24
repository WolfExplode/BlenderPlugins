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
- Copy shape keys between objects.  
- Transfer shape key values (e.g., facial expressions).  
- Swap the basis shape key with another.  
- Reset all shape key values to zero.  
- Remove unused zero-value shape keys.  

**How to Use**:  
1. **Installation**:  
   - Install like the BoneRenamer script.  
   - Requires Blender 4.1.0 or later.  

2. **Usage**:  
   - Open the *Tool* tab in the 3D View sidebar.  
   - **Copy Shape Keys**:  
     - Pick a *Source* and *Target* object.  
     - Click *Copy Shapekeys* to duplicate keys (geometry only).  
   - **Transfer Values**:  
     - Copies slider values from source to target (names must match).  
   - **Swap Basis**:  
     - Select a shape key and click *Swap with Basis* to exchange it with the basis shape.  
   - **Reset Values**: Sets all sliders to zero.  

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
