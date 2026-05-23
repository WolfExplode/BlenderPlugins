## Variable Playback / Cyclic Animation Tools

**File**: `cyclic animation.py`

**Purpose**: Bake cyclic animations whose playback speed, strength, and even chosen action can vary over time, driven by curve data.

**Key features**
- **Variable BPM playback**: Uses a curve object (time on X, BPM on Y) to control playback speed over time. Each beat plays the **entire** source action once; cycle length on the timeline is `scene FPS × (60 / BPM)` frames (e.g. 60 BPM @ 24 fps → 24 frames per cycle, two cycles in 48 frames).
- **Loop / fence-post**: Loop clips are often keyed `0..N` with frame `N` identical to frame `0` (e.g. `0..24` at 24 fps = 1 s, 25 keys, 24 frames of motion). The baker walks every key index `0..N` in order via a running step counter, so the seam frame (e.g. output 24 → source 24) is not placed one frame early and later cycles do not skip the loop start.
- **Strength curve**: Optional second curve controls an overall influence/strength multiplier across the bake.
- **Single or multi-action mode**:
  - Single mode: remap one action (or a specific slot/layer) over time.
  - Multi mode: define multiple animation slots with weighted random selection per loop.
- **Random variations**:
  - Per-loop random intensity multiplier.
  - Per-loop random speed multiplier (with seed control for reproducibility).
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
8. Click **Bake** to create a new baked action with the chosen options.


