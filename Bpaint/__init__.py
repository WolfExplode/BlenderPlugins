import os

import bpy
import numpy as np
from bpy_extras import view3d_utils
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.interpolate import poly_3d_calc

from . import world_size

bl_info = {
    "name": "Bpaint",
    "author": "WXP",
    "version": (0, 4, 0),
    "blender": (5, 1, 0),
    "location": "Texture Paint mode",
    "description": "Bbrush-style modifier brushes for Texture Paint: hold Shift for Blur, hold Ctrl for Mask "
                   "(stencil image created automatically). Alt+LMB inverts the stroke instead of Ctrl. "
                   "Adds a Bpaint Average brush that paints the average color under it, "
                   "and a World Size toggle that keeps brush size constant in world units.",
    "category": "Paint",
}

_ESSENTIALS_TEXTURE = "brushes/essentials_brushes-mesh_texture.blend/Brush/"

MASK_BRUSH_NAME = "Bpaint Mask"
AVERAGE_BRUSH_NAME = "Bpaint Average"

# Brushes Bpaint adds to the user's brush library: name -> (essentials brush it copies, settings changed).
_BRUSHES = {
    # Blender's own Mask brush is stuck at 0.5 strength, and it is the Ctrl brush.
    MASK_BRUSH_NAME: ("Mask", {"strength": 1.0}),
    # Its color is set to the average under the cursor when each stroke starts.
    AVERAGE_BRUSH_NAME: ("Paint Soft", {}),
}

# One slot per modifier. "default" is used until the user picks another brush while holding that modifier.
# The Ctrl default is None because the Bpaint Mask brush lives wherever the user's brush library is.
_slots = {
    "SHIFT": {"default": ("ESSENTIALS", "", _ESSENTIALS_TEXTURE + "Blur"), "secondary": None},
    "CTRL": {"default": None, "secondary": None},
}

_MODIFIER_KEYS = {
    "SHIFT": ("LEFT_SHIFT", "RIGHT_SHIFT"),
    "CTRL": ("LEFT_CTRL", "RIGHT_CTRL"),
}

# Only one slot can be engaged at a time. primary/applied are only set while it is engaged.
_state = {"slot": None, "primary": None, "applied": None}

STENCIL_NAME = "Bpaint Mask"

addon_keymaps = []


def _read_ref(context):
    ref = context.tool_settings.image_paint.brush_asset_reference
    if ref is None:
        return None
    return (ref.asset_library_type, ref.asset_library_identifier, ref.relative_asset_identifier)


def _activate(triple):
    try:
        return "FINISHED" in bpy.ops.brush.asset_activate(
            asset_library_type=triple[0],
            asset_library_identifier=triple[1],
            relative_asset_identifier=triple[2],
        )
    except RuntimeError:
        return False


def _brush_file(name):
    return os.path.join("Saved", "Brushes", name + ".asset.blend")


def _brush_library():
    """The asset library the user's brushes are saved to.

    Blender saves brush assets to <library>/Saved/Brushes, so it is the first library that
    already has some there. With none saved yet, the User Library, else the first library.
    """
    libs = bpy.context.preferences.filepaths.asset_libraries
    for lib in libs:
        folder = os.path.join(lib.path, "Saved", "Brushes")
        if os.path.isdir(folder) and any(f.endswith(".asset.blend") for f in os.listdir(folder)):
            return lib
    return libs.get("User Library") or next(iter(libs), None)


def _brush_ref(name):
    lib = _brush_library()
    if lib is None:
        return None
    return ("CUSTOM", lib.name, _brush_file(name) + "/Brush/" + name)


def _missing_brushes():
    lib = _brush_library()
    if lib is None:
        return []
    return [name for name in _BRUSHES if not os.path.exists(os.path.join(lib.path, _brush_file(name)))]


def _save_brush(context, name):
    """Save one Bpaint brush to the user's brush library, as a copy of its essentials brush.

    Only brush.asset_save_as (what Duplicate Asset runs) writes an asset file that Blender
    lets you save changes to, and it copies the active brush with its current settings.
    """
    source_name, settings = _BRUSHES[name]
    if not _activate(("ESSENTIALS", "", _ESSENTIALS_TEXTURE + source_name)):
        return False
    source = context.tool_settings.image_paint.brush
    uid = source.session_uid
    original = {key: getattr(source, key) for key in settings}
    for key, value in settings.items():
        setattr(source, key, value)
    try:
        bpy.ops.brush.asset_save_as(name=name, asset_library_reference=_brush_library().name)
    except RuntimeError:
        return False
    finally:
        # The settings were changed on this session's copy of the essentials brush, so put them back.
        # brush.asset_revert can't do it: saving reloads the library, and it fails until that finishes.
        source = next((b for b in bpy.data.brushes if b.session_uid == uid), None)
        if source is not None:
            for key, value in original.items():
                setattr(source, key, value)
    return True


# Creating the brushes switches the active brush, and activating fails until Blender has finished
# loading the asset libraries (which saving a brush starts again), so each step is retried.
_setup = {"previous": None, "attempts": 0}


def _brush_setup_step(context):
    missing = _missing_brushes()
    if missing and _setup["previous"] is None:
        _setup["previous"] = _read_ref(context)
    for name in missing:
        if not _save_brush(context, name):
            return False
    if _setup["previous"] is not None:
        if not _activate(_setup["previous"]):
            return False
        _setup["previous"] = None
    return True


def _brush_setup_tick():
    """Timer: create the missing brushes in a window that is in Texture Paint, then restore its brush."""
    for window in bpy.context.window_manager.windows:
        area = next((a for a in window.screen.areas if a.type == "VIEW_3D"), None)
        if area is None:
            continue
        region = next(r for r in area.regions if r.type == "WINDOW")
        with bpy.context.temp_override(window=window, area=area, region=region):
            if bpy.context.mode != "PAINT_TEXTURE":
                continue
            if _brush_setup_step(bpy.context):
                return None
            _setup["attempts"] -= 1
            return 0.5 if _setup["attempts"] > 0 else None
    return None


def _schedule_brush_creation(*_args):
    if _missing_brushes() and not bpy.app.timers.is_registered(_brush_setup_tick):
        _setup["attempts"] = 40
        bpy.app.timers.register(_brush_setup_tick, first_interval=0.1)


_msgbus_owner = object()


def _subscribe_mode_changes():
    bpy.msgbus.clear_by_owner(_msgbus_owner)
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.Object, "mode"), owner=_msgbus_owner, args=(), notify=_schedule_brush_creation
    )


@bpy.app.handlers.persistent
def _on_load(_filepath):
    # Loading a file drops message bus subscriptions, and the file may open in Texture Paint.
    _subscribe_mode_changes()
    _schedule_brush_creation()


def _modifier_held(event, slot):
    return event.shift if slot == "SHIFT" else event.ctrl


def _engage(context, slot):
    if _state["slot"] is not None:
        return
    primary = _read_ref(context)
    if primary is None:
        return
    target = _slots[slot]["secondary"] or _slots[slot]["default"]
    if target is None:
        if MASK_BRUSH_NAME in _missing_brushes():
            _schedule_brush_creation()
            return
        target = _brush_ref(MASK_BRUSH_NAME)
    if primary == target:
        # Already on the secondary brush, so nothing to swap and nothing to restore.
        return
    if _activate(target):
        _state.update(slot=slot, primary=primary, applied=_read_ref(context))


def _release(context):
    slot = _state["slot"]
    if slot is None:
        return
    current = _read_ref(context)
    # A brush picked while the modifier was held becomes that slot's new secondary.
    if current is not None and current != _state["applied"]:
        _slots[slot]["secondary"] = current
    _activate(_state["primary"])
    _state.update(slot=None, primary=None, applied=None)


def _paint_canvas(context):
    ip = context.tool_settings.image_paint
    if ip.mode == "IMAGE":
        return ip.canvas
    mat = context.object.active_material if context.object else None
    if mat is None or not mat.texture_paint_images:
        return None
    return mat.texture_paint_images[min(mat.paint_active_slot, len(mat.texture_paint_images) - 1)]


def _fill_udim_tiles(context, image, canvas):
    """Give every UDIM tile of the stencil a black buffer sized like the canvas tile.

    image.tiles.new() only adds an empty tile, and image.tile_fill needs an Image Editor,
    so another area is borrowed for the duration of the call.
    """
    area = next((a for a in context.screen.areas if a != context.area), None)
    if area is None:
        return False
    old_type = area.ui_type
    try:
        area.ui_type = "IMAGE_EDITOR"
        space = area.spaces.active
        prev_image = space.image
        space.image = image
        region = next(r for r in area.regions if r.type == "WINDOW")
        with context.temp_override(area=area, space_data=space, region=region):
            for tile in image.tiles:
                if tile.size[0]:
                    continue
                src = canvas.tiles.get(tile.number)
                width, height = src.size if src else canvas.size
                image.tiles.active = tile
                bpy.ops.image.tile_fill(
                    color=(0, 0, 0, 1), generated_type="BLANK",
                    width=width, height=height, float=False, alpha=False,
                )
        space.image = prev_image
    finally:
        area.ui_type = old_type
    return True


def _ensure_stencil(context):
    """The Mask brush paints into the stencil image, so make sure one exists and is enabled."""
    ip = context.tool_settings.image_paint
    if ip.stencil_image is None:
        canvas = _paint_canvas(context)
        width, height = canvas.size if canvas and canvas.size[0] else (2048, 2048)
        tiled = canvas is not None and canvas.source == "TILED"
        image = bpy.data.images.new(STENCIL_NAME, width, height, alpha=False, tiled=tiled)
        if tiled:
            for tile in canvas.tiles:
                if tile.number != 1001:
                    image.tiles.new(tile_number=tile.number)
            _fill_udim_tiles(context, image, canvas)
        ip.stencil_image = image
    ip.use_stencil_layer = True


def _paint_uv_layer(context, mesh):
    ip = context.tool_settings.image_paint
    mat = context.object.active_material
    if ip.mode == "MATERIAL" and mat is not None and mat.texture_paint_slots:
        slot = mat.texture_paint_slots[min(mat.paint_active_slot, len(mat.texture_paint_slots) - 1)]
        if slot is not None and slot.uv_layer in mesh.uv_layers:
            return mesh.uv_layers[slot.uv_layer]
    return mesh.uv_layers.active


def _average_under_cursor(context, event):
    """Mean color of the paint image under the brush circle, in scene linear.

    Rays are cast through a grid of points inside the screen-space brush circle, so only the
    texels on the visible surface under the brush count, like the projected stroke itself.
    Mapping the circle straight into UV space instead picks up other islands and empty
    texture space wherever the UV density differs from the face under the cursor.
    """
    region, rv3d, obj = context.region, context.region_data, context.object
    image = _paint_canvas(context)
    if rv3d is None or obj is None or obj.type != "MESH" or image is None:
        return None
    if image.source == "TILED" or not image.size[0]:
        return None

    obj_eval = obj.evaluated_get(context.evaluated_depsgraph_get())
    matrix = obj_eval.matrix_world
    inv = matrix.inverted()
    inv3 = inv.to_3x3()
    mesh = obj_eval.data
    uv_layer = _paint_uv_layer(context, mesh)
    if uv_layer is None:
        return None

    # Indexing the mesh's RNA collections per hit is slow, so read everything once.
    co = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    loop_verts = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", loop_verts)
    loop_uvs = np.empty(len(mesh.loops) * 2, dtype=np.float32)
    uv_layer.uv.foreach_get("vector", loop_uvs)
    loop_uvs = loop_uvs.reshape(-1, 2)
    starts = np.empty(len(mesh.polygons), dtype=np.int32)
    mesh.polygons.foreach_get("loop_start", starts)
    totals = np.empty(len(mesh.polygons), dtype=np.int32)
    mesh.polygons.foreach_get("loop_total", totals)
    hidden = np.empty(len(mesh.polygons), dtype=bool)
    mesh.polygons.foreach_get("hide", hidden)

    if hidden.any():
        # Object.ray_cast hits hidden faces too, and painting ignores them, so cast against
        # a tree of the visible faces only. Its hit indices count visible faces.
        visible = np.flatnonzero(~hidden)
        faces = np.split(loop_verts, starts[1:])
        tree = BVHTree.FromPolygons(co.tolist(), [faces[i].tolist() for i in visible])

        def ray_cast(origin, direction):
            location, _normal, index, _distance = tree.ray_cast(origin, direction)
            return (location, int(visible[index])) if location is not None else None
    else:
        def ray_cast(origin, direction):
            hit, location, _normal, face = obj_eval.ray_cast(origin, direction)
            return (location, face) if hit else None

    def cast(coord):
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        return ray_cast(inv @ origin, inv3 @ direction)

    def uv_at(location, face):
        loops = slice(starts[face], starts[face] + totals[face])
        weights = poly_3d_calc([Vector(v) for v in co[loop_verts[loops]]], location)
        return np.asarray(weights) @ loop_uvs[loops]

    center = Vector((event.mouse_region_x, event.mouse_region_y))
    ip = context.tool_settings.image_paint
    ups = ip.unified_paint_settings
    size_owner = ups if ups.use_unified_size else ip.brush
    if size_owner.use_locked_size == "SCENE":
        # The circle's screen size depends on the depth of the surface under the cursor.
        hit = cast(center)
        if hit is None:
            return None
        world_center = matrix @ hit[0]
        right = rv3d.view_matrix.inverted().to_3x3() @ Vector((1.0, 0.0, 0.0))
        a = view3d_utils.location_3d_to_region_2d(region, rv3d, world_center)
        b = view3d_utils.location_3d_to_region_2d(
            region, rv3d, world_center + right.normalized() * size_owner.unprojected_size / 2
        )
        if a is None or b is None:
            return None
        radius = (b - a).length
    else:
        radius = size_owner.size / 2

    # About 800 rays at any brush size; one per pixel for brushes under 16 px.
    step = max(1.0, radius / 16)
    n = int(radius / step)
    uvs = []
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            offset = Vector((i * step, j * step))
            if offset.length_squared > radius * radius:
                continue
            hit = cast(center + offset)
            if hit is not None:
                uvs.append(uv_at(*hit))
    if not uvs:
        return None

    width, height = image.size
    uvs = np.array(uvs, dtype=np.float64) % 1.0
    xs = np.minimum((uvs[:, 0] * width).astype(int), width - 1)
    ys = np.minimum((uvs[:, 1] * height).astype(int), height - 1)
    pixels = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    texels = pixels.reshape(height, width, 4)[ys, xs]

    rgb = texels[:, :3]
    if not image.is_float and image.colorspace_settings.name == "sRGB":
        rgb = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    # Weight by alpha so transparent pixels don't pull the average towards their hidden color.
    weight = texels[:, 3]
    total = weight.sum()
    if total <= 0:
        return None
    return (rgb * weight[:, None]).sum(axis=0) / total


class PAINT_OT_bpaint_modifier(bpy.types.Operator):
    """Restores the primary brush when Shift or Ctrl is released; Ctrl also switches on press.

    Shift only switches once a stroke or wheel resize starts, so Shift shortcuts keep working
    on the primary brush. Ctrl switches to the Mask brush as soon as it is pressed.
    """

    bl_idname = "paint.bpaint_modifier"
    bl_label = "Bpaint Modifier Key"
    bl_options = {"INTERNAL"}

    slot: bpy.props.EnumProperty(items=(("SHIFT", "Shift", ""), ("CTRL", "Ctrl", "")))
    press: bpy.props.BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        return context.mode == "PAINT_TEXTURE"

    def invoke(self, context, event):
        if self.press:
            if event.ctrl and not event.shift and not event.alt:
                _engage(context, "CTRL")
        elif _state["slot"] == self.slot and not _modifier_held(event, self.slot):
            _release(context)
        return {"PASS_THROUGH"}


class PAINT_OT_bpaint_stroke(bpy.types.Operator):
    """Runs before every stroke, then passes the click on to it.

    In order: Shift/Ctrl switch to that modifier's brush (and the Mask brush gets a stencil),
    the 3D cursor moves to the surface and the brush takes its world size there, and the
    Bpaint Average brush takes the average color under it at that size.
    """

    bl_idname = "paint.bpaint_stroke"
    bl_label = "Bpaint Stroke Setup"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        return context.mode == "PAINT_TEXTURE"

    def invoke(self, context, event):
        if not event.alt and event.shift != event.ctrl:
            _engage(context, "SHIFT" if event.shift else "CTRL")
        ip = context.tool_settings.image_paint
        brush = ip.brush
        if brush is not None and brush.image_brush_type == "MASK":
            _ensure_stencil(context)
        if context.area is None or context.area.type != "VIEW_3D":
            return {"PASS_THROUGH"}
        world_size.before_stroke(context)
        if brush is not None and brush.name == AVERAGE_BRUSH_NAME:
            color = _average_under_cursor(context, event)
            if color is not None:
                ups = ip.unified_paint_settings
                (ups if ups.use_unified_color else brush).color = color
        return {"PASS_THROUGH"}


class PAINT_OT_bpaint_shift_wheel(bpy.types.Operator):
    """Shift/Ctrl+wheel resizes the brush that modifier switched to, instead of panning the view."""

    bl_idname = "paint.bpaint_shift_wheel"
    bl_label = "Bpaint Resize Secondary Brush"
    bl_options = {"INTERNAL"}

    direction: bpy.props.IntProperty(default=1)

    @classmethod
    def poll(cls, context):
        return context.mode == "PAINT_TEXTURE"

    def invoke(self, context, event):
        if event.alt or event.shift == event.ctrl:
            return {"PASS_THROUGH"}
        _engage(context, "SHIFT" if event.shift else "CTRL")
        ip = context.tool_settings.image_paint
        ups = ip.unified_paint_settings
        target = ups if ups.use_unified_size else ip.brush
        if target is None:
            return {"CANCELLED"}
        step = max(1, round(target.size * 0.1))
        target.size = max(1, target.size + self.direction * step)
        return {"FINISHED"}


classes = (PAINT_OT_bpaint_modifier, PAINT_OT_bpaint_stroke, PAINT_OT_bpaint_shift_wheel)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    world_size.register()
    # The brushes can only be created in Texture Paint mode, so that happens on entering it.
    _subscribe_mode_changes()
    bpy.app.handlers.load_post.append(_on_load)
    _schedule_brush_creation()
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:
        return

    km = kc.keymaps.new(name="Window", space_type="EMPTY")
    for slot, keys in _MODIFIER_KEYS.items():
        for key in keys:
            for value in ("PRESS", "RELEASE") if slot == "CTRL" else ("RELEASE",):
                kmi = km.keymap_items.new(
                    "paint.bpaint_modifier", key, value, shift=-1, ctrl=-1, alt=-1, oskey=-1
                )
                kmi.properties.slot = slot
                kmi.properties.press = value == "PRESS"
                addon_keymaps.append((km, kmi))

    # Add-on items run before the default Image Paint ones, so these take over Ctrl+LMB
    # (normally the inverted stroke) and move inversion to Alt+LMB.
    # Each add-on item lands at the top of the user keymap, so they are added in reverse:
    # the mask setup must end up first so it runs before the stroke starts.
    km = kc.keymaps.new(name="Image Paint", space_type="EMPTY")
    for wheel, direction in (("WHEELUPMOUSE", 1), ("WHEELDOWNMOUSE", -1)):
        for mod in ({"shift": True}, {"ctrl": True}):
            kmi = km.keymap_items.new("paint.bpaint_shift_wheel", wheel, "PRESS", head=True, **mod)
            kmi.properties.direction = direction
            addon_keymaps.append((km, kmi))
    kmi = km.keymap_items.new("paint.image_paint", "LEFTMOUSE", "PRESS", alt=True, ctrl=-1)
    kmi.properties.mode = "INVERT"
    addon_keymaps.append((km, kmi))
    kmi = km.keymap_items.new("paint.image_paint", "LEFTMOUSE", "PRESS", ctrl=True)
    kmi.properties.mode = "NORMAL"
    addon_keymaps.append((km, kmi))
    kmi = km.keymap_items.new("paint.bpaint_stroke", "LEFTMOUSE", "PRESS", ctrl=True, alt=-1)
    addon_keymaps.append((km, kmi))
    kmi = km.keymap_items.new("paint.bpaint_stroke", "LEFTMOUSE", "PRESS", shift=True, head=True)
    addon_keymaps.append((km, kmi))
    kmi = km.keymap_items.new("paint.bpaint_stroke", "LEFTMOUSE", "PRESS", alt=-1, head=True)
    addon_keymaps.append((km, kmi))


def unregister():
    if bpy.app.timers.is_registered(_brush_setup_tick):
        bpy.app.timers.unregister(_brush_setup_tick)
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    bpy.msgbus.clear_by_owner(_msgbus_owner)
    if _state["slot"] is not None:
        _release(bpy.context)
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    world_size.unregister()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
