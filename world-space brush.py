bl_info = {
    "name": "World-Space Brush Radius For Texture Painting",
    "author": "WolfExplode + chatgpt",
    "version": (1, 1, 0),
    "blender": (4, 0, 0),
    "location": "Tool > Brush Settings (while in texture paint mode)",
    "description": "Keeps Texture Paint brush size constant in world units; with debug overlay & logs.",
    "category": "Paint",
}

import bpy
from bpy.types import Operator, PropertyGroup
from bpy.props import BoolProperty, PointerProperty
from mathutils import Vector
from bpy_extras import view3d_utils
import blf

# -----------------------------
# Global debug state
# -----------------------------
_DBG = {
    "active": False,
    "msg": "",
    "last_ppu": None,
    "last_radius_px": None,
    "last_brush_px": None,
    "last_depth": None,
}
_DRAW_HANDLE = None
_RUNNING = False
_STATE = {
    "world_diameter_bu": 0.10,
    "update_rate": 0.05,
}


def dbg_print(*args):
    # Console logging follows the overlay toggle
    if getattr(bpy.context.scene, 'wltp_dbg', None) and bpy.context.scene.wltp_dbg.enable_overlay:
        print("[WLTP]", *args)


# -----------------------------
# Utilities
# -----------------------------

def get_texpaint_brush(context):
    ts = context.tool_settings
    ip = ts.image_paint
    return ip.brush if ip else None


def region_under_mouse(context, mx_win, my_win):
    """Find VIEW_3D area+WINDOW region that contains (window) mouse coords."""
    for area in context.window.screen.areas:
        if area.type != 'VIEW_3D':
            continue
        for region in area.regions:
            if region.type != 'WINDOW':
                continue
            if region.x <= mx_win < region.x + region.width and region.y <= my_win < region.y + region.height:
                return area, region
    # Fallback: first 3D view
    for area in context.window.screen.areas:
        if area.type == 'VIEW_3D':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return area, region
    return None, None


def pixels_per_world_unit(area, region, world_point):
    """Pixels per 1 world unit around given world point (sample along view-right)."""
    rv3d = area.spaces.active.region_3d
    view_right_world = (rv3d.view_matrix.inverted().to_3x3() @ Vector((1, 0, 0))).normalized()
    p0 = world_point
    p1 = world_point + view_right_world  # +1 BU
    s0 = view3d_utils.location_3d_to_region_2d(region, rv3d, p0)
    s1 = view3d_utils.location_3d_to_region_2d(region, rv3d, p1)
    if s0 is None or s1 is None:
        return None
    return (s1 - s0).length


def fallback_depth_point(context, area, region):
    """If no surface under mouse: use 3D cursor depth slightly toward camera."""
    rv3d = area.spaces.active.region_3d
    cursor = context.scene.cursor.location.copy()
    cam = rv3d.view_matrix.inverted().translation
    dir_to_cam = (cam - cursor).normalized()
    return cursor + dir_to_cam * 0.001


def set_brush_pixel_radius(context, px_radius):
    """Apply brush size respecting Unified Size if enabled."""
    ts = context.tool_settings
    ups = ts.unified_paint_settings
    br = get_texpaint_brush(context)
    if br is None:
        return
    val = int(max(1, min(round(px_radius), 10000)))
    if ups.use_unified_size:
        ups.size = val
    else:
        br.size = val


# -----------------------------
# Property update callbacks
# -----------------------------

def wltp_enabled_update(self, context):
    # Start the modal operator when enabling; let it self-cancel when disabling
    # (it checks the property every tick).
    global _RUNNING
    if self.enabled and not _RUNNING:
        try:
            bpy.ops.wltp.update('INVOKE_DEFAULT')
        except Exception:
            pass

# -----------------------------
# Debug overlay draw
# -----------------------------

def draw_debug_overlay():
    if not _DBG["active"]:
        return
    font_id = 0
    try:
        blf.size(font_id, 14, 72)
    except TypeError:
        blf.size(font_id, 14)
    lines = [
        "WLTP Debug",
        f"PPU (px/BU):  {(_DBG['last_ppu'] if _DBG['last_ppu'] is not None else 'None')}",
        f"Desired pxR:  {(_DBG['last_radius_px'] if _DBG['last_radius_px'] is not None else 'None')}",
        f"Applied pxR:  {(_DBG['last_brush_px'] if _DBG['last_brush_px'] is not None else 'None')}",
        f"Depth (m):    {(_DBG['last_depth'] if _DBG['last_depth'] is not None else 'None')}",
    ]
    x, y = 20, 60
    for i, t in enumerate(lines):
        blf.position(font_id, x, y + (len(lines) - i - 1) * 18, 0)
        blf.draw(font_id, str(t))


def ensure_draw_handler(enable: bool):
    global _DRAW_HANDLE
    if enable and _DRAW_HANDLE is None:
        _DRAW_HANDLE = bpy.types.SpaceView3D.draw_handler_add(draw_debug_overlay, (), 'WINDOW', 'POST_PIXEL')
    elif not enable and _DRAW_HANDLE is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_DRAW_HANDLE, 'WINDOW')
        _DRAW_HANDLE = None


# -----------------------------
# Properties
# -----------------------------

class WLTP_Props(PropertyGroup):
    enabled: BoolProperty(
        name="Toggle world-space radius",
        description="Toggle brush size relative to the view or scene in world units (BU)",
        default=False,
        update=wltp_enabled_update,
    )


class WLTP_DebugProps(PropertyGroup):
    enable_overlay: BoolProperty(
        name="Show Debug Overlay",
        description="Draw computed values in the viewport and log to console",
        default=False,
        update=lambda s, c: ensure_draw_handler(s.enable_overlay),
    )


# -----------------------------
# Modal updater
# -----------------------------

class WLTP_OT_Update(Operator):
    """Modal timer that recomputes brush pixel size to match a world diameter."""
    bl_idname = "wltp.update"
    bl_label = "World-Locked Texture Brush Updater"
    _timer = None
    f_adjust_active = False

    def _update_world_diameter_from_brush(self, context, event):
        """
        On F-key release/confirm, convert the current pixel brush size
        to a world-space diameter and store it.
        """
        mx_win = event.mouse_x
        my_win = event.mouse_y
        area, region = region_under_mouse(context, mx_win, my_win)
        if not (area and region):
            return

        world_point = fallback_depth_point(context, area, region)
        ppu = pixels_per_world_unit(area, region, world_point)
        br = get_texpaint_brush(context)

        if ppu and ppu > 0.0 and br:
            ups = context.tool_settings.unified_paint_settings
            radius_px = ups.size if ups.use_unified_size else br.size
            radius_bu = float(radius_px) / float(ppu)
            _STATE["world_diameter_bu"] = max(0.0001, radius_bu * 2.0)

            # Sync overlay immediately so Desired and Applied match right away
            _DBG.update({
                "active": context.scene.wltp_dbg.enable_overlay,
                "last_ppu": round(ppu, 3),
                "last_radius_px": int(round(radius_bu * ppu)),
                "last_brush_px": radius_px,
                "msg": "World diameter set",
            })
            ensure_draw_handler(context.scene.wltp_dbg.enable_overlay)
            area.tag_redraw()

    def modal(self, context, event):
        props = context.scene.wltp
        dbg = context.scene.wltp_dbg

        if not props.enabled:
            self.cancel(context)
            _DBG["active"] = False
            ensure_draw_handler(False)
            return {'CANCELLED'}

        # Only act in texture paint
        if context.mode not in {'PAINT_TEXTURE', 'TEXTURE_PAINT'}:
            _DBG["msg"] = f"Inactive mode: {context.mode}"
            return {'PASS_THROUGH'}

        # Respect Blender's default F-key brush size adjuster.
        if event.type == 'F' and event.value == 'PRESS':
            self.f_adjust_active = True
            _DBG["msg"] = "Adjusting size (F)"
            return {'PASS_THROUGH'}
        
        # On F-release or confirm/cancel of the F-adjust operator
        is_release_f = event.type == 'F' and event.value == 'RELEASE'
        is_confirm_adjust = self.f_adjust_active and (
            (event.type in {'LEFTMOUSE', 'RIGHTMOUSE'} and event.value in {'PRESS', 'RELEASE'}) or
            (event.type in {'RET', 'SPACE', 'ESC'} and event.value == 'PRESS')
        )
        
        if is_release_f or is_confirm_adjust:
            if self.f_adjust_active:
                self._update_world_diameter_from_brush(context, event)
            self.f_adjust_active = False
            return {'PASS_THROUGH'}

        if event.type == 'TIMER' or event.type in {'MOUSEMOVE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            # Find region under the current mouse
            mx_win = event.mouse_x
            my_win = event.mouse_y
            area, region = region_under_mouse(context, mx_win, my_win)
            if not area or not region:
                _DBG["msg"] = "No VIEW_3D region"
                dbg_print("No VIEW_3D region under mouse.")
                return {'PASS_THROUGH'}

            rv3d = area.spaces.active.region_3d
            # Build view ray origin for depth calc (debug only)
            mr_x = event.mouse_region_x
            mr_y = event.mouse_region_y
            origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, (mr_x, mr_y))
            world_point = fallback_depth_point(context, area, region)

            # Compute pixels per world unit (BU) at that depth
            ppu = pixels_per_world_unit(area, region, world_point)
            if ppu is None or ppu <= 0.0:
                _DBG["msg"] = "PPU None/<=0"
                dbg_print("pixels_per_world_unit failed; s0/s1 None")
                return {'PASS_THROUGH'}

            desired_radius_bu = 0.5 * _STATE["world_diameter_bu"]
            desired_radius_px = desired_radius_bu * ppu

            # Apply brush size unless user is actively adjusting with F
            if not self.f_adjust_active:
                set_brush_pixel_radius(context, desired_radius_px)

            # Debug bookkeeping
            br = get_texpaint_brush(context)
            applied = None
            if br:
                ups = context.tool_settings.unified_paint_settings
                applied = ups.size if ups.use_unified_size else br.size

            depth = (world_point - origin).length
            _DBG.update({
                "active": dbg.enable_overlay,
                "last_ppu": round(ppu, 3),
                "last_radius_px": int(round(desired_radius_px)),
                "last_brush_px": applied,
                "last_depth": round(depth, 4) if depth is not None else None,
            })

            dbg_print(
                f"PPU={_DBG['last_ppu']} px/BU | desired_pxR={_DBG['last_radius_px']} | "
                f"applied={applied} | depth={_DBG['last_depth']}"
            )

            # Ensure overlay handler on/off matches toggle
            ensure_draw_handler(dbg.enable_overlay)

            # Request redraw so overlay updates
            area.tag_redraw()

        return {'PASS_THROUGH'}

    def execute(self, context):
        props = context.scene.wltp
        dbg = context.scene.wltp_dbg
        wm = context.window_manager

        if self._timer is None:
            self._timer = wm.event_timer_add(_STATE["update_rate"], window=context.window)
            wm.modal_handler_add(self)
            self.f_adjust_active = False
            _DBG["active"] = dbg.enable_overlay
            ensure_draw_handler(dbg.enable_overlay)
            dbg_print("WLTP modal started.")
            global _RUNNING
            _RUNNING = True
            return {'RUNNING_MODAL'}
        return {'CANCELLED'}

    def cancel(self, context):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None
        dbg_print("WLTP modal stopped.")
        global _RUNNING
        _RUNNING = False


# -----------------------------
# UI injection into brush settings
# -----------------------------

def draw_wltp_toggle_under_radius(self, context):
    # Append a compact toggle near the built-in Radius control in the
    # Brush Settings panel. We re-draw the radius on the same row so the
    # toggle appears adjacent, mimicking "under/next to radius" placement.
    if context.mode not in {'PAINT_TEXTURE', 'TEXTURE_PAINT'}:
        return
    props = getattr(context.scene, 'wltp', None)
    dbg = getattr(context.scene, 'wltp_dbg', None)
    if not props or not dbg:
        return
    br = get_texpaint_brush(context)
    if not br:
        return
    ups = context.tool_settings.unified_paint_settings
    layout = self.layout
    row = layout.row(align=True)
    row.prop(props, "enabled", text="Scene Radius", icon='WORLD', toggle=True)
    # Debug overlay toggle to the right of world-space toggle also controls logging
    row.prop(dbg, "enable_overlay", text="Debug", toggle=True)

# -----------------------------
# Registration
# -----------------------------

classes = (
    WLTP_Props,
    WLTP_DebugProps,
    WLTP_OT_Update,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.wltp = PointerProperty(type=WLTP_Props)
    bpy.types.Scene.wltp_dbg = PointerProperty(type=WLTP_DebugProps)
    ensure_draw_handler(False)
    # Inject our toggle into the Brush Settings panel
    try:
        bpy.types.VIEW3D_PT_tools_brush_settings.append(draw_wltp_toggle_under_radius)
    except Exception:
        pass

def unregister():
    ensure_draw_handler(False)
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    del bpy.types.Scene.wltp_dbg
    del bpy.types.Scene.wltp
    print("[WLTP] Unregistered.")
    # Remove UI injection
    try:
        bpy.types.VIEW3D_PT_tools_brush_settings.remove(draw_wltp_toggle_under_radius)
    except Exception:
        pass

if __name__ == "__main__":
    register()