bl_info = {
    "name": "Target, Please!",
    "author": "Ilyasse Lm, WXP",
    "version": (1, 3, 1),
    "blender": (4, 2, 0),
    "location": "3D View",
    "description": (
        "Creates tracking target with smart orbit pivot. "
        "Child Of is added only while rotating the pivot empty (camera/light orbits); "
        "it is removed when rotate ends and when move starts if present. Track To handles aiming when not rotating."
    ),
    "category": "Object",
}

import bpy
import json
from mathutils import Vector
from bpy_extras import view3d_utils
from bpy.app.handlers import persistent

# ---------------------------------------------------------------------
# Smart Pivot
# ---------------------------------------------------------------------
_TRANSFORM_OPS = {
    'TRANSLATE': lambda: bpy.ops.transform.translate('INVOKE_DEFAULT'),
    'ROTATE':    lambda: bpy.ops.transform.rotate('INVOKE_DEFAULT'),
    'RESIZE':    lambda: bpy.ops.transform.resize('INVOKE_DEFAULT'),
}
_SPY_KEYS = (('G', 'TRANSLATE'), ('R', 'ROTATE'), ('S', 'RESIZE'))
_DZ_KEYS = (
    "camera", "base_scale", "base_camera_world_pos", "base_lens",
    "base_dist", "local_z_world", "lens_min", "lens_max",
)


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


def _linked_smart_pivot_orbit_object(empty):
    objs = _linked_smart_pivot_orbit_objects(empty)
    return objs[0] if objs else None


def _linked_smart_pivot_orbit_names(empty):
    if empty is None:
        return []
    names = []
    raw = empty.get("smart_pivot_orbit_objects", "")
    if isinstance(raw, str) and raw:
        try:
            names = [n for n in json.loads(raw) if isinstance(n, str)]
        except Exception:
            names = []
    legacy = empty.get("smart_pivot_orbit_object", "") or empty.get("smart_pivot_camera", "")
    if legacy and legacy not in names:
        names.append(legacy)
    return [n for n in names if n]


def _linked_smart_pivot_orbit_objects(empty):
    objs = []
    for name in _linked_smart_pivot_orbit_names(empty):
        obj = bpy.data.objects.get(name)
        if obj and obj.type in {'CAMERA', 'LIGHT'}:
            objs.append(obj)
    return objs


def _set_linked_smart_pivot_orbit_objects(empty, objs):
    names, seen = [], set()
    for obj in objs:
        if obj and obj.type in {'CAMERA', 'LIGHT'} and obj.name not in seen:
            seen.add(obj.name)
            names.append(obj.name)
    empty["smart_pivot_orbit_objects"] = json.dumps(names)
    if names:
        empty["smart_pivot_orbit_object"] = names[0]
    elif "smart_pivot_orbit_object" in empty:
        del empty["smart_pivot_orbit_object"]
    if "smart_pivot_camera" in empty:
        del empty["smart_pivot_camera"]


def _linked_smart_pivot_empty_from_orbit_object(obj):
    """Smart pivot empty targeted by this orbit object (camera/light)."""
    if obj is None or obj.type not in {'CAMERA', 'LIGHT'}:
        return None
    for c in obj.constraints:
        if c.type == 'TRACK_TO' and c.name.startswith('LiveTarget_TrackTo'):
            target = getattr(c, "target", None)
            if target and target.type == 'EMPTY' and target.get("is_smart_pivot_target"):
                return target
    for c in obj.constraints:
        if c.type == 'CHILD_OF' and c.name.startswith('LiveTarget_ChildOf'):
            target = getattr(c, "target", None)
            if target and target.type == 'EMPTY' and target.get("is_smart_pivot_target"):
                return target
    return None


def _has_live_target_childof(obj, empty):
    return any(c.type == 'CHILD_OF' and c.name.startswith('LiveTarget_ChildOf') and c.target == empty for c in obj.constraints)


def _find_live_target_track_to_index(obj):
    return next((i for i, c in enumerate(obj.constraints) if c.type == 'TRACK_TO' and c.name.startswith('LiveTarget_TrackTo')), None)


def _find_live_target_childof_index(obj, empty):
    return next((
        i for i, c in enumerate(obj.constraints)
        if c.type == 'CHILD_OF' and c.name.startswith('LiveTarget_ChildOf') and c.target == empty
    ), None)


def _find_live_target_track_to(obj, empty):
    for c in obj.constraints:
        if c.type == 'TRACK_TO' and c.name.startswith('LiveTarget_TrackTo') and c.target == empty:
            return c
    return None


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


def _apply_live_target_trackto(scene, obj, empty):
    """Bake current evaluated transform, then remove LiveTarget Track To."""
    ctx = bpy.context
    to_remove = [
        c for c in list(obj.constraints)
        if c.type == 'TRACK_TO' and c.name.startswith('LiveTarget_TrackTo') and c.target == empty
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


def _ensure_live_target_constraint_order(obj, empty):
    """Keep LiveTarget Track To above LiveTarget Child Of when both exist."""
    track_idx = _find_live_target_track_to_index(obj)
    child_idx = _find_live_target_childof_index(obj, empty)
    if track_idx is None or child_idx is None:
        return
    if track_idx > child_idx:
        try:
            obj.constraints.move(track_idx, child_idx)
        except Exception:
            pass


def _recreate_live_target_childof(scene, obj, empty):
    """Bake off any existing LiveTarget Child Of, then re-add and keep it below Track To."""
    _apply_live_target_childof(scene, obj, empty)
    child_of = obj.constraints.new(type='CHILD_OF')
    child_of.name = "LiveTarget_ChildOf"
    child_of.target = empty
    for axis in 'xyz':
        setattr(child_of, f'use_location_{axis}', True)
        setattr(child_of, f'use_rotation_{axis}', True)
        setattr(child_of, f'use_scale_{axis}', False)
    _ensure_live_target_constraint_order(obj, empty)
    _smart_pivot_view_layers_update(scene)
    try:
        child_of.set_inverse_pending = True
        _smart_pivot_view_layers_update(scene)
    except Exception:
        try:
            obj.constraints.remove(child_of)
        except Exception:
            pass


def _recreate_live_target_trackto(scene, obj, empty, prev_state=None):
    """Recreate LiveTarget Track To and keep prior settings when available."""
    _apply_live_target_trackto(scene, obj, empty)
    track_to = obj.constraints.new(type='TRACK_TO')
    track_to.name = "LiveTarget_TrackTo"
    track_to.target = empty
    if prev_state:
        track_to.track_axis = prev_state.get("track_axis", 'TRACK_NEGATIVE_Z')
        track_to.up_axis = prev_state.get("up_axis", 'UP_Y')
        track_to.use_target_z = prev_state.get("use_target_z", False)
    _ensure_live_target_constraint_order(obj, empty)


def _ensure_live_target_trackto(scene, obj, empty, prev_state=None):
    """Guarantee a LiveTarget Track To exists for this object/empty pair."""
    track_to = _find_live_target_track_to(obj, empty)
    if track_to is not None:
        _ensure_live_target_constraint_order(obj, empty)
        return track_to
    _recreate_live_target_trackto(scene, obj, empty, prev_state=prev_state)
    track_to = _find_live_target_track_to(obj, empty)
    _ensure_live_target_constraint_order(obj, empty)
    return track_to


def _get_uniform_scale_factor(base_scale, current_scale):
    ratios = [abs(current_scale[i]) / abs(base_scale[i]) for i in range(3) if abs(base_scale[i]) > 1.0e-8]
    if not ratios:
        return 1.0
    return max(1.0e-4, sum(ratios) / len(ratios))


def _set_world_translation(obj, world_pos):
    mw = obj.matrix_world.copy()
    mw.translation = world_pos
    obj.matrix_world = mw


def _has_scale_keyframes(obj):
    ad = getattr(obj, "animation_data", None)
    action = getattr(ad, "action", None) if ad else None
    return bool(action and any(f.data_path == "scale" and f.keyframe_points for f in action.fcurves))


def _capture_dolly_zoom_state(empty, cam):
    cam_data = getattr(cam, "data", None)
    if not cam_data or getattr(cam_data, "type", None) != 'PERSP':
        return None
    base_pos = cam.matrix_world.translation.copy()
    empty_pos = empty.matrix_world.translation.copy()
    offset = base_pos - empty_pos
    base_dist = offset.length
    if base_dist <= 1.0e-8:
        return None
    local_z = (cam.matrix_world.to_quaternion() @ Vector((0.0, 0.0, 1.0))).normalized()
    state = {
        "camera_name": cam.name,
        "empty_name": empty.name,
        "base_empty_scale": empty.scale.copy(),
        "base_camera_world_pos": base_pos,
        "base_lens": float(cam_data.lens),
        "base_dist": float(base_dist),
        "local_z_world": local_z,
        "lens_min": 1.0,
        "lens_max": 5000.0,
    }
    stored = {
        "camera": cam.name,
        "base_scale": [float(v) for v in state["base_empty_scale"]],
        "base_camera_world_pos": [float(v) for v in state["base_camera_world_pos"]],
        "base_lens": float(state["base_lens"]),
        "base_dist": float(state["base_dist"]),
        "local_z_world": [float(v) for v in state["local_z_world"]],
        "lens_min": float(state["lens_min"]),
        "lens_max": float(state["lens_max"]),
    }
    for k, v in stored.items():
        empty[f"smart_pivot_dz_{k}"] = v
    return state


def _dolly_zoom_state_from_empty(empty):
    cam_name = empty.get("smart_pivot_dz_camera", "")
    if not cam_name:
        return None
    try:
        state = {
            "camera_name": cam_name,
            "empty_name": empty.name,
            "base_empty_scale": Vector(empty["smart_pivot_dz_base_scale"]),
            "base_camera_world_pos": Vector(empty["smart_pivot_dz_base_camera_world_pos"]),
            "base_lens": float(empty["smart_pivot_dz_base_lens"]),
            "base_dist": float(empty["smart_pivot_dz_base_dist"]),
            "local_z_world": Vector(empty["smart_pivot_dz_local_z_world"]),
            "lens_min": float(empty.get("smart_pivot_dz_lens_min", 1.0)),
            "lens_max": float(empty.get("smart_pivot_dz_lens_max", 5000.0)),
        }
    except Exception:
        return None
    if state["base_dist"] <= 1.0e-8 or state["local_z_world"].length <= 1.0e-8:
        return None
    state["local_z_world"].normalize()
    return state


def _apply_dolly_zoom_state(state):
    cam = bpy.data.objects.get(state["camera_name"])
    dz_empty = bpy.data.objects.get(state["empty_name"])
    if not cam or not dz_empty or cam.type != 'CAMERA' or not getattr(cam, "data", None):
        return False
    if getattr(cam.data, "type", None) != 'PERSP':
        return False
    s = _get_uniform_scale_factor(state["base_empty_scale"], dz_empty.scale)
    new_dist = state["base_dist"] * s
    delta = new_dist - state["base_dist"]
    new_pos = state["base_camera_world_pos"] + (state["local_z_world"] * delta)
    _set_world_translation(cam, new_pos)
    new_lens = state["base_lens"] * s
    cam.data.lens = min(state["lens_max"], max(state["lens_min"], new_lens))
    return True


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
        active = getattr(context, "active_object", None)
        empty = _active_smart_pivot_empty(context)
        orbit_objs = _linked_smart_pivot_orbit_objects(empty) if empty else []

        # Also support starting G/R/S directly from the linked camera/light.
        self._active_is_orbit_object = bool(active and active.type in {'CAMERA', 'LIGHT'})
        if empty is None and self._active_is_orbit_object:
            empty = _linked_smart_pivot_empty_from_orbit_object(active)
            orbit_objs = [active]

        scene = _shared_scene_for_objects(empty, *orbit_objs) if orbit_objs else None
        self._ending = False
        self._empty_name = empty.name if empty else ""
        self._orbit_object_names = [obj.name for obj in orbit_objs]
        self._restore_childof_after_translate = set()
        self._had_childof_before_translate = {}
        self._trackto_state_before_rotate = {}
        self._translate_was_cancelled = False
        self._resize_was_cancelled = False
        self._dolly_zoom = None

        # Spy only for active smart-pivot empties with a valid linked orbit object.
        # Otherwise stay fully transparent and let default G/R/S keymaps run.
        if empty is None or not orbit_objs or scene is None:
            return {'PASS_THROUGH'}

        # Safety net: rebuild missing Track To if undo/redo or manual edits broke links.
        for obj in orbit_objs:
            _ensure_live_target_trackto(scene, obj, empty)

        # Apply expected pre-transform state.
        # Only Translate (Grab) should force-remove Child Of.
        if self.transform_type == 'TRANSLATE':
            self._had_childof_before_translate = {obj.name: _has_live_target_childof(obj, empty) for obj in orbit_objs}
            for obj in orbit_objs:
                if self._had_childof_before_translate.get(obj.name):
                    _apply_live_target_childof(scene, obj, empty)
            # If user grabbed camera/light directly, restore Child Of after grab ends.
            if self._active_is_orbit_object and active and self._had_childof_before_translate.get(active.name):
                self._restore_childof_after_translate = {active.name}
        elif self.transform_type == 'ROTATE':
            for obj in orbit_objs:
                if not _has_live_target_childof(obj, empty):
                    _recreate_live_target_childof(scene, obj, empty)
                track_to = _find_live_target_track_to(obj, empty)
                if track_to:
                    self._trackto_state_before_rotate[obj.name] = {
                        "track_axis": track_to.track_axis,
                        "up_axis": track_to.up_axis,
                        "use_target_z": track_to.use_target_z,
                    }
                    _apply_live_target_trackto(scene, obj, empty)
        else:
            for obj in orbit_objs:
                if not _has_live_target_childof(obj, empty):
                    _recreate_live_target_childof(scene, obj, empty)

        # Dolly zoom session: scaling smart pivot empty drives camera lens + local Z dolly.
        cam = next((obj for obj in orbit_objs if obj.type == 'CAMERA'), None)
        if self.transform_type == 'RESIZE' and empty == active and cam:
            self._dolly_zoom = _capture_dolly_zoom_state(empty, cam)

        result = self._invoke_native_transform()
        if 'RUNNING_MODAL' not in result and 'FINISHED' not in result:
            # Immediate cancel/failure: restore original Child Of state for direct camera/light grab.
            if self.transform_type == 'TRANSLATE':
                for obj in orbit_objs:
                    had = self._had_childof_before_translate.get(obj.name, False)
                    has_now = _has_live_target_childof(obj, empty)
                    if had and not has_now:
                        _recreate_live_target_childof(scene, obj, empty)
                    elif not had and has_now:
                        _apply_live_target_childof(scene, obj, empty)
            elif self.transform_type == 'ROTATE':
                for obj in orbit_objs:
                    prev = self._trackto_state_before_rotate.get(obj.name)
                    has_now = _find_live_target_track_to(obj, empty) is not None
                    if prev and not has_now:
                        _recreate_live_target_trackto(scene, obj, empty, prev_state=prev)
                    elif (not prev) and has_now:
                        _apply_live_target_trackto(scene, obj, empty)
            return {'CANCELLED'}

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if self._ending:
            empty = bpy.data.objects.get(self._empty_name)
            orbit_objs = [bpy.data.objects.get(n) for n in self._orbit_object_names]
            orbit_objs = [o for o in orbit_objs if o]
            scene = _shared_scene_for_objects(empty, *orbit_objs) if empty and orbit_objs else None
            if (
                self.transform_type == 'TRANSLATE'
                and empty and orbit_objs and scene
            ):
                if self._translate_was_cancelled:
                    for obj in orbit_objs:
                        if self._had_childof_before_translate.get(obj.name) and not _has_live_target_childof(obj, empty):
                            _recreate_live_target_childof(scene, obj, empty)
                else:
                    for obj in orbit_objs:
                        if obj.name not in self._restore_childof_after_translate and _has_live_target_childof(obj, empty):
                            _apply_live_target_childof(scene, obj, empty)
            if self.transform_type == 'ROTATE' and empty and orbit_objs and scene:
                for obj in orbit_objs:
                    prev = self._trackto_state_before_rotate.get(obj.name)
                    has_now = _find_live_target_track_to(obj, empty) is not None
                    if prev and not has_now:
                        _recreate_live_target_trackto(scene, obj, empty, prev_state=prev)
                    elif (not prev) and has_now:
                        _apply_live_target_trackto(scene, obj, empty)
            if self.transform_type == 'RESIZE' and self._dolly_zoom:
                cam = bpy.data.objects.get(self._dolly_zoom["camera_name"])
                if cam and cam.type == 'CAMERA' and getattr(cam, "data", None):
                    if self._resize_was_cancelled:
                        _set_world_translation(cam, self._dolly_zoom["base_camera_world_pos"])
                        cam.data.lens = self._dolly_zoom["base_lens"]
                    else:
                        # Snap once on finish to the final scale-driven dolly-zoom result.
                        _apply_dolly_zoom_state(self._dolly_zoom)
            return {'FINISHED'}

        if self.transform_type == 'RESIZE' and self._dolly_zoom:
            _apply_dolly_zoom_state(self._dolly_zoom)

        if (
            self.transform_type == 'TRANSLATE'
            and event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}
            and event.value == 'PRESS'
        ):
            wheel_step = 0.1
            delta = wheel_step if event.type == 'WHEELUPMOUSE' else -wheel_step
            for name in self._orbit_object_names:
                obj = bpy.data.objects.get(name)
                if not obj:
                    continue
                local_z_world = (obj.matrix_world.to_quaternion() @ Vector((0.0, 0.0, 1.0)))
                if local_z_world.length <= 1.0e-8:
                    continue
                local_z_world.normalize()
                _set_world_translation(obj, obj.matrix_world.translation + (local_z_world * delta))
            # Consume wheel so view zoom does not fight local-Z dolly while grabbing.
            return {'RUNNING_MODAL'}

        # Detect both confirm and cancel keys while allowing transform to consume them.
        if event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER', 'RIGHTMOUSE', 'ESC'} and event.value in {'PRESS', 'CLICK'}:
            cancelled = event.type in {'RIGHTMOUSE', 'ESC'}
            self._translate_was_cancelled = cancelled
            self._resize_was_cancelled = cancelled
            self._ending = True
            return {'PASS_THROUGH'}

        return {'PASS_THROUGH'}


# ---------------------------------------------------------------------
# Keymaps & purge
# ---------------------------------------------------------------------
@persistent
def _cleanup_orphan_live_target_constraints(_scene, _depsgraph):
    """If target empties are deleted manually, remove now-orphaned LiveTarget constraints."""
    for obj in bpy.data.objects:
        for c in list(obj.constraints):
            if c.type not in {'TRACK_TO', 'CHILD_OF'}:
                continue
            if not c.name.startswith(('LiveTarget_TrackTo', 'LiveTarget_ChildOf')):
                continue
            if getattr(c, 'target', None) is None:
                try:
                    obj.constraints.remove(c)
                except Exception:
                    pass


@persistent
def _sync_keyframed_dolly_zoom(_scene, _depsgraph=None):
    for empty in bpy.data.objects:
        if empty.type != 'EMPTY' or not empty.get("is_smart_pivot_target"):
            continue
        if not _has_scale_keyframes(empty):
            continue
        cam = next((obj for obj in _linked_smart_pivot_orbit_objects(empty) if obj.type == 'CAMERA'), None)
        if not cam or cam.type != 'CAMERA':
            continue
        state = _dolly_zoom_state_from_empty(empty)
        if state is None or state["camera_name"] != cam.name:
            state = _capture_dolly_zoom_state(empty, cam)
        if state:
            _apply_dolly_zoom_state(state)


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
        if c.type in {'TRACK_TO', 'CHILD_OF'} and c.name.startswith(('LiveTarget_TrackTo', 'LiveTarget_ChildOf')):
            obj.constraints.remove(c)


def _cleanup_live_target_empty(empty):
    if empty is None:
        return
    keys = ["is_smart_pivot_target", "smart_pivot_orbit_object", "smart_pivot_orbit_objects", "smart_pivot_camera"]
    keys.extend(f"smart_pivot_dz_{k}" for k in _DZ_KEYS)
    for key in keys:
        if key in empty:
            del empty[key]


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
         description="When keeping the target Empty: for camera/light objects, Child Of is used only while rotating the Empty (orbit); translating the Empty uses Track To only.",
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
        orbit_objs = []
        for obj in context.selected_objects:
            if obj == self.empty:
                continue

            if self.use_orbit and obj.type in {'CAMERA', 'LIGHT'}:
                orbit_objs.append(obj)

            constraint = obj.constraints.new(type='TRACK_TO')
            constraint.name = "LiveTarget_TrackTo"
            constraint.target = self.empty
            constraint.track_axis = self.track_axis
            constraint.up_axis = self.up_axis
            constraint.use_target_z = self.target_z
            self.constrained_objects.append((obj, constraint))
        if self.use_orbit:
            _set_linked_smart_pivot_orbit_objects(self.empty, orbit_objs)
            # LiveTarget_ChildOf is added only by the transform spy during rotate.

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
    handlers = (
        (bpy.app.handlers.depsgraph_update_post, _cleanup_orphan_live_target_constraints),
        (bpy.app.handlers.frame_change_post, _sync_keyframed_dolly_zoom),
    )
    for hlist, fn in handlers:
        if fn not in hlist:
            hlist.append(fn)

def unregister():
    for hlist, fn in (
        (bpy.app.handlers.frame_change_post, _sync_keyframed_dolly_zoom),
        (bpy.app.handlers.depsgraph_update_post, _cleanup_orphan_live_target_constraints),
    ):
        if fn in hlist:
            hlist.remove(fn)
    unregister_keymaps()
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
