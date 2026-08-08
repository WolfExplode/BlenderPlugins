## Variable Playback Baker

**File**: `cyclic animation.py`

**Purpose**: Bake a cyclic/looping animation (e.g. a walk cycle) onto a target's timeline with a variable playback rate driven by a BPM curve, instead of a fixed constant speed.

**Key features**
- **BPM-driven playback**: Reads a BPM curve (and optional strength-influence curve) to vary how fast the source animation plays back over time.
- **Source animation support**: Works with object animation data and shape key animation data.
- **Keyframe / driver helpers**: Keyframe the BPM value onto the source, or copy BPM as a new driver.
- **Bake to new animation**: Bakes the result to a new action, with an option to overwrite an existing bake.

**UI location**
- `3D Viewport` → Sidebar (`N`) → `Animation` tab → `Variable Playback Baker` panel.

**Basic usage**
1. Pick a **Source Object** and **Source Action** with existing animation.
2. Set up a BPM curve (and optionally a strength-influence curve) to control playback speed over time.
3. Click **Bake** to produce a new action where playback speed follows the BPM curve.
