bl_info = {
    "name": "World-Space Brush Radius For Texture Painting",
    "author": "WolfExplode",
    "version": (1, 2, 0),
    "blender": (3, 2, 0),
    "location": "Tool > Brush Settings (while in texture paint mode)",
    "description": "Keeps Texture Paint brush size constant in world units using 3D cursor as reference.",
    "doc_url": "https://github.com/WolfExplode/BlenderPlugins/blob/main/world-space%20brush.py",
    "category": "Paint"}

import bpy
import time
from bpy.types import Operator, PropertyGroup
from bpy.props import BoolProperty, PointerProperty
from mathutils import Vector
from bpy_extras import view3d_utils
import blf

# -----------------------------
# Global state
# -----------------------------
_DBG = {
    "active": False,
    "last_ppu": None,
    "last_radius_px": None,
    "last_brush_px": None,
    "last_view_matrix": None,
}
_DRAW_HANDLE = None
_RUNNING = False
_KEYMAPS = []
_STATE = {
    "world_diameter_bu": 0.10,
    "update_rate": 0.01,  # Increased frequency for better responsiveness during quick zoom
}


def dbg_print(*args):
    if getattr(bpy.context.scene, 'wltp_dbg', None) and bpy.context.scene.wltp_dbg.enable_overlay:
        print("[WLTP]", *args)


# -----------------------------
# Utilities
# -----------------------------

def get_texpaint_brush(context):
    ts = context.tool_settings
    ip = ts.image_paint
    return ip.brush if ip else None


def get_3d_view_area_region(context):
    """Get any available 3D view area and region."""
    for area in context.window.screen.areas:
        if area.type == 'VIEW_3D':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return area, region
    return None, None


def pixels_per_world_unit_at_cursor(context, area, region):
    """Calculate pixels per world unit at the 3D cursor location."""
    rv3d = area.spaces.active.region_3d
    cursor = context.scene.cursor.location.copy()
    
    # Get view right direction in world space
    view_right_world = (rv3d.view_matrix.inverted().to_3x3() @ Vector((1, 0, 0))).normalized()
    
    # Calculate two points 1 BU apart at cursor depth
    p0 = cursor
    p1 = cursor + view_right_world
    
    # Project to screen space
    s0 = view3d_utils.location_3d_to_region_2d(region, rv3d, p0)
    s1 = view3d_utils.location_3d_to_region_2d(region, rv3d, p1)
    
    if s0 is None or s1 is None:
        return None
    
    return (s1 - s0).length


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


def get_current_brush_size(context):
    """Get current brush size (unified or individual)."""
    br = get_texpaint_brush(context)
    if not br:
        return None
    ups = context.tool_settings.unified_paint_settings
    return ups.size if ups.use_unified_size else br.size


def has_view_changed_significantly(context, area):
    """Check if the view matrix has changed significantly since last check."""
    if not area or not area.spaces.active:
        return True
    
    rv3d = area.spaces.active.region_3d
    current_view_matrix = rv3d.view_matrix.copy()
    
    if _DBG["last_view_matrix"] is None:
        _DBG["last_view_matrix"] = current_view_matrix
        return True
    
    # Check if view matrix has changed significantly
    # Calculate the difference matrix and sum the absolute values of all elements
    diff_matrix = current_view_matrix - _DBG["last_view_matrix"]
    view_diff = sum(abs(val) for row in diff_matrix for val in row)
    _DBG["last_view_matrix"] = current_view_matrix
    
    # More sensitive threshold for better responsiveness during quick zoom
    return view_diff > 0.001


# -----------------------------
# Property update callbacks
# -----------------------------

def wltp_enabled_update(self, context):
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
        "WLTP Debug (Cursor-based)",
        f"PPU (px/BU):  {(_DBG['last_ppu'] if _DBG['last_ppu'] is not None else 'None')}",
        f"Desired pxR:  {(_DBG['last_radius_px'] if _DBG['last_radius_px'] is not None else 'None')}",
        f"Applied pxR:  {(_DBG['last_brush_px'] if _DBG['last_brush_px'] is not None else 'None')}",
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
# Cursor snapping operator
# -----------------------------

class PAINT_OT_cursor_on_lmb(bpy.types.Operator):
    """Snap 3-D cursor to surface on LMB (Texture Paint)"""
    bl_idname  = "paint.cursor_on_lmb"
    bl_label   = "3D Cursor on LMB"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        # Only run in Texture Paint mode
        if context.mode != 'PAINT_TEXTURE':
            return {'PASS_THROUGH'}

        # Only run in 3D viewport (not in 2D image editor)
        if context.area.type != 'VIEW_3D':
            return {'PASS_THROUGH'}

        # Do exactly what Shift-RMB does
        bpy.ops.view3d.cursor3d('INVOKE_DEFAULT')
        return {'PASS_THROUGH'}


# -----------------------------
# Modal updater
# -----------------------------

class WLTP_OT_Update(Operator):
    """Modal timer that recomputes brush pixel size to match a world diameter using 3D cursor as reference."""
    bl_idname = "wltp.update"
    bl_label = "World-Locked Texture Brush Updater"
    _timer = None
    f_adjust_active = False
    _last_zoom_time = 0.0

    def _update_world_diameter_from_brush(self, context):
        """Convert the current pixel brush size to a world-space diameter and store it."""
        area, region = get_3d_view_area_region(context)
        if not (area and region):
            return

        ppu = pixels_per_world_unit_at_cursor(context, area, region)
        radius_px = get_current_brush_size(context)

        if ppu and ppu > 0.0 and radius_px is not None:
            radius_bu = float(radius_px) / float(ppu)
            _STATE["world_diameter_bu"] = max(0.0001, radius_bu * 2.0)

            # Sync overlay immediately
            _DBG.update({
                "active": context.scene.wltp_dbg.enable_overlay,
                "last_ppu": round(ppu, 3),
                "last_radius_px": int(round(radius_bu * ppu)),
                "last_brush_px": radius_px,
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
            return {'PASS_THROUGH'}

        # Handle F-key brush size adjustment
        if event.type == 'F' and event.value == 'PRESS':
            self.f_adjust_active = True
            return {'PASS_THROUGH'}
        
        # On F-release or confirm/cancel of the F-adjust operator
        is_release_f = event.type == 'F' and event.value == 'RELEASE'
        is_confirm_adjust = self.f_adjust_active and (
            (event.type in {'LEFTMOUSE', 'RIGHTMOUSE'} and event.value in {'PRESS', 'RELEASE'}) or
            (event.type in {'RET', 'SPACE', 'ESC'} and event.value == 'PRESS')
        )
        
        if is_release_f or is_confirm_adjust:
            if self.f_adjust_active:
                self._update_world_diameter_from_brush(context)
            self.f_adjust_active = False
            return {'PASS_THROUGH'}

        # Track zoom events for more responsive updates
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            self._last_zoom_time = time.time()
            
        # Check if we're actively zooming
        is_zooming = (time.time() - self._last_zoom_time) < 0.5
            
        # Update on timer events and any viewport interaction
        # Force updates during active zooming or on any viewport interaction
        if event.type == 'TIMER' or event.type in {'MOUSEMOVE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'MIDDLEMOUSE', 'TRACKPADPAN'} or is_zooming:
            area, region = get_3d_view_area_region(context)
            if not (area and region):
                dbg_print("No VIEW_3D region found.")
                return {'PASS_THROUGH'}

            # Check if view has changed significantly (for quick zoom detection)
            view_changed = has_view_changed_significantly(context, area)
            
            # Force update on significant view changes, timer events, or active zooming
            should_update = view_changed or event.type == 'TIMER' or is_zooming

            # Compute pixels per world unit at cursor location
            ppu = pixels_per_world_unit_at_cursor(context, area, region)
            if ppu is None or ppu <= 0.0:
                dbg_print("pixels_per_world_unit_at_cursor failed")
                return {'PASS_THROUGH'}

            desired_radius_bu = 0.5 * _STATE["world_diameter_bu"]
            desired_radius_px = desired_radius_bu * ppu

            applied = get_current_brush_size(context)

            # Only update world diameter if the user manually changed the brush size
            # and we're not currently in F-adjust mode
            if (not self.f_adjust_active and 
                _DBG["last_brush_px"] is not None and 
                applied != _DBG["last_brush_px"] and
                abs(applied - desired_radius_px) > 1.0):  # Allow small rounding differences
                self._update_world_diameter_from_brush(context)
            # Apply brush size unless user is actively adjusting with F
            # Force update when view changes significantly or during active zooming
            elif not self.f_adjust_active and (view_changed or is_zooming or abs(applied - desired_radius_px) > 1.0):
                set_brush_pixel_radius(context, desired_radius_px)

            _DBG.update({
                "active": dbg.enable_overlay,
                "last_ppu": round(ppu, 3),
                "last_radius_px": int(round(desired_radius_px)),
                "last_brush_px": applied,
            })

            # Only print debug info when view changes or on timer to reduce spam
            if view_changed or event.type == 'TIMER':
                dbg_print(
                    f"PPU={_DBG['last_ppu']} px/BU | desired_pxR={_DBG['last_radius_px']} | "
                    f"applied={applied} | view_changed={view_changed}"
                )

            ensure_draw_handler(dbg.enable_overlay)
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
            self._last_zoom_time = time.time()
            _DBG["active"] = dbg.enable_overlay
            ensure_draw_handler(dbg.enable_overlay)
            dbg_print("WLTP modal started (cursor-based).")
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
    if context.mode not in {'PAINT_TEXTURE', 'TEXTURE_PAINT'}:
        return
    props = getattr(context.scene, 'wltp', None)
    dbg = getattr(context.scene, 'wltp_dbg', None)
    if not props or not dbg:
        return
    br = get_texpaint_brush(context)
    if not br:
        return
    layout = self.layout
    row = layout.row(align=True)
    row.prop(props, "enabled", text="Scene Radius", icon='WORLD', toggle=True)
    row.prop(dbg, "enable_overlay", text="", icon='CONSOLE', toggle=True)

# -----------------------------
# Registration
# -----------------------------

classes = (
    WLTP_Props,
    WLTP_DebugProps,
    WLTP_OT_Update,
    PAINT_OT_cursor_on_lmb,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.wltp = PointerProperty(type=WLTP_Props)
    bpy.types.Scene.wltp_dbg = PointerProperty(type=WLTP_DebugProps)
    ensure_draw_handler(False)
    
    # Register keymap for cursor snapping
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name="Image Paint", space_type='EMPTY')
        kmi = km.keymap_items.new(
            PAINT_OT_cursor_on_lmb.bl_idname,
            'LEFTMOUSE', 'PRESS', head=True)
        _KEYMAPS.append((km, kmi))
    
    try:
        bpy.types.VIEW3D_PT_tools_brush_settings.append(draw_wltp_toggle_under_radius)
    except Exception:
        pass

def unregister():
    ensure_draw_handler(False)
    
    # Unregister keymap for cursor snapping
    for km, kmi in _KEYMAPS:
        km.keymap_items.remove(kmi)
    _KEYMAPS.clear()
    
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    del bpy.types.Scene.wltp_dbg
    del bpy.types.Scene.wltp
    print("[WLTP] Unregistered.")
    try:
        bpy.types.VIEW3D_PT_tools_brush_settings.remove(draw_wltp_toggle_under_radius)
    except Exception:
        pass

if __name__ == "__main__":
    register()
