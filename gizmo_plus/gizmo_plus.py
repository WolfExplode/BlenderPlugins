import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from math import radians
from mathutils import Matrix, Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_location_3d

bl_info = {
    "name": "Gizmo Plus",
    "author": "WXP",
    "version": (3, 1, 0),
    "blender": (4, 0, 0),
    "location": "3D View, automatic with the Move/Rotate/Scale/Transform tools",
    "description": "Keeps the transform gizmo on screen when its object is out of view (Softimage-style)",
    "category": "3D View",
}

# Keep the pinned manipulator this many pixels away from the viewport edges.
EDGE_MARGIN = 130.0

# Which handle sets to show for each transform tool. The pinned manipulator
# only appears while the pivot is off-screen — on screen, the native tool
# gizmo is already visible and ours stays hidden.
TOOL_MODES = {
    "builtin.move": {'TRANSLATE'},
    "builtin.rotate": {'ROTATE'},
    "builtin.scale": {'SCALE'},
    "builtin.transform": {'TRANSLATE', 'ROTATE', 'SCALE'},
}

AXES = (
    ((1.0, 0.2, 0.32), Matrix.Rotation(radians(90), 4, 'Y')),   # X
    ((0.55, 0.86, 0.0), Matrix.Rotation(radians(-90), 4, 'X')),  # Y
    ((0.17, 0.56, 1.0), Matrix.Identity(4)),                     # Z
)


def active_tool_modes(context):
    try:
        tool = context.workspace.tools.from_space_view3d_mode(
            context.mode, create=False
        )
    except Exception:
        return None
    if tool is None:
        return None
    return TOOL_MODES.get(tool.idname)


def gizmo_pivot(context):
    if context.mode == 'POSE':
        ob = context.object
        bones = context.selected_pose_bones
        if not bones:
            return None
        return sum(
            ((ob.matrix_world @ b.matrix).translation for b in bones), Vector()
        ) / len(bones)
    sel = context.selected_objects
    if not sel:
        return None
    return sum((o.matrix_world.translation for o in sel), Vector()) / len(sel)


def manipulator_position(region, rv3d, pivot):
    """Where to draw the manipulator: the pivot itself while it is on screen,
    otherwise a point clamped inside the viewport at the pivot's view depth.
    Returns (position, was_clamped)."""
    depth_ref = pivot
    # Behind the camera the pivot can't be projected; anchor the depth to a
    # point in front of the eye instead so the pinned gizmo stays visible.
    if (rv3d.view_matrix @ pivot).z > -0.01:
        inv = rv3d.view_matrix.inverted()
        eye = inv.translation
        forward = -Vector((inv[0][2], inv[1][2], inv[2][2]))
        depth_ref = eye + forward * max((pivot - eye).length, 1.0)
        co2d = None
    else:
        co2d = location_3d_to_region_2d(region, rv3d, pivot)
    if co2d is None:
        co2d = Vector((region.width / 2, region.height / 2))
    x = min(max(co2d.x, EDGE_MARGIN), region.width - EDGE_MARGIN)
    y = min(max(co2d.y, EDGE_MARGIN), region.height - EDGE_MARGIN)
    if x == co2d.x and y == co2d.y and depth_ref is pivot:
        return pivot, False
    return region_2d_to_location_3d(region, rv3d, Vector((x, y)), depth_ref), True


class GIZMOPLUS_GGT_manipulator(bpy.types.GizmoGroup):
    bl_idname = "GIZMOPLUS_GGT_manipulator"
    bl_label = "Gizmo Plus Manipulator"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT', 'SHOW_MODAL_ALL'}

    @classmethod
    def poll(cls, context):
        return (
            active_tool_modes(context) is not None
            and gizmo_pivot(context) is not None
        )

    # Layout constants from Blender's transform_gizmo_3d.cc for the combined
    # (Transform tool) gizmo: stemless move cones at 1.2, scale boxes
    # shortened to 0.9, center circle at 0.2.
    COMBINED_ARROW_LENGTH = 1.4
    COMBINED_SCALE_LENGTH = 0.8
    CENTER_SCALE = 0.2

    def setup(self, context):
        self.handles = {'TRANSLATE': [], 'ROTATE': [], 'SCALE': []}

        # White center circle, shown only in the combined layout.
        gz = self.gizmos.new("GIZMO_GT_dial_3d")
        gz.scale_basis = self.CENTER_SCALE
        props = gz.target_set_operator("transform.translate")
        props.release_confirm = True
        self.center = gz
        gz.color = (0.85, 0.85, 0.85)
        gz.alpha = 0.7
        gz.color_highlight = (1.0, 1.0, 1.0)
        gz.alpha_highlight = 1.0
        gz.line_width = 2.0
        gz.use_draw_modal = True

        for i, (color, _rot) in enumerate(AXES):
            axis = tuple(j == i for j in range(3))

            gz = self.gizmos.new("GIZMO_GT_arrow_3d")
            props = gz.target_set_operator("transform.translate")
            props.constraint_axis = axis
            props.orient_type = 'GLOBAL'
            props.release_confirm = True
            self.handles['TRANSLATE'].append(gz)

            gz = self.gizmos.new("GIZMO_GT_dial_3d")
            gz.draw_options = {'CLIP'}
            props = gz.target_set_operator("transform.rotate")
            props.orient_axis = 'XYZ'[i]
            props.orient_type = 'GLOBAL'
            props.release_confirm = True
            self.handles['ROTATE'].append(gz)

            gz = self.gizmos.new("GIZMO_GT_arrow_3d")
            gz.draw_style = 'BOX'
            props = gz.target_set_operator("transform.resize")
            props.constraint_axis = axis
            props.release_confirm = True
            self.handles['SCALE'].append(gz)

            for mode in self.handles:
                gz = self.handles[mode][i]
                gz.color = color
                gz.alpha = 0.9
                gz.color_highlight = (1.0, 1.0, 0.5)
                gz.alpha_highlight = 1.0
                gz.line_width = 2.0
                gz.use_draw_modal = True

    def draw_prepare(self, context):
        # Don't restyle mid-drag; keep the manipulator as it was grabbed.
        if any(gz.is_modal for gz in self.gizmos):
            return
        modes = active_tool_modes(context)
        pivot = gizmo_pivot(context)
        if modes is None or pivot is None:
            return
        rv3d = context.region_data
        pos, clamped = manipulator_position(context.region, rv3d, pivot)
        place = Matrix.Translation(pos)
        combined = modes == {'TRANSLATE', 'ROTATE', 'SCALE'}
        for mode, group in self.handles.items():
            shown = clamped and mode in modes
            for gz, (_color, rot) in zip(group, AXES):
                gz.hide = not shown
                gz.matrix_basis = place @ rot
                if mode == 'TRANSLATE':
                    # Combined layout: stemless cones pushed past the ring.
                    gz.draw_options = set() if combined else {'STEM'}
                    gz.length = self.COMBINED_ARROW_LENGTH if combined else 1.0
                elif mode == 'SCALE':
                    gz.length = self.COMBINED_SCALE_LENGTH if combined else 1.0
        self.center.hide = not (clamped and combined)
        self.center.matrix_basis = place @ rv3d.view_rotation.to_matrix().to_4x4()


# --- Dashed leader line from the pinned manipulator back to the pivot -------

draw_handle = None


def draw_leader_line():
    context = bpy.context
    region = context.region
    rv3d = context.region_data
    if region is None or rv3d is None:
        return
    if active_tool_modes(context) is None:
        return
    pivot = gizmo_pivot(context)
    if pivot is None:
        return
    pos, clamped = manipulator_position(region, rv3d, pivot)
    if not clamped:
        return
    a = location_3d_to_region_2d(region, rv3d, pos)
    b = location_3d_to_region_2d(region, rv3d, pivot)
    if a is None or b is None:
        return
    span = b - a
    length = span.length
    if length < 1.0:
        return
    direction = span / length
    coords = []
    dash, gap = 7.0, 5.0
    t = 0.0
    while t < length:
        coords.append(a + direction * t)
        coords.append(a + direction * min(t + dash, length))
        t += dash + gap
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'LINES', {"pos": coords})
    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(1.5)
    shader.uniform_float("color", (1.0, 1.0, 1.0, 0.8))
    batch.draw(shader)
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')


# --- Registration ------------------------------------------------------------

def register():
    bpy.utils.register_class(GIZMOPLUS_GGT_manipulator)
    global draw_handle
    draw_handle = bpy.types.SpaceView3D.draw_handler_add(
        draw_leader_line, (), 'WINDOW', 'POST_PIXEL'
    )


def unregister():
    global draw_handle
    if draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(draw_handle, 'WINDOW')
        draw_handle = None
    bpy.utils.unregister_class(GIZMOPLUS_GGT_manipulator)


if __name__ == "__main__":
    register()
