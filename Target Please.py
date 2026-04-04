bl_info = {
    "name": "Target, Please! (Smart Pivot)",
    "author": "Ilyasse L",
    "version": (1, 1, 12),
    "blender": (4, 2, 0),
    "location": "3D View",
    "description": (
        "Creates tracking target with smart orbit pivot. "
        "Child Of is added only while rotating the pivot empty (camera orbits); "
        "it is removed when rotate ends and when move starts if present. Track To handles aiming when not rotating."
    ),
    "category": "Object",
}

import bpy
from mathutils import Vector
from bpy_extras import view3d_utils

# Timer cannot read prefs; synced from preferences on change, invoke, and register.
_smart_pivot_extra_translate_ops_cache = ""

# ---------------------------------------------------------------------
# Smart Pivot
# ---------------------------------------------------------------------
_TRANSLATE_OPERATOR_IDS = frozenset({
    'transform.translate',
    'TRANSFORM_OT_translate',
})

_ROTATE_OPERATOR_IDS = frozenset({
    'transform.rotate',
    'TRANSFORM_OT_rotate',
})

_smart_pivot_prev_translate_ptrs = None
_smart_pivot_prev_rotate_ptrs = None


def _sync_smart_pivot_translate_ops_cache(prefs):
    global _smart_pivot_extra_translate_ops_cache
    _smart_pivot_extra_translate_ops_cache = getattr(prefs, "smart_pivot_extra_translate_ops", "") or ""


def _translate_operator_ids_cached():
    ids = set(_TRANSLATE_OPERATOR_IDS)
    for part in _smart_pivot_extra_translate_ops_cache.split(","):
        p = part.strip()
        if p:
            ids.add(p)
    return ids


def _window_has_modal_in_set(window, operator_ids):
    try:
        modops = window.modal_operators
    except AttributeError:
        return False
    for op in modops:
        if getattr(op, "bl_idname", None) in operator_ids:
            return True
    return False


def _smart_pivot_empties_with_modal_ops(operator_ids):
    """Smart-pivot empties whose active object is under a matching modal in any window."""
    found = []
    if not operator_ids:
        return frozenset()
    try:
        wm = bpy.context.window_manager
    except Exception:
        return frozenset()
    if wm:
        for window in wm.windows:
            if not _window_has_modal_in_set(window, operator_ids):
                continue
            vl = getattr(window, "view_layer", None)
            if vl is None:
                continue
            try:
                ao = vl.objects.active
            except Exception:
                continue
            if ao and ao.get("is_smart_pivot_target"):
                found.append(ao.as_pointer())
    try:
        op = bpy.context.active_operator
    except Exception:
        op = None
    if op is not None and op.bl_idname in operator_ids:
        try:
            ao = bpy.context.active_object
        except Exception:
            ao = None
        if ao and ao.get("is_smart_pivot_target"):
            found.append(ao.as_pointer())
    return frozenset(found)


def _scene_object_by_pointer(scene, ptr):
    for o in scene.objects:
        if o.as_pointer() == ptr:
            return o
    return None


def _smart_pivot_view_layers_update(scene):
    for vl in getattr(scene, "view_layers", []):
        try:
            vl.update()
        except Exception:
            pass


def _smart_pivot_pick_window_for_scene(scene):
    try:
        wm = bpy.context.window_manager
        if not wm:
            return None
        for w in wm.windows:
            if getattr(w, "scene", None) == scene:
                return w
    except Exception:
        pass
    try:
        w = bpy.context.window
        if w and getattr(w, "scene", None) == scene:
            return w
    except Exception:
        pass
    try:
        wm = bpy.context.window_manager
        if wm and wm.windows:
            return wm.windows[0]
    except Exception:
        pass
    return None


def _linked_smart_pivot_cameras(scene, empty):
    """Cameras bound to this pivot (smart_pivot_target); Child Of may be absent between modals."""
    out = []
    for obj in scene.objects:
        if obj.type == 'CAMERA' and obj.get("smart_pivot_target") == empty.name:
            out.append(obj)
    return out


def _smart_pivot_linked_camera_selected_in_scene(scene, cams):
    """
    True if any linked camera is selected in a view layer for this scene.
    Used to avoid baking/removing constraints while transform.translate / rotate / scale
    is modal on the pivot empty *and* the camera is also being transformed — that can crash Blender.
    """
    if not cams:
        return False
    cam_set = frozenset(cams)
    try:
        wm = bpy.context.window_manager
    except Exception:
        return False
    if not wm:
        return False
    for w in wm.windows:
        if getattr(w, "scene", None) != scene:
            continue
        vl = getattr(w, "view_layer", None)
        if vl is None:
            continue
        for o in vl.objects:
            if o in cam_set and o.select_get():
                return True
    return False


def _find_live_target_track_to_index(obj):
    for i, c in enumerate(obj.constraints):
        if c.type == 'TRACK_TO' and c.name.startswith('LiveTarget_TrackTo'):
            return i
    return None


def _apply_live_target_childof(scene, obj, empty):
    """
    Bake the constraint stack (Child Of + Track To) into matrix_world, then remove LiveTarget Child Of.
    Same idea as Blender's Apply Constraint — transform stays; Child Of is gone.
    """
    ctx = bpy.context
    to_remove = []
    for c in list(obj.constraints):
        if c.type == 'CHILD_OF' and c.name.startswith('LiveTarget_ChildOf') and c.target == empty:
            to_remove.append(c)
    if not to_remove:
        return
    _smart_pivot_view_layers_update(scene)
    win = _smart_pivot_pick_window_for_scene(scene)
    dg = None
    try:
        if win is not None:
            vl = getattr(win, "view_layer", None)
            with ctx.temp_override(window=win, screen=win.screen, scene=scene, view_layer=vl):
                dg = ctx.evaluated_depsgraph_get()
        else:
            with ctx.temp_override(scene=scene):
                dg = ctx.evaluated_depsgraph_get()
    except Exception:
        dg = None
    if dg is None:
        try:
            dg = ctx.evaluated_depsgraph_get()
        except Exception:
            dg = None
    if dg is not None:
        try:
            ev = obj.evaluated_get(dg)
            obj.matrix_world = ev.matrix_world.copy()
        except Exception:
            pass
    for c in to_remove:
        try:
            obj.constraints.remove(c)
        except Exception:
            pass


def _recreate_live_target_childof(scene, obj, empty):
    """Bake off any existing LiveTarget Child Of, then re-add above Track To; one Set Inverse."""
    ctx = bpy.context
    _apply_live_target_childof(scene, obj, empty)
    track_idx = _find_live_target_track_to_index(obj)
    child_of = obj.constraints.new(type='CHILD_OF')
    child_of.name = "LiveTarget_ChildOf"
    child_of.target = empty
    for axis in 'xyz':
        setattr(child_of, f'use_location_{axis}', True)
        setattr(child_of, f'use_rotation_{axis}', True)
        setattr(child_of, f'use_scale_{axis}', False)
    co_idx = len(obj.constraints) - 1
    if track_idx is not None and co_idx != track_idx:
        try:
            obj.constraints.move(co_idx, track_idx)
        except Exception:
            pass
    _smart_pivot_view_layers_update(scene)
    win = _smart_pivot_pick_window_for_scene(scene)
    try:
        childof_set_inverse(ctx, obj, child_of.name, scene=scene, window=win)
    except Exception:
        pass


def _smart_pivot_resolve_scene():
    try:
        s = bpy.context.scene
        if s is not None:
            return s
    except Exception:
        pass
    try:
        wm = bpy.context.window_manager
        if wm and wm.windows:
            s = wm.windows[0].scene
            if s is not None:
                return s
    except Exception:
        pass
    return None


def smart_pivot_update():
    """
    Move (G): bake + remove Child Of when move starts (empty moves alone; camera does not follow via Child Of).
    Rotate (R): recreate + Set Inverse when rotate modal starts; bake + remove when it ends. Resize does not use Child Of.
    """
    global _smart_pivot_prev_translate_ptrs, _smart_pivot_prev_rotate_ptrs

    scene = _smart_pivot_resolve_scene()
    if scene is None:
        return

    curr_t = _smart_pivot_empties_with_modal_ops(_translate_operator_ids_cached())
    curr_rot = _smart_pivot_empties_with_modal_ops(_ROTATE_OPERATOR_IDS)

    prev_t = _smart_pivot_prev_translate_ptrs
    prev_rot = _smart_pivot_prev_rotate_ptrs

    def _for_ptrs(ptr_set):
        for ptr in ptr_set:
            empty = _scene_object_by_pointer(scene, ptr)
            if empty is None or not empty.get("is_smart_pivot_target"):
                continue
            cams = _linked_smart_pivot_cameras(scene, empty)
            if not cams:
                continue
            yield empty, cams

    if prev_t is not None:
        for empty, cams in _for_ptrs(curr_t - prev_t):
            if _smart_pivot_linked_camera_selected_in_scene(scene, cams):
                continue
            for obj in cams:
                _apply_live_target_childof(scene, obj, empty)

    if prev_rot is not None:
        for empty, cams in _for_ptrs(curr_rot - prev_rot):
            if _smart_pivot_linked_camera_selected_in_scene(scene, cams):
                continue
            for obj in cams:
                _recreate_live_target_childof(scene, obj, empty)
        for empty, cams in _for_ptrs(prev_rot - curr_rot):
            for obj in cams:
                _apply_live_target_childof(scene, obj, empty)

    _smart_pivot_prev_translate_ptrs = curr_t
    _smart_pivot_prev_rotate_ptrs = curr_rot


def smart_pivot_timer():
    try:
        smart_pivot_update()
    except Exception:
        pass
    return 0.05


# ---------------------------------------------------------------------
# Keymaps & purge
# ---------------------------------------------------------------------
def unregister_keymaps():
    wm = bpy.context.window_manager
    if wm.keyconfigs.addon:
        for km, kmi in addon_keymaps:
            try:
                km.keymap_items.remove(kmi)
            except Exception:
                pass
        addon_keymaps.clear()

def register_keymaps():
    wm = bpy.context.window_manager
    if wm.keyconfigs.addon:
        prefs = bpy.context.preferences.addons[__name__].preferences
        km = wm.keyconfigs.addon.keymaps.new(name='3D View', space_type='VIEW_3D')
        kmi1 = km.keymap_items.new(
            OBJECT_OT_live_set_target.bl_idname, 
            type=prefs.key_direct, 
            value='PRESS', 
            shift=prefs.key_direct_shift, 
            ctrl=prefs.key_direct_ctrl
        )
        kmi2 = km.keymap_items.new(
            OBJECT_OT_live_set_target.bl_idname, 
            type=prefs.key_dialog, 
            value='PRESS', 
            shift=prefs.key_dialog_shift, 
            ctrl=prefs.key_dialog_ctrl
        )
        addon_keymaps.append((km, kmi1))
        addon_keymaps.append((km, kmi2))

def update_hotkeys(self, context):
    unregister_keymaps()
    register_keymaps()


def purge_empty_if_no_constraint_target(empty_obj):
    if not empty_obj or empty_obj.type != 'EMPTY':
        return
    for o in bpy.data.objects:
        for con in o.constraints:
            if getattr(con, 'target', None) == empty_obj:
                return
    bpy.data.objects.remove(empty_obj, do_unlink=True)

def purge_orphan_live_target_empties_for_base_name(base_name):
    prefix = f"{base_name}_Target"
    for o in list(bpy.data.objects):
        if o.type != 'EMPTY':
            continue
        if o.name != prefix and not o.name.startswith(prefix + "."):
            continue
        purge_empty_if_no_constraint_target(o)

def _first_view3d_area_region(screen):
    if not screen:
        return None, None
    for area in screen.areas:
        if area.type != 'VIEW_3D':
            continue
        for region in area.regions:
            if region.type == 'WINDOW':
                return area, region
        return area, None
    return None, None


def childof_set_inverse(context, obj, constraint_name, *, scene=None, window=None):
    """Set Child Of inverse using operator. Timer/restricted context: pass scene + window."""
    win = window or getattr(context, "window", None)
    if win is None and scene is not None:
        win = _smart_pivot_pick_window_for_scene(scene)
    if not win:
        return
    scr = win.screen
    area, region = _first_view3d_area_region(scr)
    if area is None and getattr(context, "area", None) and context.area.type == 'VIEW_3D':
        area = context.area
        for r in area.regions:
            if r.type == 'WINDOW':
                region = r
                break
    override_kw = dict(
        window=win,
        screen=scr,
        active_object=obj,
        object=obj,
        selected_objects=[obj],
        selected_editable_objects=[obj],
    )
    if scene is not None:
        override_kw["scene"] = scene
    try:
        vl = getattr(win, "view_layer", None)
        if vl is not None:
            override_kw["view_layer"] = vl
    except Exception:
        pass
    if area is not None:
        override_kw["area"] = area
    if region is not None:
        override_kw["region"] = region
    with context.temp_override(**override_kw):
        try:
            bpy.ops.constraint.childof_set_inverse(constraint=constraint_name, owner='OBJECT')
        except Exception:
            pass

def _update_extra_translate_ops_cache(self, context):
    _sync_smart_pivot_translate_ops_cache(self)


# ---------------------------------------------------------------------
# Addon Preferences
# ---------------------------------------------------------------------
class TargetAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__
    
    key_direct: bpy.props.StringProperty(
         name="Key (Direct Execution)", default="T", update=update_hotkeys
    )
    key_direct_shift: bpy.props.BoolProperty(
         name="Shift", default=True, update=update_hotkeys
    )
    key_direct_ctrl: bpy.props.BoolProperty(
         name="Ctrl", default=False, update=update_hotkeys
    )
    
    key_dialog: bpy.props.StringProperty(
         name="Key (Dialog)", default="T", update=update_hotkeys
    )
    key_dialog_shift: bpy.props.BoolProperty(
         name="Shift", default=True, update=update_hotkeys
    )
    key_dialog_ctrl: bpy.props.BoolProperty(
         name="Ctrl", default=True, update=update_hotkeys
    )
    
    delete_empty_after: bpy.props.BoolProperty(
         name="Delete Empty After Validation",
         description="If enabled, the temporary Empty will be deleted and the final transformation applied",
         default=True
    )

    camera_orbit_pivot: bpy.props.BoolProperty(
         name="Camera Orbit Pivot",
         description="When keeping the target Empty: a Child Of is used only while rotating the Empty (orbit); translating the Empty uses Track To only.",
         default=False
    )

    smart_pivot_extra_translate_ops: bpy.props.StringProperty(
         name="Extra translate bl_idnames",
         description="Comma-separated operator bl_idnames to treat as move/grab if your tools do not use transform.translate.",
         default="",
         update=_update_extra_translate_ops_cache,
    )

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="Hotkey Settings (Direct Execution)")
        col = box.column(align=True)
        col.prop(self, "key_direct")
        col.prop(self, "key_direct_shift")
        col.prop(self, "key_direct_ctrl")
        
        box = layout.box()
        box.label(text="Hotkey Settings (Dialog)")
        col = box.column(align=True)
        col.prop(self, "key_dialog")
        col.prop(self, "key_dialog_shift")
        col.prop(self, "key_dialog_ctrl")
        
        box = layout.box()
        box.label(text="Operator Settings")
        box.prop(self, "delete_empty_after")
        box.prop(self, "camera_orbit_pivot")
        box.prop(self, "smart_pivot_extra_translate_ops")

# ---------------------------------------------------------------------
# Main Operator
# ---------------------------------------------------------------------
class OBJECT_OT_live_set_target(bpy.types.Operator):
    bl_idname = "object.live_set_target"
    bl_label = "Set Live Target"
    bl_options = {'UNDO'}

    track_axis: bpy.props.EnumProperty(
        name="Track Axis",
        items=[
            ('TRACK_X', "Track X", ""),
            ('TRACK_Y', "Track Y", ""),
            ('TRACK_Z', "Track Z", ""),
            ('TRACK_NEGATIVE_X', "Track -X", ""),
            ('TRACK_NEGATIVE_Y', "Track -Y", ""),
            ('TRACK_NEGATIVE_Z', "Track -Z", ""),
        ],
        default='TRACK_NEGATIVE_Z'
    )

    up_axis: bpy.props.EnumProperty(
        name="Up Axis",
        items=[
            ('UP_X', "Up X", ""),
            ('UP_Y', "Up Y", ""),
            ('UP_Z', "Up Z", ""),
        ],
        default='UP_Y'
    )
    
    target_z: bpy.props.BoolProperty(
        name="Target Z", default=False
    )
    
    delete_empty_after: bpy.props.BoolProperty(
        name="Delete Empty After Validation", default=True
    )

    camera_orbit_pivot: bpy.props.BoolProperty(
        name="Camera Orbit Pivot", default=False
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "track_axis")
        layout.prop(self, "up_axis")
        layout.prop(self, "target_z")
        layout.prop(self, "delete_empty_after")
        orbit_col = layout.column()
        orbit_col.enabled = not self.delete_empty_after
        orbit_col.prop(self, "camera_orbit_pivot")
        if self.delete_empty_after:
            orbit_col.label(text="(Requires keeping the Empty)", icon='INFO')

    def invoke(self, context, event):
        if context.area.type != 'VIEW_3D':
            self.report({'WARNING'}, "3D View not found, operation cancelled")
            return {'CANCELLED'}
        prefs = context.preferences.addons[__name__].preferences
        _sync_smart_pivot_translate_ops_cache(prefs)
        self.delete_empty_after = prefs.delete_empty_after
        self.camera_orbit_pivot = prefs.camera_orbit_pivot
        if event.ctrl:
            if not context.selected_objects:
                self.report({'WARNING'}, "Nothing selected. Operation cancelled.")
                return {'PASS_THROUGH'}
            return context.window_manager.invoke_props_dialog(self, width=300)
        else:
            return self.execute(context)

    def execute(self, context):
        if not context.selected_objects:
            self.report({'WARNING'}, "Nothing selected. Operation cancelled.")
            return {'PASS_THROUGH'}

        sel = context.selected_objects

        for obj in list(sel):
            for c in list(obj.constraints):
                if c.type == 'TRACK_TO' and c.name.startswith('LiveTarget_TrackTo'):
                    obj.constraints.remove(c)
                elif c.type == 'CHILD_OF' and c.name.startswith('LiveTarget_ChildOf'):
                    obj.constraints.remove(c)
            if obj.type == 'CAMERA' and "smart_pivot_target" in obj:
                del obj["smart_pivot_target"]

        # Create Empty
        if context.active_object and context.active_object in sel:
            base_name = context.active_object.name
        else:
            base_name = sel[0].name
        purge_orphan_live_target_empties_for_base_name(base_name)
        self.empty = bpy.data.objects.new(f"{base_name}_Target", None)
        self.empty.empty_display_size = 0.5
        self.empty.empty_display_type = 'PLAIN_AXES'
        
        # Mark as smart pivot if orbit mode enabled
        use_orbit = self.camera_orbit_pivot and not self.delete_empty_after
        if use_orbit:
            self.empty["is_smart_pivot_target"] = True
            
        context.collection.objects.link(self.empty)

        if context.active_object:
            self.ref_point = context.active_object.location.copy()
        else:
            self.ref_point = Vector((0, 0, 0))

        # Apply constraints
        self.constrained_objects = []
        for obj in context.selected_objects:
            if obj == self.empty:
                continue
                
            child_of = None
            if use_orbit and obj.type == 'CAMERA':
                obj["smart_pivot_target"] = self.empty.name
                # LiveTarget_ChildOf is added only when rotating the pivot empty (smart_pivot_update).

            constraint = obj.constraints.new(type='TRACK_TO')
            constraint.name = "LiveTarget_TrackTo"
            constraint.target = self.empty
            constraint.track_axis = self.track_axis
            constraint.up_axis = self.up_axis
            constraint.use_target_z = self.target_z
            self.constrained_objects.append((obj, constraint, child_of))

        context.view_layer.update()

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        # Update constraint settings in real-time
        for obj, constraint, _child_of in self.constrained_objects:
            constraint.track_axis = self.track_axis
            constraint.up_axis = self.up_axis
            constraint.use_target_z = self.target_z

        if event.type == 'MOUSEMOVE':
            region = context.region
            rv3d = context.region_data
            coord = (event.mouse_region_x, event.mouse_region_y)
            view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
            ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
            result, location, *_ = context.scene.ray_cast(
                context.view_layer.depsgraph, ray_origin, view_vector)
            if result:
                self.empty.location = location
            else:
                self.empty.location = view3d_utils.region_2d_to_location_3d(region, rv3d, coord, self.ref_point)
            return {'RUNNING_MODAL'}

        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            prefs = context.preferences.addons[__name__].preferences
            prefs.delete_empty_after = self.delete_empty_after
            prefs.camera_orbit_pivot = self.camera_orbit_pivot

            if self.delete_empty_after:
                # Bake and cleanup
                depsgraph = context.evaluated_depsgraph_get()
                for obj, constraint, child_of in self.constrained_objects:
                    eval_obj = obj.evaluated_get(depsgraph)
                    obj.matrix_world = eval_obj.matrix_world.copy()
                    try:
                        obj.constraints.remove(constraint)
                    except:
                        pass
                    if child_of is not None:
                        try:
                            obj.constraints.remove(child_of)
                        except:
                            pass
                    if obj.type == 'CAMERA' and "smart_pivot_target" in obj:
                        del obj["smart_pivot_target"]

                if self.empty.get("is_smart_pivot_target"):
                    del self.empty["is_smart_pivot_target"]
                    
                bpy.data.objects.remove(self.empty, do_unlink=True)
                self.report({'INFO'}, "Target validated and applied (baked)")
            else:
                self.report({'INFO'}, "Target validated - Smart Pivot active")
            return {'FINISHED'}

        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            # Cancel cleanup
            for obj, constraint, child_of in self.constrained_objects:
                try:
                    obj.constraints.remove(constraint)
                except:
                    pass
                if child_of is not None:
                    try:
                        obj.constraints.remove(child_of)
                    except:
                        pass
                if obj.type == 'CAMERA' and "smart_pivot_target" in obj:
                    del obj["smart_pivot_target"]

            bpy.data.objects.remove(self.empty, do_unlink=True)
            self.report({'INFO'}, "Operation cancelled")
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

# ---------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------
addon_keymaps = []

def register():
    bpy.utils.register_class(TargetAddonPreferences)
    bpy.utils.register_class(OBJECT_OT_live_set_target)
    register_keymaps()
    try:
        _sync_smart_pivot_translate_ops_cache(bpy.context.preferences.addons[__name__].preferences)
    except Exception:
        pass

    if not bpy.app.timers.is_registered(smart_pivot_timer):
        bpy.app.timers.register(smart_pivot_timer, persistent=True)

def unregister():
    global _smart_pivot_prev_translate_ptrs, _smart_pivot_prev_rotate_ptrs
    _smart_pivot_prev_translate_ptrs = None
    _smart_pivot_prev_rotate_ptrs = None
    if bpy.app.timers.is_registered(smart_pivot_timer):
        bpy.app.timers.unregister(smart_pivot_timer)

    unregister_keymaps()
    bpy.utils.unregister_class(OBJECT_OT_live_set_target)
    bpy.utils.unregister_class(TargetAddonPreferences)

if __name__ == "__main__":
    register()