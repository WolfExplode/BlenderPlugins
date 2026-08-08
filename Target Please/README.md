## Target, Please!

**File**: `Target Please.py`

**Purpose**: Create a tracking target with a smart orbit pivot for cameras and lights — orbit around a subject without manually parenting/unparenting.

**Key features**
- **Smart pivot empty**: Adds a pivot empty that the camera/light orbits around.
- **Auto Child Of**: A `Child Of` constraint is added only while rotating the pivot (orbiting), and removed as soon as rotation ends or a move starts.
- **Track To aiming**: When not rotating, a `Track To` constraint keeps the camera/light aimed at the target.

**UI location**
- `3D Viewport` → operator search / addon panel (see script for exact menu entry).

**Basic usage**
1. Select the camera or light you want to orbit, then run the "Target, Please!" operator to create the pivot + target.
2. Use **R** (rotate) on the pivot to orbit — aiming and parenting are handled automatically.
3. Use **G**/**S** to move or scale as normal; the Child Of constraint is removed automatically.
