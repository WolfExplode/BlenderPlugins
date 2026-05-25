bl_info = {
    "name": "Symmetrize Plus",
    "author": "WXP",
    "version": (0, 1, 4),
    "blender": (4, 0, 0),
    "location": "Edit Mesh / Weight Paint: Alt+X",
    "description": "MESHmachine-style symmetrize with flick gizmo (mesh + weight paint)",
    "category": "Mesh",
}

import time

import bpy
import bmesh
import blf
import gpu
import mathutils
from bl_ui.space_statusbar import STATUSBAR_HT_header as statusbar
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    IntVectorProperty,
    PointerProperty,
    StringProperty,
)
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

CUSTOM_NORMAL_METHOD_ITEMS = [
    ('INDEX', "Index", ""),
    ('LOCATION', "Location", ""),
]

FIX_CENTER_METHOD_ITEMS = [
    ('CLEAR', "Clear Normals", ""),
    ('TRANSFER', "Transfer Normals", ""),
]

AXIS_MAPPING = {
    "X": Vector((1, 0, 0)),
    "Y": Vector((0, 1, 0)),
    "Z": Vector((0, 0, 1)),
}

RED = (1, 0.25, 0.25)
GREEN = (0.25, 1, 0.25)
BLUE = (0.2, 0.6, 1)
WHITE = (1, 1, 1)
YELLOW = (1, 0.9, 0.2)
NORMAL_COLOR = (0.5, 0.5, 1)

UNIFORM_SHADER = 'POINT_UNIFORM_COLOR' if bpy.app.version >= (4, 5, 0) else 'UNIFORM_COLOR'
FLICK_DISTANCE_DEFAULT = 75

# flash draw state (set by symmetrize, read by draw operator)
_flash_draw = {'indices': [], 'custom_normals': False, 'remove': False}


def _addon_prefs():
    return bpy.context.preferences.addons.get(__name__)


def _pref(name, default):
    prefs = _addon_prefs()
    if prefs:
        return getattr(prefs.preferences, name, default)
    return default


def _hud_scale(context):
    return context.preferences.system.ui_scale * _pref('modal_hud_scale', 1.0)


# --- status bar (MESHmachine) -------------------------------------------------

def _icon_from_key(key):
    if key in ['LMB', 'MMB', 'RMB', 'LMB_DRAG', 'LMB_2X', 'MMB_DRAG', 'MMB_SCROLL', 'RMB_DRAG', 'MOVE']:
        if bpy.app.version < (4, 3, 0) and key == 'MMB_SCROLL':
            key = 'MMB'
        return f"MOUSE_{key}"
    if key in ['SPACE']:
        return f"EVENT_{key}KEY"
    return f"EVENT_{key}"


def _draw_key_icons(layout, key):
    keys = [key] if isinstance(key, str) else key
    for icon in keys:
        layout.label(text='', icon=icon)
        if bpy.app.version >= (4, 3, 0):
            if icon in ['KEY_EMPTY2', 'EVENT_CTRL', 'EVENT_ALT', 'EVENT_OS', 'EVENT_F10', 'EVENT_F11', 'EVENT_F12', 'EVENT_ESC', 'EVENT_PAUSE', 'EVENT_INSERT', 'EVENT_HOME', 'EVENT_END', 'EVENT_APP', 'EVENT_BACKSPACE', 'EVENT_DEL']:
                layout.separator(factor=1.5)
            elif icon in ['KEY_EMPTY3', 'EVENT_SPACEKEY']:
                layout.separator(factor=3)


def _draw_status_item(layout, active=True, alert=False, key=None, text="", gap=None):
    row = layout.row(align=True)
    row.active = active
    row.alert = alert
    keys = [key] if isinstance(key, str) else (key or [])
    if gap:
        row.separator(factor=gap)
    _draw_key_icons(row, [_icon_from_key(k) for k in keys])
    if text:
        row.label(text=text)


def _init_status(op, func):
    op._bar_orig = statusbar.draw
    statusbar.draw = func


def _finish_status(op):
    if getattr(op, '_bar_orig', None):
        statusbar.draw = op._bar_orig


def _force_ui_update(context):
    if context.mode == 'OBJECT':
        if active := context.active_object:
            active.select_set(True)
        elif visible := context.visible_objects:
            visible[0].select_set(visible[0].select_get())
    elif context.mode in {'EDIT_MESH', 'PAINT_WEIGHT'}:
        if context.active_object:
            context.active_object.select_set(True)
    for area in context.window.screen.areas:
        area.tag_redraw()


def _draw_symmetrize_status(op):
    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.label(text='Symmetrize')

        _draw_status_item(row, key='MOVE', text='Pick Axis')
        _draw_status_item(row, key='LMB', text='Finish')
        _draw_status_item(row, key='RMB', text='Cancel')

        if op.weight_paint:
            _draw_status_item(row, active=op.use_topology, key='T', text='Topology', gap=10)
            if op.has_vertex_groups:
                _draw_status_item(row, active=op.mirror_vertex_groups, key='V', text='Mirror Vertex Groups', gap=2)
                _draw_status_item(row, active=op.mirror_paired_bones, key='B', text='Mirror to Paired Bone', gap=2)
            sp = op.active.symmetrize_plus
            _draw_status_item(row, key=['CTRL', 'SHIFT'], text='Axis Locks', gap=4)
            _draw_status_item(row, active=sp.lock_x, key='X', text='', gap=1)
            _draw_status_item(row, active=sp.lock_y, key='Y', text='', gap=1)
            _draw_status_item(row, active=sp.lock_z, key='Z', text='', gap=1)
            return

        _draw_status_item(row, active=op.partial, key='S', text='Selected only', gap=10)
        _draw_status_item(row, active=op.remove and not (op.is_shift or op.is_ctrl), key='X', text='Remove', gap=2)

        if not op.remove:
            row.separator(factor=2)
            if op.has_uvs:
                _draw_status_item(row, active=op.offset_uvs, key='D', text='Offset UVs', gap=2)

            is_normal_mirror = not op.partial and op.has_custom_normals and op.mirror_custom_normals

            if not is_normal_mirror:
                _draw_status_item(row, active=op.remove_redundant_center, key='R', text='Remove Redundant Center', gap=2)
                if op.has_vertex_groups:
                    _draw_status_item(row, active=op.mirror_vertex_groups, key='V', text='Mirror Vertex Groups', gap=2)

            if op.has_custom_normals:
                _draw_status_item(row, active=op.mirror_custom_normals, key='N', text='Mirror Custom Normals', gap=2)

        is_exclusive = op.is_ctrl
        key = [] if op.is_ctrl or op.is_shift else ['CTRL', 'SHIFT']
        lock_mode = 'Exclusive ' if is_exclusive else 'Individual ' if op.is_ctrl or op.is_shift else ''
        _draw_status_item(row, key=key, text=f"{lock_mode}Axis Locks", gap=4)

        sp = op.active.symmetrize_plus
        _draw_status_item(row, active=sp.lock_x, key='X', text='', gap=1)
        _draw_status_item(row, active=sp.lock_y, key='Y', text='', gap=1)
        _draw_status_item(row, active=sp.lock_z, key='Z', text='', gap=1)

    return draw


# --- minimal GPU draw ---------------------------------------------------------

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


def _text_dimensions(context, text='', size=12):
    font_id = 1
    blf.size(font_id, int(size * _hud_scale(context)))
    return Vector(blf.dimensions(font_id, text))


def _draw_label(context, title='', coords=None, size=12, color=WHITE, alpha=1.0, center=True):
    if coords is None:
        region = context.region
        width = region.width / 2
        height = region.height / 2
    else:
        width, height = coords[0], coords[1]

    scale = _hud_scale(context)
    font_id = 1
    blf.size(font_id, int(size * scale))
    blf.color(font_id, *color, alpha)

    if center:
        dims = blf.dimensions(font_id, title)
        blf.position(font_id, width - (dims[0] / 2), height, 0)
    else:
        blf.position(font_id, width, height, 0)

    blf.draw(font_id, title)
    return Vector(blf.dimensions(font_id, title))


def _draw_point_3d(co, color=WHITE, size=5, alpha=0.8):
    gpu.state.depth_test_set('NONE')
    gpu.state.blend_set('ALPHA')
    gpu.state.point_size_set(size)
    shader = gpu.shader.from_builtin(UNIFORM_SHADER)
    shader.bind()
    shader.uniform_float("color", (*color, alpha))
    batch = batch_for_shader(shader, 'POINTS', {"pos": [co]})
    batch.draw(shader)


def _draw_points_3d(coords, color=WHITE, size=6, alpha=0.3):
    if not coords:
        return
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.blend_set('ALPHA')
    gpu.state.point_size_set(size)
    shader = gpu.shader.from_builtin(UNIFORM_SHADER)
    shader.bind()
    shader.uniform_float("color", (*color, alpha))
    batch = batch_for_shader(shader, 'POINTS', {"pos": coords})
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


def _zoom_factor(context, depth_location, scale=10, ignore_obj_scale=False):
    center = Vector((context.region.width / 2, context.region.height / 2))
    offset = center + Vector((scale, 0))
    center_3d = region_2d_to_location_3d(context.region, context.region_data, center, depth_location)
    offset_3d = region_2d_to_location_3d(context.region, context.region_data, offset, depth_location)
    zoom_factor = (center_3d - offset_3d).length
    if context.active_object and not ignore_obj_scale:
        mx = context.active_object.matrix_world.to_3x3()
        zoom_vector = mx.inverted_safe() @ Vector((zoom_factor, 0, 0))
        zoom_factor = zoom_vector.length
    return zoom_factor


def _is_hyper_bevel(obj):
    return getattr(obj, 'HC', False) and getattr(obj.HC, 'ishyperbevel', False)


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

    return max(axes_2d.items(), key=lambda item: influence(item[1]))[0]


def _negate_string(floatstring):
    if floatstring.startswith("-"):
        return floatstring[1:]
    return "-" + floatstring


def _loop_index_update(bm):
    lidx = 0
    for face in bm.faces:
        for loop in face.loops:
            loop.index = lidx
            lidx += 1


def _paired_vertex_group_name(name):
    """Return the L/R counterpart name (Blender-style .L/.R suffix)."""
    for left, right in (
        ('.L', '.R'), ('.R', '.L'),
        ('_L', '_R'), ('_R', '_L'),
        ('.l', '.r'), ('.r', '.l'),
        ('_l', '_r'), ('_r', '_l'),
    ):
        if name.endswith(left):
            return name[:-len(left)] + right
    return None


def _deform_clear_vgroup(bm, dvert, vg_index):
    for v in bm.verts:
        weights = v[dvert]
        if vg_index in weights:
            del weights[vg_index]


def _deform_remove_vgroup_selected(bm, dvert, vg_index):
    for v in bm.verts:
        if not v.select:
            continue
        weights = v[dvert]
        if vg_index in weights:
            del weights[vg_index]


def _add_vgroup(obj, name, vert_ids, weight=1.0):
    vgroup = obj.vertex_groups.new(name=name)
    if vert_ids:
        vgroup.add(vert_ids, weight, 'ADD')
    return vgroup


def _add_normal_transfer_mod(obj, source, vgroup_name):
    mod = obj.modifiers.new("SymmetrizePlusNormalXfer", 'DATA_TRANSFER')
    mod.object = source
    mod.use_loop_data = True
    mod.loop_mapping = 'POLYINTERP_NEAREST'
    mod.vertex_group = vgroup_name
    mod.data_types_loops = {'CUSTOM_NORMAL'}
    mod.show_expanded = False
    mod.show_in_editmode = True
    mod.use_object_transform = False
    if bpy.app.version < (4, 1, 0):
        obj.data.use_auto_smooth = True
    return mod


def _normal_clear(obj, limit=False):
    bpy.ops.object.mode_set(mode='OBJECT')
    mesh = obj.data

    if bpy.app.version < (4, 1, 0):
        mesh.calc_normals_split()

    loop_normals = [loop.normal.copy() for loop in mesh.loops]

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    verts = [v for v in bm.verts if v.select]
    faces = [f for f in bm.faces if f.select]

    for v in verts:
        for loop in v.link_loops:
            if not limit or loop.face in faces:
                loop_normals[loop.index] = mathutils.Vector()

    mesh.normals_split_custom_set(loop_normals)

    if bpy.app.version < (4, 1, 0):
        mesh.use_auto_smooth = True

    bpy.ops.object.mode_set(mode='EDIT')


def _normal_transfer_from_obj(active, source, vert_ids, clear_sharps=True):
    bpy.ops.object.mode_set(mode='OBJECT')
    vgroup = _add_vgroup(active, "SymmetrizePlusNormalXfer", vert_ids)
    mod = _add_normal_transfer_mod(active, source, vgroup.name)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    if vg := active.vertex_groups.get(vgroup.name):
        active.vertex_groups.remove(vg)
    bpy.ops.object.mode_set(mode='EDIT')

    mode = tuple(bpy.context.scene.tool_settings.mesh_select_mode)
    if mode != (True, False, False):
        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type='VERT')

    bpy.ops.mesh.loop_multi_select(ring=False)

    if clear_sharps:
        bpy.ops.mesh.mark_sharp(clear=True)

    bpy.ops.mesh.select_all(action='DESELECT')

    if mode != (True, False, False):
        bpy.context.scene.tool_settings.mesh_select_mode = mode


# --- MESHmachine symmetrize core (ported) -------------------------------------

def symmetrize_mesh(obj, data, debug=False):
    direction = data['direction']
    threshold = data['threshold']
    partial = data['partial']
    remove = data['remove']
    remove_redundant_center = data['remove_redundant_center']
    redundant_threshold = data['redundant_threshold']
    uv_offset = data['uv_offset']
    mirror_vertex_groups = data['mirror_vertex_groups']
    mirror_custom_normals = data['mirror_custom_normals']
    custom_normal_method = data['custom_normal_method']
    fix_center = data['fix_center']
    fix_center_method = data['fix_center_method']
    clear_sharps = data['clear_sharps']

    symdir, axis = direction.split('_')

    def offset_mirrored_uvs(bm, sides, offset):
        mirrored_vert_indices = sides[1]
        mirrored_faces = {f for v in bm.verts if v.index in mirrored_vert_indices for f in v.link_faces}
        if mirrored_faces:
            layers = bm.loops.layers.uv
            for face in mirrored_faces:
                for loop in face.loops:
                    for layer in layers:
                        loop[layer].uv += offset

    def sort_verts_into_sides():
        original = []
        mirror = []
        center = []
        verts = [v for v in bm.verts if v.select] if partial else bm.verts

        for v in verts:
            if axis == "X":
                if -threshold < v.co[0] < threshold:
                    v.co[0] = 0
                if symdir == "POSITIVE":
                    if v.co[0] == 0:
                        center.append(v.index)
                    elif v.co[0] > 0:
                        original.append(v.index)
                    else:
                        mirror.append(v.index)
                elif symdir == "NEGATIVE":
                    if v.co[0] == 0:
                        center.append(v.index)
                    elif v.co[0] < 0:
                        original.append(v.index)
                    else:
                        mirror.append(v.index)

            if axis == "Y":
                if -threshold < v.co[1] < threshold:
                    v.co[1] = 0
                if symdir == "POSITIVE":
                    if v.co[1] == 0:
                        center.append(v.index)
                    elif v.co[1] > 0:
                        original.append(v.index)
                    else:
                        mirror.append(v.index)
                elif symdir == "NEGATIVE":
                    if v.co[1] == 0:
                        center.append(v.index)
                    elif v.co[1] < 0:
                        original.append(v.index)
                    else:
                        mirror.append(v.index)

            if axis == "Z":
                if -threshold < v.co[2] < threshold:
                    v.co[2] = 0
                if symdir == "POSITIVE":
                    if v.co[2] == 0:
                        center.append(v.index)
                    elif v.co[2] > 0:
                        original.append(v.index)
                    else:
                        mirror.append(v.index)
                elif symdir == "NEGATIVE":
                    if v.co[2] == 0:
                        center.append(v.index)
                    elif v.co[2] < 0:
                        original.append(v.index)
                    else:
                        mirror.append(v.index)

            v.select = False
        bm.select_flush(False)

        if len(original) != len(mirror):
            print("Symmetrize Plus: WARNING, uneven vertex list sizes!")

        return (original, mirror, center), axis

    def get_mirror_verts_via_index(original, mirror, center):
        mirror_verts = {}
        for vm, vp in zip(mirror, original):
            mirror_verts[vp] = vm
        for vz in center:
            mirror_verts[vz] = vz
        return mirror_verts

    def get_mirror_verts_via_location(original, mirror, center, axis_name):
        precision = 10
        lookup = {}

        for v in bm.verts:
            x = "%.*f" % (precision, v.co[0])
            y = "%.*f" % (precision, v.co[1])
            z = "%.*f" % (precision, v.co[2])

            if axis_name == "X":
                key = (y, z)
                lookup.setdefault(key, {})[x] = v.index
            elif axis_name == "Y":
                key = (x, z)
                lookup.setdefault(key, {})[y] = v.index
            else:
                key = (x, y)
                lookup.setdefault(key, {})[z] = v.index

        mirror_verts = {}
        for idx in original:
            vo = bm.verts[idx]
            x = "%.*f" % (precision, vo.co[0])
            y = "%.*f" % (precision, vo.co[1])
            z = "%.*f" % (precision, vo.co[2])

            if axis_name == "X":
                mirror_verts[idx] = lookup[(y, z)][_negate_string(x)]
            elif axis_name == "Y":
                mirror_verts[idx] = lookup[(x, z)][_negate_string(y)]
            else:
                mirror_verts[idx] = lookup[(x, y)][_negate_string(z)]

        for vc in center:
            mirror_verts[vc] = vc
        return mirror_verts

    def get_mirror_faces(mirror_verts):
        faces = {}
        loops = {}
        for face in bm.faces:
            vertlist = [v.index for v in face.verts]
            faces[frozenset(vertlist)] = face.index
            for loop in face.loops:
                loops[(face.index, loop.vert.index)] = loop.index

        mirror_faces = {}
        for vertlist in faces:
            try:
                mirrored_vertlist = frozenset(mirror_verts[idx] for idx in vertlist)
                mirror_faces[faces[vertlist]] = faces[mirrored_vertlist]
            except KeyError:
                pass
        return mirror_faces, loops

    def get_mirror_loops(mirror_verts, mirror_faces, loops):
        mirror_loops = {}
        for fidx in mirror_faces:
            for loop in bm.faces[fidx].loops:
                mirror_loops[loop.index] = loops[(mirror_faces[fidx], mirror_verts[loop.vert.index])]
        return mirror_loops

    def remove_vertex_groups(vg, sides):
        for idx in sides[1] + sides[2]:
            v = bm.verts[idx]
            for vg_idx in list(v[vg].keys()):
                del v[vg][vg_idx]

    def fix_center_seam(center):
        for v in obj.data.vertices:
            if v.index in center:
                v.select = True

        bpy.ops.object.mode_set(mode='EDIT')
        mode = tuple(bpy.context.scene.tool_settings.mesh_select_mode)
        if mode != (True, False, False):
            bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type='VERT')

        bpy.ops.mesh.loop_multi_select(ring=False)

        if clear_sharps:
            bpy.ops.mesh.mark_sharp(clear=True)

        if fix_center_method == "CLEAR":
            _normal_clear(obj, limit=False)
        elif fix_center_method == "TRANSFER":
            _normal_transfer_from_obj(obj, normal_source_obj, center, clear_sharps=clear_sharps)

        bpy.ops.mesh.select_all(action='DESELECT')
        if mode != (True, False, False):
            bpy.context.scene.tool_settings.mesh_select_mode = mode

    is_uv_offset = obj.data.uv_layers and (uv_offset.x or uv_offset.y)
    is_normal_mirror = not remove and not partial and mirror_custom_normals
    normal_source_obj = None

    if not remove and not partial and obj.data.has_custom_normals:
        if mirror_custom_normals and fix_center and fix_center_method == "TRANSFER":
            obj.update_from_editmode()
            normal_source_obj = obj.copy()
            normal_source_obj.data = obj.data.copy()

    if not partial:
        bpy.ops.mesh.reveal()
        bpy.ops.mesh.select_all(action='SELECT')

    bpy.ops.mesh.symmetrize(direction=direction, threshold=threshold)

    if not partial:
        bpy.ops.mesh.select_all(action='DESELECT')

    if is_normal_mirror:
        if bpy.app.version < (4, 1, 0) and not obj.data.use_auto_smooth:
            obj.data.use_auto_smooth = True

        bpy.ops.object.mode_set(mode='OBJECT')

        if bpy.app.version < (4, 1, 0):
            obj.data.calc_normals_split()

        loop_normals = [loop.normal.normalized() for loop in obj.data.loops]

        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        _loop_index_update(bm)

        sides, axis_name = sort_verts_into_sides()

        if is_uv_offset:
            offset_mirrored_uvs(bm, sides, uv_offset)
            bm.to_mesh(obj.data)

        if custom_normal_method == "INDEX":
            mirror_verts = get_mirror_verts_via_index(*sides)
        else:
            mirror_verts = get_mirror_verts_via_location(*sides, axis_name)

        mirror_faces, loop_map = get_mirror_faces(mirror_verts)
        mirror_loops = get_mirror_loops(mirror_verts, mirror_faces, loop_map)
        mirror_vector = AXIS_MAPPING[axis_name]

        for ml in mirror_loops:
            loop_normals[mirror_loops[ml]] = loop_normals[ml].reflect(mirror_vector)

        obj.data.normals_split_custom_set(loop_normals)

        if sides[2] and fix_center:
            fix_center_seam(sides[2])
        else:
            bpy.ops.object.mode_set(mode='EDIT')

        if normal_source_obj:
            bpy.data.objects.remove(normal_source_obj, do_unlink=True)

        return {
            'original': sides[0], 'mirror': sides[1], 'center': sides[2],
            'custom_normal': True,
        }

    bpy.ops.object.mode_set(mode='OBJECT')

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    _loop_index_update(bm)

    vg = bm.verts.layers.deform.verify()
    sides, _ = sort_verts_into_sides()

    if is_uv_offset:
        offset_mirrored_uvs(bm, sides, uv_offset)

    if not mirror_vertex_groups:
        remove_vertex_groups(vg, sides)

    if is_uv_offset or not mirror_vertex_groups:
        bm.to_mesh(obj.data)

    bpy.ops.object.mode_set(mode='EDIT')

    if remove or remove_redundant_center:
        bm = bmesh.from_edit_mesh(obj.data)
        bm.normal_update()
        bm.verts.ensure_lookup_table()

        if remove:
            verts = [bm.verts[idx] for idx in sides[1]]
            bmesh.ops.delete(bm, geom=verts, context='VERTS')
        elif remove_redundant_center:
            redundant = [
                e for e in bm.edges
                if e.is_manifold
                and all(v.index in sides[2] for v in e.verts)
                and round(e.calc_face_angle(), 5) <= redundant_threshold
            ]
            bmesh.ops.dissolve_edges(bm, edges=redundant, use_verts=True, use_face_split=False)
            sides = (sides[0], sides[1], [])

        bmesh.update_edit_mesh(obj.data)

    return {
        'original': sides[0], 'mirror': sides[1], 'center': sides[2],
        'custom_normal': False,
    }


# --- object props + flick operator --------------------------------------------

class SymmetrizePlusProps(bpy.types.PropertyGroup):
    lock_x: BoolProperty(name="Allow X", default=True)
    lock_y: BoolProperty(name="Allow Y", default=True)
    lock_z: BoolProperty(name="Allow Z", default=True)


class SymmetrizePlusPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    flick_distance: IntProperty(
        name="Flick Distance",
        default=FLICK_DISTANCE_DEFAULT,
        min=20,
        max=1000,
    )
    modal_hud_scale: FloatProperty(name="HUD Scale", default=1.0, min=0.5, max=10.0)
    modal_hud_timeout: FloatProperty(
        name="Timeout",
        description="Flash overlay duration factor (like MESHmachine)",
        default=1.0,
        min=0.5,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "flick_distance")
        layout.prop(self, "modal_hud_scale")
        layout.prop(self, "modal_hud_timeout")


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


class MESH_OT_symmetrize_plus_draw(bpy.types.Operator):
    bl_idname = "mesh.symmetrize_plus_draw"
    bl_label = "Draw Symmetrize Flash"
    bl_options = {'INTERNAL'}

    time: FloatProperty(default=1.0)
    alpha: FloatProperty(default=0.3, min=0.1, max=1.0)
    normal_offset = 0.002

    def invoke(self, context, event):
        return self.execute(context)

    def execute(self, context):
        obj = context.active_object
        mx = obj.matrix_world
        offset = sum(obj.dimensions) / 3 * self.normal_offset
        indices = _flash_draw['indices']
        mesh = obj.data

        coords = []
        for i in indices:
            co = mesh.vertices[i].co.copy()
            if offset:
                co += mesh.vertices[i].normal * offset
            coords.append(mx @ co)

        self.coords = coords
        self.remove = _flash_draw['remove']
        if self.remove:
            self.color = RED
        elif _flash_draw['custom_normals']:
            self.color = NORMAL_COLOR
        else:
            self.color = WHITE

        self._timer_start = time.time()
        self._timer_duration = self.time * _pref('modal_hud_timeout', 1.0)
        self.area = context.area

        self._handler = bpy.types.SpaceView3D.draw_handler_add(
            self.draw_VIEW3D, (context,), 'WINDOW', 'POST_VIEW'
        )
        self._timer = context.window_manager.event_timer_add(0.05, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def draw_VIEW3D(self, context):
        if context.area != self.area:
            return
        elapsed = time.time() - self._timer_start
        progress = max(0.0, 1.0 - elapsed / self._timer_duration)
        alpha = progress * self.alpha * (10.0 if self.remove else 1.0)
        _draw_points_3d(self.coords, self.color, alpha=alpha)

    def modal(self, context, event):
        if context.area:
            context.area.tag_redraw()
        else:
            self._finish()
            return {'FINISHED'}

        if time.time() - self._timer_start >= self._timer_duration:
            self._finish()
            return {'FINISHED'}

        return {'PASS_THROUGH'}

    def _finish(self):
        wm = bpy.context.window_manager
        if getattr(self, '_timer', None):
            wm.event_timer_remove(self._timer)
        if getattr(self, '_handler', None):
            bpy.types.SpaceView3D.draw_handler_remove(self._handler, 'WINDOW')


class MESH_OT_symmetrize_plus_flick(bpy.types.Operator):
    """MESHmachine-style symmetrize flick gizmo"""
    bl_idname = "mesh.symmetrize_plus_flick"
    bl_label = "Symmetrize Plus"
    bl_description = "Symmetrize a mesh incl. custom normals (MESHmachine-style)"
    bl_options = {'REGISTER', 'UNDO'}

    has_custom_normals: BoolProperty(default=False)
    has_vertex_groups: BoolProperty(default=False)
    has_uvs: BoolProperty(default=False)

    passthrough = None

    axis: EnumProperty(items=AXIS_ITEMS, default='X')
    direction: EnumProperty(items=DIRECTION_ITEMS, default='POSITIVE')
    flick_direction: StringProperty(default="")

    threshold: FloatProperty(default=0.0001)
    partial: BoolProperty(default=False)
    remove: BoolProperty(default=False)
    remove_redundant_center: BoolProperty(default=True)
    redundant_threshold: FloatProperty(default=0.05, min=0, max=1, step=0.1)

    mirror_custom_normals: BoolProperty(default=True)
    custom_normal_method: EnumProperty(items=CUSTOM_NORMAL_METHOD_ITEMS, default='INDEX')
    fix_center: BoolProperty(default=False)
    fix_center_method: EnumProperty(items=FIX_CENTER_METHOD_ITEMS, default='CLEAR')
    clear_sharps: BoolProperty(default=True)

    mirror_vertex_groups: BoolProperty(default=False)
    offset_uvs: BoolProperty(default=True)
    uv_offset: IntVectorProperty(default=(1, 0), size=2, min=-100, max=100)

    use_topology: BoolProperty(
        name="Topology Mirror",
        default=False,
        description="Topology-based mirror for weight paint vertex_group_mirror",
    )
    mirror_paired_bones: BoolProperty(
        name="Mirror to Paired Bone",
        default=False,
        description="Mirror weights from the active .L/.R vertex group into its paired group (e.g. Bone.L → Bone.R)",
    )

    @classmethod
    def poll(cls, context):
        return _poll(context)

    def draw(self, context):
        layout = self.layout
        column = layout.column(align=True)

        row = column.row(align=True)
        row.prop(self, "axis", expand=True)
        row.prop(self, "direction", expand=True)

        if context.mode == 'PAINT_WEIGHT':
            column.separator()
            column.prop(self, "use_topology", text="Topology Mirror", toggle=True)
            if self.has_vertex_groups:
                column.separator()
                column.prop(self, "mirror_vertex_groups", text="Mirror Vertex Groups", toggle=True)
                column.prop(self, "mirror_paired_bones", text="Mirror to Paired Bone (.L/.R)", toggle=True)
            return

        row = column.row(align=True)
        row.prop(self, 'partial', text='Selected' if self.partial else 'All', toggle=True)
        row.prop(self, 'remove', text='Remove' if self.remove else 'Symmetrize', toggle=True)

        is_normal_mirror = not self.partial and self.has_custom_normals and self.mirror_custom_normals

        if not self.remove:
            if self.has_uvs:
                column.separator()
                column.prop(self, "offset_uvs", text="Offset UVs", toggle=True)
                if self.offset_uvs:
                    column.row(align=True).prop(self, "uv_offset", text="")

            if not self.partial:
                if not is_normal_mirror:
                    column.separator()
                    column.prop(self, "remove_redundant_center", toggle=True)
                    if self.remove_redundant_center:
                        column.row(align=True).prop(self, "redundant_threshold", text='Threshold', slider=True)
                    if self.has_vertex_groups:
                        column.separator()
                        column.prop(self, "mirror_vertex_groups", text="Mirror Vertex Groups", toggle=True)

                if self.has_custom_normals:
                    column.separator()
                    if self.mirror_custom_normals:
                        box = column.box()
                        col = box.column()
                        col.prop(self, "mirror_custom_normals", toggle=True)
                        b = col.box()
                        b.label(text="Custom Normal Pairing Method")
                        b.row().prop(self, "custom_normal_method", expand=True)
                        col.separator()
                        col.prop(self, "fix_center")
                        if self.fix_center:
                            bb = col.box()
                            bb.row().label(text="Fix Center Method")
                            bb.row().prop(self, "clear_sharps")
                            bb.row().prop(self, "fix_center_method", expand=True)
                    else:
                        column.prop(self, "mirror_custom_normals", toggle=True)

    def invoke(self, context, event):
        self.active = context.active_object
        self.weight_paint = context.mode == 'PAINT_WEIGHT'

        if self.partial and not self.weight_paint:
            bm = bmesh.from_edit_mesh(self.active.data)
            if not [v for v in bm.verts if v.select]:
                self.partial = False

        self.has_custom_normals = self.active.data.has_custom_normals
        self.has_vertex_groups = bool(self.active.vertex_groups)
        self.has_uvs = bool(self.active.data.uv_layers)

        if self.weight_paint and self.has_vertex_groups:
            self.mirror_vertex_groups = True

        if self.remove_redundant_center and _is_hyper_bevel(self.active):
            self.remove_redundant_center = False

        self.flick_distance = int(_pref('flick_distance', FLICK_DISTANCE_DEFAULT) * _hud_scale(context))

        mx = self.active.matrix_world
        self.mousepos = Vector((event.mouse_region_x, event.mouse_region_y, 0))

        view_origin = region_2d_to_origin_3d(context.region, context.region_data, self.mousepos)
        view_dir = region_2d_to_vector_3d(context.region, context.region_data, self.mousepos)
        self.origin = view_origin + view_dir * 10

        self.is_ctrl = False
        self.is_shift = False
        self.passthrough = None
        self.zoom = _zoom_factor(context, self.origin, scale=self.flick_distance, ignore_obj_scale=True)

        self.init_mouse = self.mousepos.copy()
        self.init_mouse_3d = region_2d_to_location_3d(
            context.region, context.region_data, self.init_mouse, self.origin
        )

        self.flick_vector = self.mousepos - self.init_mouse
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
        self.colors = [RED, RED, GREEN, GREEN, BLUE, BLUE]

        _ensure_default_lock(self.active)
        self.init_locked_axes = _locked_axes(self.active)

        _init_status(self, _draw_symmetrize_status(self))
        self.active.select_set(True)

        self.area = context.area
        self.HUD = bpy.types.SpaceView3D.draw_handler_add(self.draw_HUD, (context,), 'WINDOW', 'POST_PIXEL')
        self.VIEW3D = bpy.types.SpaceView3D.draw_handler_add(self.draw_VIEW3D, (context,), 'WINDOW', 'POST_VIEW')

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def draw_HUD(self, context):
        if context.area != self.area or self.passthrough:
            return

        scale = _hud_scale(context)
        axes = _locked_axes(self.active)
        p0 = self.init_mouse

        _draw_line_2d(p0, p0 + self.flick_vector, WHITE, width=1, alpha=0.99)

        color = RED if self.remove else WHITE
        circle_alpha = 0.2 if self.remove else 0.02
        _draw_circle_2d(p0, self.flick_distance, color, width=3, alpha=circle_alpha)

        top_y = p0.y + self.flick_distance
        bottom_y = p0.y - self.flick_distance + (15 * scale)

        if not self.weight_paint and self.partial:
            _draw_label(context, 'Selected', (p0.x, top_y), center=True, color=color, alpha=1.0)
            top_y -= 15 * scale

        if not self.weight_paint:
            title = 'Remove' if self.remove else 'Symmetrize'
            _draw_label(context, title, (p0.x, top_y), center=True, color=color, alpha=1.0 if self.remove else 0.8)
            top_y -= 12 * scale

        _draw_label(
            context,
            " ".join(axes) if axes else "None",
            (p0.x, top_y),
            center=True,
            size=10,
            color=WHITE if axes else RED,
            alpha=0.5 if axes else 1.0,
        )

        flick_title = self.flick_direction.replace('_', ' ').title() if self.flick_direction else "None"
        _draw_label(context, flick_title, (p0.x, bottom_y), center=True, alpha=0.4)

        if self.weight_paint:
            bottom_y -= 15 * scale
            topo = 'Topology' if self.use_topology else 'Position'
            tcolor, talpha = (BLUE, 1.0) if self.use_topology else (WHITE, 0.2)
            _draw_label(context, f"Weight Mirror ({topo})", (p0.x, bottom_y), center=True, color=tcolor, alpha=talpha)
            if self.has_vertex_groups:
                bottom_y -= 15 * scale
                title = f"{'Mirror' if self.mirror_vertex_groups else 'has'} Vertex Groups"
                gcolor, galpha = (GREEN, 1.0) if self.mirror_vertex_groups else (WHITE, 0.2)
                _draw_label(context, title, (p0.x, bottom_y), center=True, color=gcolor, alpha=galpha)
                bottom_y -= 15 * scale
                paired = 'Paired Bone (.L/.R)' if self.mirror_paired_bones else 'Same Group'
                pcolor, palpha = (YELLOW, 1.0) if self.mirror_paired_bones else (WHITE, 0.2)
                _draw_label(context, paired, (p0.x, bottom_y), center=True, color=pcolor, alpha=palpha)
            return

        if not self.remove:
            is_normal_mirror = not self.partial and self.has_custom_normals and self.mirror_custom_normals

            if self.has_uvs:
                bottom_y -= 15 * scale
                title = f"{'Offset' if self.offset_uvs else 'has'} UVs"
                ucolor, ualpha = (BLUE, 1.0) if self.offset_uvs else (WHITE, 0.2)
                dims = _text_dimensions(context, title)
                _draw_label(context, title, (p0.x - dims.x / 2, bottom_y), center=False, color=ucolor, alpha=ualpha)
                if not is_normal_mirror and self.remove_redundant_center:
                    _draw_label(context, " ⚠", (p0.x + dims.x / 2, bottom_y), center=False, size=18, color=YELLOW)

            if not is_normal_mirror:
                if self.remove_redundant_center:
                    bottom_y -= 15 * scale
                    _draw_label(context, "Remove Redundant Center", (p0.x, bottom_y), center=True, color=RED)

                if self.has_vertex_groups:
                    bottom_y -= 15 * scale
                    title = f"{'Mirror' if self.mirror_vertex_groups else 'has'} Vertex Groups"
                    gcolor, galpha = (GREEN, 1.0) if self.mirror_vertex_groups else (WHITE, 0.2)
                    _draw_label(context, title, (p0.x, bottom_y), center=True, color=gcolor, alpha=galpha)

            if self.has_custom_normals:
                bottom_y -= 15 * scale
                title = f"{'Mirror' if self.mirror_custom_normals else 'has'} Custom Normals"
                ncolor, nalpha = (NORMAL_COLOR, 1.0) if self.mirror_custom_normals else (WHITE, 0.2)
                _draw_label(context, title, (p0.x, bottom_y), center=True, color=ncolor, alpha=nalpha)

    def draw_VIEW3D(self, context):
        if context.area != self.area:
            return

        axes = _locked_axes(self.active)
        if not axes:
            return

        for direction, axis_vec, color in zip(self.axes.keys(), self.axes.values(), self.colors):
            dir_name, axis_name = direction.split('_')
            if axis_name in axes:
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
            sp.lock_x = True

        can_finish = bool(_locked_axes(self.active))

        events = ['MOUSEMOVE', 'X', 'Y', 'Z']
        if self.weight_paint:
            events.append('T')
            if self.has_vertex_groups:
                events.extend(['V', 'B'])
        else:
            events.extend(['S', 'P'])
            if not self.remove:
                if self.has_uvs:
                    events.append('D')
                is_normal_mirror = not self.partial and self.has_custom_normals and self.mirror_custom_normals
                if not is_normal_mirror:
                    events.append('R')
                    if self.has_vertex_groups:
                        events.append('V')
                if self.has_custom_normals:
                    events.extend(['N', 'C'])

        if event.type in events:
            if self.passthrough:
                self.passthrough = False
                self.init_mouse = self.mousepos.copy()
                self.init_mouse_3d = region_2d_to_location_3d(
                    context.region, context.region_data, self.init_mouse, self.origin
                )
                self.zoom = _zoom_factor(
                    context, self.origin, scale=self.flick_distance, ignore_obj_scale=True
                )

            self._update_flick(context)

            if can_finish and self.flick_vector.length > self.flick_distance:
                self.finish()
                return self.execute(context)

            if (self.is_shift or self.is_ctrl) and event.type in {'X', 'Y', 'Z'} and event.value == 'PRESS':
                if self.is_ctrl:
                    sp.lock_x = event.type == 'X'
                    sp.lock_y = event.type == 'Y'
                    sp.lock_z = event.type == 'Z'
                else:
                    setattr(sp, f'lock_{event.type.lower()}', not getattr(sp, f'lock_{event.type.lower()}'))
                self._update_flick(context)
                _force_ui_update(context)

            elif self.weight_paint and event.type == 'T' and event.value == 'PRESS':
                self.use_topology = not self.use_topology
                _force_ui_update(context)

            elif self.weight_paint and event.type == 'V' and event.value == 'PRESS':
                self.mirror_vertex_groups = not self.mirror_vertex_groups
                _force_ui_update(context)

            elif self.weight_paint and event.type == 'B' and event.value == 'PRESS':
                self.mirror_paired_bones = not self.mirror_paired_bones
                _force_ui_update(context)

            elif (
                not self.weight_paint
                and event.type == 'X'
                and event.value == 'PRESS'
                and not (self.is_shift or self.is_ctrl)
            ):
                self.remove = not self.remove
                _force_ui_update(context)

            elif not self.weight_paint and event.type in {'S', 'P'} and event.value == 'PRESS':
                self.partial = not self.partial
                _force_ui_update(context)

            elif not self.weight_paint and event.type == 'D' and event.value == 'PRESS':
                self.offset_uvs = not self.offset_uvs
                _force_ui_update(context)

            elif not self.weight_paint and event.type == 'R' and event.value == 'PRESS':
                self.remove_redundant_center = not self.remove_redundant_center
                _force_ui_update(context)

            elif not self.weight_paint and event.type == 'V' and event.value == 'PRESS':
                self.mirror_vertex_groups = not self.mirror_vertex_groups
                _force_ui_update(context)

            elif not self.weight_paint and event.type in {'N', 'C'} and event.value == 'PRESS':
                self.mirror_custom_normals = not self.mirror_custom_normals
                _force_ui_update(context)

        elif _navigation_passthrough(event):
            self.passthrough = True
            return {'PASS_THROUGH'}

        elif can_finish and event.type in {'LEFTMOUSE', 'SPACE'} and event.value == 'PRESS':
            self.finish()
            if self.flick_direction:
                self._apply_flick_direction()
                return self.execute(context)
            return {'CANCELLED'}

        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self.finish()
            if _locked_axes(self.active) != self.init_locked_axes:
                self._restore_axis_locks()
            _force_ui_update(context)
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def _update_flick(self, context):
        self.flick_vector = self.mousepos - self.init_mouse
        if not self.flick_vector.length:
            self.flick_direction = ""
            return
        direction = _get_flick_direction(self, context, _locked_axes(self.active))
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

    def finish(self):
        if getattr(self, 'HUD', None):
            bpy.types.SpaceView3D.draw_handler_remove(self.HUD, 'WINDOW')
        if getattr(self, 'VIEW3D', None):
            bpy.types.SpaceView3D.draw_handler_remove(self.VIEW3D, 'WINDOW')
        _finish_status(self)

    def _execute_weight_paint(self, context):
        if not self.mirror_vertex_groups:
            self.report({'WARNING'}, "Mirror vertex groups disabled")
            return {'CANCELLED'}

        if self.axis != 'X':
            self.report({'WARNING'}, "Weight mirror only supports the X axis in Blender")
            return {'CANCELLED'}

        obj = context.active_object
        mesh = obj.data

        if not obj.vertex_groups or obj.vertex_groups.active_index < 0:
            self.report({'WARNING'}, "No active vertex group")
            return {'CANCELLED'}

        active_vg = obj.vertex_groups.active
        if self.mirror_paired_bones:
            paired_name = _paired_vertex_group_name(active_vg.name)
            if not paired_name or obj.vertex_groups.get(paired_name) is None:
                self.report(
                    {'WARNING'},
                    f"No paired vertex group for '{active_vg.name}' (expected .L/.R naming)",
                )
                return {'CANCELLED'}

        flick_dir, _ = self.flick_direction.split('_')
        sign = 1.0 if flick_dir == 'POSITIVE' else -1.0
        orig_mask = mesh.use_paint_mask_vertex

        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(mesh)
        bm.select_mode = {'VERT'}

        for v in bm.verts:
            v.select = (v.co.x * sign) > 1e-5

        bm.select_flush_mode()

        if self.mirror_paired_bones:
            paired_vg = obj.vertex_groups[paired_name]
            dvert = bm.verts.layers.deform.verify()
            # Blender mirrors in-place when the active group is weighted on both sides.
            # Clear the paired group and the active group on the destination side so
            # vertex_group_mirror always copies source -> paired.
            _deform_clear_vgroup(bm, dvert, paired_vg.index)
            _deform_remove_vgroup_selected(bm, dvert, active_vg.index)

        bmesh.update_edit_mesh(mesh)

        bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
        mesh.use_paint_mask_vertex = True

        bpy.ops.object.vertex_group_mirror(
            mirror_weights=True,
            flip_group_names=self.mirror_paired_bones,
            all_groups=False,
            use_topology=self.use_topology,
        )

        mesh.use_paint_mask_vertex = orig_mask
        return {'FINISHED'}

    def _execute_edit_mesh(self, context):
        obj = context.active_object
        obj.update_from_editmode()

        data = {
            'direction': f"{self.direction}_{self.axis}",
            'threshold': self.threshold,
            'partial': self.partial,
            'remove': self.remove,
            'remove_redundant_center': self.remove_redundant_center,
            'redundant_threshold': self.redundant_threshold,
            'uv_offset': Vector(self.uv_offset) if self.has_uvs and self.offset_uvs else Vector((0, 0)),
            'mirror_vertex_groups': bool(self.has_vertex_groups and self.mirror_vertex_groups),
            'mirror_custom_normals': bool(self.has_custom_normals and self.mirror_custom_normals),
            'custom_normal_method': self.custom_normal_method,
            'fix_center': self.fix_center,
            'fix_center_method': self.fix_center_method,
            'clear_sharps': self.clear_sharps,
        }

        ret = symmetrize_mesh(obj, data)

        _flash_draw['custom_normal'] = ret['custom_normal']
        _flash_draw['remove'] = self.remove
        _flash_draw['indices'] = ret['center'] if self.remove else ret['mirror'] + ret['center']

        if _flash_draw['indices']:
            bpy.ops.mesh.symmetrize_plus_draw('INVOKE_DEFAULT')

        return {'FINISHED'}

    def execute(self, context):
        if context.mode == 'PAINT_WEIGHT' or self.weight_paint:
            return self._execute_weight_paint(context)
        return self._execute_edit_mesh(context)


classes = (
    SymmetrizePlusPreferences,
    SymmetrizePlusProps,
    MESH_OT_symmetrize_plus_draw,
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
