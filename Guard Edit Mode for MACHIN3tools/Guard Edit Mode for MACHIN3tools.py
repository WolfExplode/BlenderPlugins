bl_info = {
    "name": "Guard Edit Mode for MACHIN3tools (debug)",
    "author": "ChatGPT",
    "version": (1, 2),
    "blender": (2, 80, 0),
    "description": "Pre-check vertex count before allowing Edit Mode. Patches MACHIN3tools and object.mode_set. Adds debug output.",
    "category": "3D View",
}

import bpy
import time
import traceback

DEFAULT_THRESHOLD = 1_000_000
_original_methods = {}

# --- utilities --------------------------------------------------------------
def _dbg_enabled():
    try:
        prefs = bpy.context.preferences.addons[__name__].preferences
        return getattr(prefs, "debug", True)
    except Exception:
        return True

def _dbg(msg):
    if _dbg_enabled():
        t = time.strftime("%H:%M:%S")
        print(f"[GEM DEBUG] {t} - {msg}")

def _get_threshold():
    try:
        prefs = bpy.context.preferences.addons[__name__].preferences
        return prefs.threshold
    except Exception:
        return DEFAULT_THRESHOLD

def _active_mesh_vert_count(context):
    obj = getattr(context.view_layer, "objects", None) and context.view_layer.objects.active
    if obj and obj.type == 'MESH':
        try:
            return len(obj.data.vertices)
        except Exception:
            return 0
    return 0

def _warn_popup(objname, verts, threshold):
    def draw(self, context):
        self.layout.label(text=f"'{objname}' has {verts:,} verts — limit is {threshold:,}.")
        self.layout.label(text="Edit Mode blocked to avoid heavy mesh conversion.")
    try:
        bpy.context.window_manager.popup_menu(draw, title="Edit Mode Guard", icon='ERROR')
    except Exception:
        # If context/window unavailable, fallback to report to console
        _dbg("Could not show popup (no window context).")

def _blid_to_class(blid):
    # convert "machin3.mesh_mode" -> "MACHIN3_OT_mesh_mode"
    try:
        group, op = blid.split('.', 1)
        clsname = f"{group.upper()}_OT_{op}"
        cls = getattr(bpy.types, clsname, None)
        return cls
    except Exception:
        return None

# --- guard factories -------------------------------------------------------
def make_execute_guard(blid, orig):
    def wrapper(self, context, *args, **kwargs):
        try:
            obj = context.view_layer.objects.active if context and getattr(context, "view_layer", None) else None
            verts = _active_mesh_vert_count(context)
            thr = _get_threshold()
            _dbg(f"CALL {blid}.execute | ctx.mode={getattr(context,'mode',None)} active={(obj.name if obj else None)} verts={verts:,} thr={thr:,}")
            # General rule: if currently not in edit (so operator is likely entering edit), block
            entering_edit = not (getattr(context, "mode", "").startswith("EDIT"))
            # However, for object.mode_set we prefer checking target mode — handled elsewhere.
            if blid in ("machin3.edit_mode", "machin3.mesh_mode"):
                if entering_edit and obj and obj.type == 'MESH' and verts > thr:
                    _dbg(f"BLOCK {blid}.execute -> CANCELLED (too many verts)")
                    _warn_popup(obj.name, verts, thr)
                    return {'CANCELLED'}
            # default: call original
            res = orig(self, context, *args, **kwargs)
            _dbg(f"ALLOWED {blid}.execute -> {res}")
            return res
        except Exception:
            _dbg(f"ERROR in guard {blid}.execute:\n{traceback.format_exc()}")
            # On error, fall back to calling original to avoid blocking mistakenly
            try:
                return orig(self, context, *args, **kwargs)
            except Exception:
                return {'CANCELLED'}
    return wrapper

def make_invoke_guard(blid, orig):
    def wrapper(self, context, event, *args, **kwargs):
        try:
            obj = context.view_layer.objects.active if context and getattr(context, "view_layer", None) else None
            verts = _active_mesh_vert_count(context)
            thr = _get_threshold()
            _dbg(f"CALL {blid}.invoke | ctx.mode={getattr(context,'mode',None)} active={(obj.name if obj else None)} verts={verts:,} thr={thr:,}")
            # If operator is one that will call mode_set to go into EDIT, block early
            # For MACHIN3's mesh_mode.invoke: it calls bpy.ops.object.mode_set(mode='EDIT') when starting from OBJECT or certain paint/sculpt modes.
            if blid == "machin3.mesh_mode":
                will_attempt_edit = getattr(context, "mode", "") not in ("EDIT_MESH", "EDIT")
                if will_attempt_edit and obj and obj.type == 'MESH' and verts > thr:
                    _dbg(f"BLOCK {blid}.invoke -> CANCELLED (too many verts)")
                    _warn_popup(obj.name, verts, thr)
                    return {'CANCELLED'}
            # default: call original
            res = orig(self, context, event, *args, **kwargs)
            _dbg(f"ALLOWED {blid}.invoke -> {res}")
            return res
        except Exception:
            _dbg(f"ERROR in guard {blid}.invoke:\n{traceback.format_exc()}")
            try:
                return orig(self, context, event, *args, **kwargs)
            except Exception:
                return {'CANCELLED'}
    return wrapper

def make_object_mode_set_execute_guard(blid, orig):
    # object.mode_set specific guard: check target mode property on operator
    def wrapper(self, context, *args, **kwargs):
        try:
            tgt_mode = getattr(self, "mode", None) or kwargs.get("mode", None)
            obj = context.view_layer.objects.active if context and getattr(context, "view_layer", None) else None
            verts = _active_mesh_vert_count(context)
            thr = _get_threshold()
            _dbg(f"CALL {blid}.execute | target_mode={tgt_mode} ctx.mode={getattr(context,'mode',None)} active={(obj.name if obj else None)} verts={verts:,} thr={thr:,}")
            if tgt_mode and isinstance(tgt_mode, str) and tgt_mode.upper().startswith("EDIT"):
                if obj and obj.type == 'MESH' and verts > thr and not getattr(context, "mode", "").startswith("EDIT"):
                    _dbg(f"BLOCK {blid}.execute -> CANCELLED (target EDIT, too many verts)")
                    _warn_popup(obj.name, verts, thr)
                    return {'CANCELLED'}
            res = orig(self, context, *args, **kwargs)
            _dbg(f"ALLOWED {blid}.execute -> {res}")
            return res
        except Exception:
            _dbg(f"ERROR in guard {blid}.execute:\n{traceback.format_exc()}")
            try:
                return orig(self, context, *args, **kwargs)
            except Exception:
                return {'CANCELLED'}
    return wrapper

# --- Addon Preferences -----------------------------------------------------
class GEMPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    threshold: bpy.props.IntProperty(
        name="Vertex Threshold",
        default=DEFAULT_THRESHOLD,
        min=1,
        max=100_000_000,
        description="Maximum vertices allowed before blocking Edit Mode"
    )

    debug: bpy.props.BoolProperty(
        name="Enable debug logging",
        default=True,
        description="Print debug lines to the system console"
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Guard Edit Mode (MACHIN3tools)")
        layout.prop(self, "threshold")
        layout.prop(self, "debug")

# --- register / patch / restore -------------------------------------------
_ops_to_patch = [
    "machin3.edit_mode",
    "machin3.mesh_mode",
    "object.mode_set",
]

def _patch_ops():
    for blid in _ops_to_patch:
        cls = _blid_to_class(blid)
        if not cls:
            _dbg(f"Operator class for '{blid}' not found (skipping).")
            continue

        # patch execute
        if hasattr(cls, "execute"):
            orig = getattr(cls, "execute")
            key = f"{blid}.execute"
            if key not in _original_methods:
                if blid == "object.mode_set":
                    _original_methods[key] = orig
                    setattr(cls, "execute", make_object_mode_set_execute_guard(blid, orig))
                    _dbg(f"Patched {blid}.execute (object.mode_set special guard).")
                else:
                    _original_methods[key] = orig
                    setattr(cls, "execute", make_execute_guard(blid, orig))
                    _dbg(f"Patched {blid}.execute.")

        # patch invoke (needed for machin3.mesh_mode)
        if hasattr(cls, "invoke"):
            orig_inv = getattr(cls, "invoke")
            key_inv = f"{blid}.invoke"
            if key_inv not in _original_methods:
                _original_methods[key_inv] = orig_inv
                setattr(cls, "invoke", make_invoke_guard(blid, orig_inv))
                _dbg(f"Patched {blid}.invoke.")

def _restore_ops():
    for key, orig in list(_original_methods.items()):
        try:
            blid, method = key.rsplit(".", 1)
            cls = _blid_to_class(blid)
            if cls and hasattr(cls, method):
                setattr(cls, method, orig)
                _dbg(f"Restored {key}.")
            else:
                _dbg(f"Could not restore {key} (class/method missing).")
        except Exception:
            _dbg(f"Error restoring {key}:\n{traceback.format_exc()}")
        finally:
            _original_methods.pop(key, None)

# --- registration ---------------------------------------------------------
classes = (GEMPreferences,)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    _dbg("Registering Guard Edit Mode addon.")
    _patch_ops()
    _dbg("Patching complete. Reproduce the issue and check system console for debug lines.")

def unregister():
    _dbg("Unregistering Guard Edit Mode addon.")
    _restore_ops()
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    _dbg("Unregistered.")

if __name__ == "__main__":
    register()
