## Variable Playback / Cyclic Animation Tools

**File**: `cyclic animation.py`

**Purpose**: Bake cyclic animations whose playback speed, strength, and even chosen action can vary over time, driven by curve data.

**Key features**
- **Variable BPM playback**: Uses a curve object (time on X, BPM on Y) to control playback speed over time.
- **Strength curve**: Optional second curve controls an overall influence/strength multiplier across the bake.
- **Single or multi-action mode**:
  - Single mode: remap one action (or a specific slot/layer) over time.
  - Multi mode: define multiple animation slots with weighted random selection per loop.
- **Random variations**:
  - Per-loop random intensity multiplier.
  - Per-loop random speed multiplier (with seed control for reproducibility).
- **Preview helper**: Creates an Empty with an action that visualizes phase, rate, and chosen animation index over time.
- **Smart baking**:
  - Bakes only curves that exist for the chosen slot/datablock.
  - Optional F-curve simplification to reduce keyframe count.

**UI location**
- `3D Viewport` → Sidebar (`N`) → `Animation` tab → **Variable Playback Baker** panel.

**Basic workflow**
1. **Prepare actions** on an object (and/or its shape keys) as usual.
2. **Create a BPM curve**:
   - Use a Curve object where:
     - X = time (minutes, scaled internally),
     - Y = BPM (beats per minute).
   - Assign it as **BPM Curve**.
3. (Optional) **Create a Strength curve**:
   - X = time (minutes), Y = influence (1.0 = 100%).
   - Assign it as **Strength Curve**.
4. In **Variable Playback Baker**:
   - Pick a **Source Object** with animation.
   - Choose **Single** or **Multi-Animation** mode:
     - In single mode, pick a single action/slot.
     - In multi mode, add slots, select actions and set weights (%).
5. Set **Output Frame Range** on the scene (start/end).
6. Click **Read BPM Data** (and **Read Strength Data**, if used) to sample the curves.
7. Adjust:
   - **Baked Speed** (global speed multiplier),
   - **Random Intensity per Loop** (range and seed),
   - **Random Speed per Loop** (range).
8. Use **Preview** to generate the visualization Empty.
9. Click **Bake** to create a new baked action with the chosen options.


