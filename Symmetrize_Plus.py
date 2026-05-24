bl_info = {
    "name": "Symmetrize Plus",
    "author": "WXP",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "Edit Mesh / Weight Paint: Alt+X",
    "description": "Flick gizmo to pick symmetrize axis",
    "category": "Mesh",
}

import bpy
import gpu
from bpy.props import BoolProperty, EnumProperty, IntProperty, PointerProperty, StringProperty
from bpy_extras.view3d_utils import (
    location_3d_to_region_2d,
    region_2d_to_location_3d,
    region_2d_to_origin_3d,
    region_2d_to_vector_3d,
)
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

addon_keymaps = []

SUPPORTED_MODES = {'EDIT_MESH', 'PAINT_WEIGHT'}
KEYMAP_NAMES = ('Mesh', 'Weight Paint')

AXIS_ITEMS = [
    ('X', "X", ""),
    ('Y', "Y", ""),
    ('Z', "Z", ""),
]

DIRECTION_ITEMS = [
    ('POSITIVE', "+", ""),
    ('NEGATIVE', "-", ""),
]

RED = (1, 0.25, 0.25)
GREEN = (0.25, 1, 0.25)
BLUE = (0.35, 0.55, 1)
WHITE = (1, 1, 1)

UNIFORM_SHADER = 'POINT_UNIFORM_COLOR' if bpy.app.version >= (4, 5, 0) else 'UNIFORM_COLOR'
FLICK_DISTANCE_DEFAULT = 75


# --- minimal GPU draw (screen + view) -----------------------------------------

def _draw_line_2d(p0, p1, color, width=1, alpha=1.0):
    gpu.state.depth_test_set('NONE')
    gpu.state.blend_set('ALPHA')
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    shader.bind()
    shader.uniform_float("color", (*color, alpha))
    shader.uniform_float("lineWidth", width)
    shader.uniform_float("viewportSize", gpu.state.scissor_get()[2:])
    batch = batch_for_shader(shader, 'LINES', {"pos": [p0, p1]})
    batch.draw(shader)


def _draw_circle_2d(center, radius, color, width=2, alpha=0.05):
    import math
    segments = max(int(radius), 16)
    coords = []
    for i in range(segments):
        t = 2 * math.pi * i / segments
        coords.append(Vector((center.x + radius * math.cos(t), center.y + radius * math.sin(t), 0)))
    indices = [(i, i + 1) if i < segments - 1 else (i, 0) for i in range(segments)]
    gpu.state.depth_test_set('NONE')
    gpu.state.blend_set('ALPHA')
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    shader.bind()
    shader.uniform_float("color", (*color, alpha))
    shader.uniform_float("lineWidth", width)
    shader.uniform_float("viewportSize", gpu.state.scissor_get()[2:])
    batch = batch_for_shader(shader, 'LINES', {"pos": coords}, indices=indices)
    batch.draw(shader)


def _draw_label_2d(context, text, coords, size=12, color=WHITE, alpha=1.0, center=True):
    import blf
    scale = context.preferences.system.ui_scale
    font_id = 1
    blf.size(font_id, int(size * scale))
    blf.color(font_id, *color, alpha)
    x, y = coords[0], coords[1]
    if center:
        dims = blf.dimensions(font_id, text)
        x -= dims[0] / 2
    blf.position(font_id, x, y, 0)
    blf.draw(font_id, text)


def _draw_point_3d(co, color=WHITE, size=5, alpha=0.8):
    gpu.state.depth_test_set('NONE')
    gpu.state.blend_set('ALPHA')
    gpu.state.point_size_set(size)
    shader = gpu.shader.from_builtin(UNIFORM_SHADER)
    shader.bind()
    shader.uniform_float("color", (*color, alpha))
    batch = batch_for_shader(shader, 'POINTS', {"pos": [co]})
    batch.draw(shader)


def _draw_vector_3d(vector, origin, color=WHITE, width=1, alpha=1.0):
    coords = [origin, origin + vector]
    colors = [(*color, alpha), (*color, alpha)]
    gpu.state.depth_test_set('NONE')
    gpu.state.blend_set('ALPHA')
    shader = gpu.shader.from_builtin('POLYLINE_SMOOTH_COLOR')
    shader.bind()
    shader.uniform_float("lineWidth", width)
    shader.uniform_float("viewportSize", gpu.state.scissor_get()[2:])
    batch = batch_for_shader(shader, 'LINES', {"pos": coords, "color": colors})
    batch.draw(shader)


def _ui_scale(context):
    return context.preferences.system.ui_scale


def _zoom_factor(context, depth_location, scale=10):
    center = Vector((context.region.width / 2, context.region.height / 2))
    offset = center + Vector((scale, 0))
    center_3d = region_2d_to_location_3d(context.region, context.region_data, center, depth_location)
    offset_3d = region_2d_to_location_3d(context.region, context.region_data, offset, depth_location)
    return (center_3d - offset_3d).length


def _navigation_passthrough(event):
    return (
        event.type in {'MIDDLEMOUSE'}
        or event.type.startswith('NDOF')
        or (event.alt and event.type in {'LEFTMOUSE', 'RIGHTMOUSE'} and event.value == 'PRESS')
    )


def _get_flick_direction(op, context, locked_axes):
    def influence(axis_data):
        return axis_data['dot'] * 2 + axis_data['weight']

    origin_2d = location_3d_to_region_2d(
        context.region,
        context.region_data,
        op.init_mouse_3d,
        default=Vector((context.region.width / 2, context.region.height / 2)),
    )
    axes_2d = {}

    for direction, axis in op.axes.items():
        _, axis_name = direction.split('_')
        if axis_name not in locked_axes:
            continue
        axis_2d = location_3d_to_region_2d(
            context.region,
            context.region_data,
            op.init_mouse_3d + axis,
            default=origin_2d,
        )
        delta = axis_2d - origin_2d
        if not delta.length:
            continue
        axes_2d[direction] = {'axis': delta.normalized(), 'dot': 0.0, 'length': delta.length, 'weight': 1.0}

    if not axes_2d:
        return None

    max_length = max(d['length'] for d in axes_2d.values())
    flick_dir = op.flick_vector.xy.normalized()

    for data in axes_2d.values():
        data['weight'] = data['length'] / max_length
        data['dot'] = data['axis'].dot(flick_dir)

    best = max(axes_2d.items(), key=lambda item: influence(item[1]))
    return best[0]


# --- per-object axis locks (optional, like MESHmachine) -----------------------

class SymmetrizePlusProps(bpy.types.PropertyGroup):
    # True = axis is allowed for flick (same as MESHmachine axis locks)
    lock_x: BoolProperty(name="Allow X", default=True)
    lock_y: BoolProperty(name="Allow Y", default=True)
    lock_z: BoolProperty(name="Allow Z", default=True)


def _locked_axes(obj):
    sp = obj.symmetrize_plus
    axes = []
    if sp.lock_x:
        axes.append('X')
    if sp.lock_y:
        axes.append('Y')
    if sp.lock_z:
        axes.append('Z')
    return axes


def _ensure_default_lock(obj):
    sp = obj.symmetrize_plus
    if not any((sp.lock_x, sp.lock_y, sp.lock_z)):
        sp.lock_x = sp.lock_y = sp.lock_z = True


def _poll(context):
    obj = context.active_object
    return obj and obj.type == 'MESH' and context.mode in SUPPORTED_MODES


# --- flick gizmo operator -----------------------------------------------------

class MESH_OT_symmetrize_plus_flick(bpy.types.Operator):
    """Drag from center to pick symmetrize axis; release past ring or confirm with LMB"""
    bl_idname = "mesh.symmetrize_plus_flick"
    bl_label = "Symmetrize Plus Flick"
    bl_options = {'REGISTER', 'UNDO'}

    flick_distance: IntProperty(name="Flick Distance", default=FLICK_DISTANCE_DEFAULT, min=20, max=1000)

    axis: EnumProperty(items=AXIS_ITEMS, default='X')
    direction: EnumProperty(items=DIRECTION_ITEMS, default='POSITIVE')
    flick_direction: StringProperty(name="Flick Direction", default="")
    use_topology: BoolProperty(name="Topology Mirror", default=False, description="Use topology-based mirroring instead of position-based (for meshes that are not perfectly symmetrical)")

    @classmethod
    def poll(cls, context):
        return _poll(context)

    def invoke(self, context, event):
        self.active = context.active_object
        mx = self.active.matrix_world

        self.flick_distance_px = self.flick_distance * _ui_scale(context)
        self.mousepos = Vector((event.mouse_region_x, event.mouse_region_y, 0))

        view_origin = region_2d_to_origin_3d(context.region, context.region_data, self.mousepos)
        view_dir = region_2d_to_vector_3d(context.region, context.region_data, self.mousepos)
        self.origin = view_origin + view_dir * 10

        self.is_ctrl = False
        self.is_shift = False
        self.zoom = _zoom_factor(context, self.origin, scale=self.flick_distance_px)

        self.init_mouse = self.mousepos.copy()
        self.init_mouse_3d = region_2d_to_location_3d(
            context.region, context.region_data, self.init_mouse, self.origin
        )

        self.flick_vector = Vector((0, 0, 0))
        self.flick_direction = ""

        quat = mx.to_quaternion()
        self.axes = {
            'POSITIVE_X': quat @ Vector((1, 0, 0)),
            'NEGATIVE_X': quat @ Vector((-1, 0, 0)),
            'POSITIVE_Y': quat @ Vector((0, 1, 0)),
            'NEGATIVE_Y': quat @ Vector((0, -1, 0)),
            'POSITIVE_Z': quat @ Vector((0, 0, 1)),
            'NEGATIVE_Z': quat @ Vector((0, 0, -1)),
        }
        self.axis_colors = [RED, RED, GREEN, GREEN, BLUE, BLUE]

        _ensure_default_lock(self.active)
        self.init_locked_axes = _locked_axes(self.active)

        self.area = context.area
        self._handlers = []
        self._handlers.append(bpy.types.SpaceView3D.draw_handler_add(self.draw_HUD, (context,), 'WINDOW', 'POST_PIXEL'))
        self._handlers.append(bpy.types.SpaceView3D.draw_handler_add(self.draw_VIEW3D, (context,), 'WINDOW', 'POST_VIEW'))

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def draw_HUD(self, context):
        if context.area != self.area:
            return

        p0 = self.init_mouse
        p1 = p0 + self.flick_vector
        _draw_line_2d(p0, p1, WHITE, width=1, alpha=0.99)
        _draw_circle_2d(p0, self.flick_distance_px, WHITE, width=3, alpha=0.04)

        top_y = p0.y + self.flick_distance_px - 4 * _ui_scale(context)
        bottom_y = p0.y - self.flick_distance_px + 15 * _ui_scale(context)

        axes = _locked_axes(self.active)
        _draw_label_2d(context, " ".join(axes) if axes else "None", (p0.x, top_y), size=10, alpha=0.5 if axes else 1.0)

        title = self.flick_direction.replace('_', ' ').title() if self.flick_direction else "Drag axis"
        _draw_label_2d(context, title, (p0.x, bottom_y), size=12, alpha=0.5)

    def draw_VIEW3D(self, context):
        if context.area != self.area:
            return

        axes = _locked_axes(self.active)
        if not axes:
            return

        for direction, axis_vec, color in zip(self.axes.keys(), self.axes.values(), self.axis_colors):
            dir_name, axis_name = direction.split('_')
            if axis_name not in axes:
                continue
            is_positive = dir_name == 'POSITIVE'
            _draw_vector_3d(
                axis_vec * self.zoom / 2,
                self.init_mouse_3d,
                color=color,
                width=2 if is_positive else 1,
                alpha=0.99 if is_positive else 0.3,
            )

        if self.flick_direction:
            tip = self.init_mouse_3d + self.axes[self.flick_direction] * self.zoom / 2 * 1.2
            _draw_point_3d(tip, color=WHITE, size=5, alpha=0.8)

    def modal(self, context, event):
        context.area.tag_redraw()
        self.mousepos = Vector((event.mouse_region_x, event.mouse_region_y, 0))
        self.is_ctrl = event.ctrl
        self.is_shift = event.shift

        sp = self.active.symmetrize_plus
        if not self.is_ctrl and not self.is_shift and not any((sp.lock_x, sp.lock_y, sp.lock_z)):
            sp.lock_x = sp.lock_y = sp.lock_z = True

        can_finish = bool(_locked_axes(self.active))

        if event.type in {'MOUSEMOVE', 'X', 'Y', 'Z'}:
            self._update_flick(context)

            if can_finish and self.flick_vector.length > self.flick_distance_px:
                self._apply_flick_direction()
                self._finish_handlers()
                return self.execute(context)

            if (self.is_shift or self.is_ctrl) and event.type in {'X', 'Y', 'Z'} and event.value == 'PRESS':
                axis = event.type
                if self.is_ctrl:
                    sp.lock_x = axis == 'X'
                    sp.lock_y = axis == 'Y'
                    sp.lock_z = axis == 'Z'
                else:
                    setattr(sp, f'lock_{axis.lower()}', not getattr(sp, f'lock_{axis.lower()}'))
                self._update_flick(context)

        elif _navigation_passthrough(event):
            return {'PASS_THROUGH'}

        elif can_finish and event.type in {'LEFTMOUSE', 'SPACE'} and event.value == 'PRESS':
            self._finish_handlers()
            if self.flick_direction:
                self._apply_flick_direction()
                return self.execute(context)
            return {'CANCELLED'}

        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self._restore_axis_locks()
            self._finish_handlers()
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def _update_flick(self, context):
        self.flick_vector = self.mousepos - self.init_mouse
        if not self.flick_vector.length:
            self.flick_direction = ""
            return
        locked = _locked_axes(self.active)
        direction = _get_flick_direction(self, context, locked)
        if direction:
            self.flick_direction = direction
            self._apply_flick_direction()

    def _apply_flick_direction(self):
        direction, axis = self.flick_direction.split('_')
        self.axis = axis
        self.direction = 'POSITIVE' if direction == 'NEGATIVE' else 'NEGATIVE'

    def _restore_axis_locks(self):
        sp = self.active.symmetrize_plus
        sp.lock_x = 'X' in self.init_locked_axes
        sp.lock_y = 'Y' in self.init_locked_axes
        sp.lock_z = 'Z' in self.init_locked_axes

    def _finish_handlers(self):
        for handler in self._handlers:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(handler, 'WINDOW')
            except ValueError:
                pass
        self._handlers.clear()

    def execute(self, context):
        if context.mode == 'EDIT_MESH':
            bpy.ops.mesh.symmetrize(direction=f'{self.direction}_{self.axis}')
            return {'FINISHED'}

        # --- weight paint ---
        if self.axis != 'X':
            self.report({'WARNING'}, "Weight mirror only supports the X axis")
            return {'CANCELLED'}

        obj = context.active_object
        mesh = obj.data

        if not obj.vertex_groups or obj.vertex_groups.active_index < 0:
            self.report({'WARNING'}, "No active vertex group")
            return {'CANCELLED'}

        import bmesh

        # Drag toward = destination side receives weights (opposite side is source).
        # mesh.symmetrize uses inverted direction (names the kept/source side), but
        # vertex_group_mirror with a vertex selection writes TO the selected verts only.
        # So here we select the flick destination, not self.direction.
        # https://blenderartists.org/t/is-there-no-one-way-solution-to-mirror-the-vertex-weights-of-a-bunch-of-selected-vertices/1274846
        flick_dir, _ = self.flick_direction.split('_')
        sign = 1.0 if flick_dir == 'POSITIVE' else -1.0

        orig_mask = mesh.use_paint_mask_vertex

        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(mesh)
        bm.select_mode = {'VERT'}

        for v in bm.verts:
            v.select = (v.co.x * sign) > 1e-5

        bm.select_flush_mode()
        bmesh.update_edit_mesh(mesh)

        bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
        mesh.use_paint_mask_vertex = True

        bpy.ops.object.vertex_group_mirror(
            mirror_weights=True,
            flip_group_names=False,
            all_groups=False,
            use_topology=self.use_topology,
        )

        mesh.use_paint_mask_vertex = orig_mask
        return {'FINISHED'}


classes = (
    SymmetrizePlusProps,
    MESH_OT_symmetrize_plus_flick,
)


def register_keymaps():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return
    for name in KEYMAP_NAMES:
        km = kc.keymaps.new(name=name, space_type='EMPTY')
        kmi = km.keymap_items.new(
            MESH_OT_symmetrize_plus_flick.bl_idname,
            type='X',
            value='PRESS',
            alt=True,
        )
        addon_keymaps.append((km, kmi))


def unregister_keymaps():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.symmetrize_plus = PointerProperty(type=SymmetrizePlusProps)
    register_keymaps()


def unregister():
    unregister_keymaps()
    del bpy.types.Object.symmetrize_plus
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
