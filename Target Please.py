bl_info = {
    "name": "Target, Please! (Smart Pivot)",
    "author": "Ilyasse L",
    "version": (1, 3, 0),
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

# ---------------------------------------------------------------------
# Smart Pivot
# ---------------------------------------------------------------------
_TRANSFORM_OPS = {
    'TRANSLATE': lambda: bpy.ops.transform.translate('INVOKE_DEFAULT'),
    'ROTATE':    lambda: bpy.ops.transform.rotate('INVOKE_DEFAULT'),
    'RESIZE':    lambda: bpy.ops.transform.resize('INVOKE_DEFAULT'),
}
_SPY_KEYS = (('G', 'TRANSLATE'), ('R', 'ROTATE'), ('S', 'RESIZE'))


def _active_smart_pivot_empty(context):
    obj = getattr(context, "active_object", None)
    return obj if (obj and obj.type == 'EMPTY' and obj.get("is_smart_pivot_target")) else None


def _smart_pivot_view_layers_update(scene):
    for vl in getattr(scene, "view_layers", []):
        try:
            vl.update()
        except Exception:
            pass


def _object_scenes(obj):
    try:
        scenes = list(obj.users_scene)
    except Exception:
        scenes = []
    if scenes:
        return scenes
    scene = getattr(bpy.context, "scene", None)
    return [scene] if scene is not None else []


def _shared_scene_for_objects(*objs):
    common = None
    scene_by_id = {}
    for obj in objs:
        if obj is None:
            return None
        scenes = _object_scenes(obj)
        if not scenes:
            return None
        ids = {s.as_pointer() for s in scenes}
        for scene in scenes:
            scene_by_id[scene.as_pointer()] = scene
        common = ids if common is None else (common & ids)
        if not common:
            return None
    return scene_by_id[next(iter(common))] if common else None


def _linked_smart_pivot_camera(empty):
    """Camera bound to this pivot from the empty's stored property."""
    obj = bpy.data.objects.get(empty.get("smart_pivot_camera", ""))
    return obj if (obj and obj.type == 'CAMERA') else None


def _has_live_target_childof(obj, empty):
    return any(c.type == 'CHILD_OF' and c.name.startswith('LiveTarget_ChildOf') and c.target == empty for c in obj.constraints)


def _find_live_target_track_to_index(obj):
    return next((i for i, c in enumerate(obj.constraints) if c.type == 'TRACK_TO' and c.name.startswith('LiveTarget_TrackTo')), None)


def _apply_live_target_childof(scene, obj, empty):
    """
    Bake the constraint stack (Child Of + Track To) into matrix_world, then remove LiveTarget Child Of.
    Same idea as Blender's Apply Constraint — transform stays; Child Of is gone.
    """
    ctx = bpy.context
    to_remove = [
        c for c in list(obj.constraints)
        if c.type == 'CHILD_OF' and c.name.startswith('LiveTarget_ChildOf') and c.target == empty
    ]
    if not to_remove:
        return
    _smart_pivot_view_layers_update(scene)
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
    try:
        child_of.set_inverse_pending = True
        _smart_pivot_view_layers_update(scene)
    except Exception:
        try:
            obj.constraints.remove(child_of)
        except Exception:
            pass


class VIEW3D_OT_smart_pivot_transform_spy(bpy.types.Operator):
    """Wraps G/R/S to react to confirm/cancel and keep Child Of lifecycle deterministic."""
    bl_idname = "view3d.smart_pivot_transform_spy"
    bl_label = "Smart Pivot Transform Spy"
    bl_options = {'MODAL_PRIORITY'}

    transform_type: bpy.props.EnumProperty(
        items=[
            ('TRANSLATE', "Translate", ""),
            ('ROTATE',    "Rotate",    ""),
            ('RESIZE',    "Scale",     ""),
        ],
        default='TRANSLATE',
    )

    def _invoke_native_transform(self):
        return _TRANSFORM_OPS[self.transform_type]()

    def invoke(self, context, event):
        empty = _active_smart_pivot_empty(context)
        cam = _linked_smart_pivot_camera(empty) if empty else None
        scene = _shared_scene_for_objects(empty, cam) if cam else None
        self._ending = False
        self._empty_name = empty.name if empty else ""
        self._camera_name = cam.name if cam else ""

        # Spy only for active smart-pivot empties with a valid linked camera.
        # Otherwise stay fully transparent and let default G/R/S keymaps run.
        if empty is None or cam is None or scene is None:
            return {'PASS_THROUGH'}

        # Apply expected pre-transform state.
        if self.transform_type == 'ROTATE':
            if not _has_live_target_childof(cam, empty):
                _recreate_live_target_childof(scene, cam, empty)
        else:
            if _has_live_target_childof(cam, empty):
                _apply_live_target_childof(scene, cam, empty)

        result = self._invoke_native_transform()
        if 'RUNNING_MODAL' not in result and 'FINISHED' not in result:
            # Immediate cancel/failure: ensure Child Of is not left behind.
            if _has_live_target_childof(cam, empty):
                _apply_live_target_childof(scene, cam, empty)
            return {'CANCELLED'}

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if self._ending:
            empty = bpy.data.objects.get(self._empty_name)
            cam = bpy.data.objects.get(self._camera_name)
            scene = _shared_scene_for_objects(empty, cam) if empty and cam else None
            if empty and cam and scene and _has_live_target_childof(cam, empty):
                _apply_live_target_childof(scene, cam, empty)
            return {'FINISHED'}

        # Detect both confirm and cancel keys while allowing transform to consume them.
        if event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER', 'RIGHTMOUSE', 'ESC'} and event.value in {'PRESS', 'CLICK'}:
            self._ending = True
            return {'PASS_THROUGH'}

        return {'PASS_THROUGH'}


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

        def _add_spy_keys(keymap):
            for key, ttype in _SPY_KEYS:
                kmi = keymap.keymap_items.new(VIEW3D_OT_smart_pivot_transform_spy.bl_idname, type=key, value='PRESS')
                kmi.properties.transform_type = ttype
                addon_keymaps.append((keymap, kmi))

        _add_spy_keys(km)
        _add_spy_keys(wm.keyconfigs.addon.keymaps.new(name='Object Mode', space_type='EMPTY'))

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

def _cleanup_live_target_object(obj):
    for c in list(obj.constraints):
        if c.type == 'TRACK_TO' and c.name.startswith('LiveTarget_TrackTo'):
            obj.constraints.remove(c)
        elif c.type == 'CHILD_OF' and c.name.startswith('LiveTarget_ChildOf'):
            obj.constraints.remove(c)


def _cleanup_live_target_empty(empty):
    if empty is not None and empty.get("is_smart_pivot_target"):
        del empty["is_smart_pivot_target"]
    if empty is not None and "smart_pivot_camera" in empty:
        del empty["smart_pivot_camera"]


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
            _cleanup_live_target_object(obj)

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
        self.use_orbit = self.camera_orbit_pivot and not self.delete_empty_after
        if self.use_orbit:
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

            if self.use_orbit and obj.type == 'CAMERA' and "smart_pivot_camera" not in self.empty:
                self.empty["smart_pivot_camera"] = obj.name
                # LiveTarget_ChildOf is added only by the transform spy during rotate.

            constraint = obj.constraints.new(type='TRACK_TO')
            constraint.name = "LiveTarget_TrackTo"
            constraint.target = self.empty
            constraint.track_axis = self.track_axis
            constraint.up_axis = self.up_axis
            constraint.use_target_z = self.target_z
            self.constrained_objects.append((obj, constraint))

        context.view_layer.update()

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        # Update constraint settings in real-time
        for obj, constraint in self.constrained_objects:
            constraint.track_axis = self.track_axis
            constraint.up_axis = self.up_axis
            constraint.use_target_z = self.target_z
        def _cleanup_session():
            for obj, _constraint in self.constrained_objects:
                _cleanup_live_target_object(obj)
            _cleanup_live_target_empty(self.empty)
            bpy.data.objects.remove(self.empty, do_unlink=True)

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
                for obj, _constraint in self.constrained_objects:
                    eval_obj = obj.evaluated_get(depsgraph)
                    obj.matrix_world = eval_obj.matrix_world.copy()
                _cleanup_session()
                self.report({'INFO'}, "Target validated and applied (baked)")
            else:
                if self.use_orbit:
                    self.report({'INFO'}, "Target validated - Smart Pivot active")
                else:
                    self.report({'INFO'}, "Target validated")
            return {'FINISHED'}

        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            # Cancel cleanup
            _cleanup_session()
            self.report({'INFO'}, "Operation cancelled")
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

# ---------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------
addon_keymaps = []
_CLASSES = (
    TargetAddonPreferences,
    OBJECT_OT_live_set_target,
    VIEW3D_OT_smart_pivot_transform_spy,
)

def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    register_keymaps()

def unregister():
    unregister_keymaps()
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
