"""World-space brush size for Texture Paint (formerly the World-Space Brush add-on).

Blender only offers a Scene radius in Sculpt and Grease Pencil. Here each brush's pixel size
is rescaled so it keeps a constant size in Blender units at the 3D cursor's depth, and every
stroke snaps the cursor to the surface it starts on so that depth follows the painting.
"""

import blf
import bpy
from bpy.app.handlers import persistent
from bpy_extras import view3d_utils
from mathutils import Vector

# Brush name (None under Unified Size) -> size in Blender units. Each brush keeps its own,
# so swapping brushes doesn't count as resizing one.
_world_sizes = {}
# What the active brush looked like after the last sync. A pixel size that differs from it
# was set by the user, and becomes that brush's new world size.
_last = {"key": None, "px": None}
_debug = {"ppu": None, "world": None, "px": None}
_modal = {"running": False, "timer": None}
_draw_handle = None


def _view3d(context):
    area = context.area
    if area is None or area.type != "VIEW_3D":
        area = next((a for a in context.window.screen.areas if a.type == "VIEW_3D"), None)
    if area is None:
        return None, None
    region = next((r for r in area.regions if r.type == "WINDOW"), None)
    return region, area.spaces.active.region_3d


def _pixels_per_unit(context, region, rv3d):
    cursor = context.scene.cursor.location
    right = rv3d.view_matrix.inverted().to_3x3() @ Vector((1.0, 0.0, 0.0))
    a = view3d_utils.location_3d_to_region_2d(region, rv3d, cursor)
    b = view3d_utils.location_3d_to_region_2d(region, rv3d, cursor + right.normalized())
    if a is None or b is None:
        return None
    return (b - a).length


def sync(context):
    """Match the active brush's pixel size to its world size at the 3D cursor's depth."""
    ip = context.tool_settings.image_paint
    if ip.brush is None:
        return
    ups = ip.unified_paint_settings
    owner, key = (ups, None) if ups.use_unified_size else (ip.brush, ip.brush.name)
    region, rv3d = _view3d(context)
    if region is None:
        return
    ppu = _pixels_per_unit(context, region, rv3d)
    if not ppu:
        return

    px = owner.size
    if (key == _last["key"] and px != _last["px"]) or key not in _world_sizes:
        _world_sizes[key] = px / ppu
    else:
        target = max(1, min(round(_world_sizes[key] * ppu), 10000))
        if target != px:
            owner.size = px = target
    _last.update(key=key, px=px)
    _debug.update(ppu=ppu, world=_world_sizes[key], px=px)


def before_stroke(context):
    """Snap the 3D cursor to the surface under the mouse, then size the brush for that depth."""
    bpy.ops.view3d.cursor3d("INVOKE_DEFAULT")
    if context.scene.bpaint.world_size:
        sync(context)


def _draw_debug():
    font = 0
    blf.size(font, 14)
    fmt = lambda v, spec: "None" if v is None else format(v, spec)
    lines = (
        "Bpaint world size",
        "px per BU at cursor: " + fmt(_debug["ppu"], ".3f"),
        "world size (BU):     " + fmt(_debug["world"], ".4f"),
        "brush size (px):     " + fmt(_debug["px"], "d"),
    )
    for i, text in enumerate(reversed(lines)):
        blf.position(font, 20, 60 + i * 18, 0)
        blf.draw(font, text)


def _set_debug_overlay(enable):
    global _draw_handle
    if enable and _draw_handle is None:
        _draw_handle = bpy.types.SpaceView3D.draw_handler_add(_draw_debug, (), "WINDOW", "POST_PIXEL")
    elif not enable and _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, "WINDOW")
        _draw_handle = None


class PAINT_OT_bpaint_world_size(bpy.types.Operator):
    """Keeps Texture Paint brush sizes constant in world units while the view changes"""

    bl_idname = "paint.bpaint_world_size"
    bl_label = "Bpaint World Size"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        if _modal["running"]:
            return {"CANCELLED"}
        wm = context.window_manager
        _modal.update(running=True, timer=wm.event_timer_add(0.01, window=context.window))
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if not context.scene.bpaint.world_size:
            self.cancel(context)
            return {"CANCELLED"}
        if event.type == "TIMER" and context.mode == "PAINT_TEXTURE":
            sync(context)
            if _draw_handle is not None:
                for area in context.window.screen.areas:
                    if area.type == "VIEW_3D":
                        area.tag_redraw()
        return {"PASS_THROUGH"}

    def cancel(self, context):
        if _modal["timer"] is not None:
            context.window_manager.event_timer_remove(_modal["timer"])
        _modal.update(running=False, timer=None)


def _start(context):
    if not _modal["running"] and context.window is not None:
        bpy.ops.paint.bpaint_world_size()


def _world_size_update(self, context):
    if self.world_size:
        # Turning it on keeps the sizes brushes have right now.
        _world_sizes.clear()
        _start(context)


class BpaintSceneSettings(bpy.types.PropertyGroup):
    world_size: bpy.props.BoolProperty(
        name="World Size",
        description="Keep the Texture Paint brush size constant in world units, measured at the 3D cursor. "
                    "Each stroke moves the 3D cursor to the surface it starts on",
        default=False,
        update=_world_size_update,
    )
    world_size_debug: bpy.props.BoolProperty(
        name="Debug Overlay",
        description="Show the world size calculation in the viewport",
        default=False,
        update=lambda self, context: _set_debug_overlay(self.world_size_debug),
    )


def _draw_toggle(self, context):
    if context.mode != "PAINT_TEXTURE":
        return
    settings = context.scene.bpaint
    row = self.layout.row(align=True)
    row.prop(settings, "world_size", icon="WORLD", toggle=True)
    row.prop(settings, "world_size_debug", text="", icon="CONSOLE", toggle=True)


def _start_if_enabled():
    """Modal operators don't survive loading a file, so restart it for scenes saved with it on."""
    wm = bpy.context.window_manager
    if _modal["running"] or not wm.windows:
        return None
    window = wm.windows[0]
    settings = window.scene.bpaint
    _set_debug_overlay(settings.world_size_debug)
    if settings.world_size:
        with bpy.context.temp_override(window=window):
            _start(bpy.context)
    return None


@persistent
def _on_load(_filepath):
    _modal.update(running=False, timer=None)
    bpy.app.timers.register(_start_if_enabled, first_interval=0.1)


classes = (BpaintSceneSettings, PAINT_OT_bpaint_world_size)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.bpaint = bpy.props.PointerProperty(type=BpaintSceneSettings)
    bpy.types.VIEW3D_PT_tools_brush_settings.append(_draw_toggle)
    bpy.app.handlers.load_post.append(_on_load)
    bpy.app.timers.register(_start_if_enabled, first_interval=0.1)


def unregister():
    if bpy.app.timers.is_registered(_start_if_enabled):
        bpy.app.timers.unregister(_start_if_enabled)
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    bpy.types.VIEW3D_PT_tools_brush_settings.remove(_draw_toggle)
    _set_debug_overlay(False)
    if _modal["timer"] is not None:
        bpy.context.window_manager.event_timer_remove(_modal["timer"])
    _modal.update(running=False, timer=None)
    del bpy.types.Scene.bpaint
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
