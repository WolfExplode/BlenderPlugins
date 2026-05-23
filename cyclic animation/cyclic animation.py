# This should work for blender 5.0+

import bpy
import random
from bpy.props import PointerProperty, EnumProperty, BoolProperty, FloatProperty, IntProperty
from bpy.types import PropertyGroup, Operator, Panel

SCENE_KEY_BPM = "variable_playback_time_rate_pairs"
SCENE_KEY_STRENGTH = "variable_playback_strength_influence_pairs"
VARIABLE_PLAYBACK_BPM_PROP = "variable_playback_bpm"
CURVE_TIME_SCALE = 60.0  # curve X units → seconds (1/60 import scale)
DEBUG = False


def _debug_log(msg):
    if DEBUG:
        print(f"VariablePlayback: {msg}")


def _get_action_slot_for_datablock(action, datablock):
    anim = getattr(datablock, "animation_data", None)
    if anim and getattr(anim, "action", None) == action:
        slot = getattr(anim, "action_slot", None)
        if slot is not None:
            return slot
    slots = getattr(action, "slots", None)
    if slots is not None:
        for slot in slots:
            if getattr(slot, "id", None) is datablock:
                return slot
        for slot in slots:
            if getattr(slot, "name", None) == getattr(datablock, "name", None):
                return slot
    return None


def _resolve_slot_identifier(slot):
    if not slot:
        return None
    return getattr(slot, "identifier", None) or getattr(slot, "name", None)


def _collect_fcurves_from_layers(action, slot=None, slot_identifier=None):
    fcurves = []
    if not hasattr(action, "layers"):
        return fcurves
    for layer in action.layers:
        for strip in layer.strips:
            channelbag = getattr(strip, "channelbag", None)
            if callable(channelbag) and slot is not None:
                bag = channelbag(slot, ensure=False)
                if bag:
                    fcurves.extend(getattr(bag, "fcurves", []))
            elif hasattr(strip, "fcurves") and slot is not None:
                fcurves.extend(strip.fcurves)
            elif hasattr(strip, "channelbags") and slot_identifier:
                for bag in strip.channelbags:
                    if _resolve_slot_identifier(getattr(bag, "slot", None)) == slot_identifier:
                        fcurves.extend(getattr(bag, "fcurves", []))
    return fcurves


def get_action_fcurves(action, datablock=None):
    if hasattr(action, "fcurves") and not hasattr(action, "slots"):
        return action.fcurves
    if not hasattr(action, "layers"):
        return getattr(action, "fcurves", []) or []
    if datablock is None:
        return []
    slot = _get_action_slot_for_datablock(action, datablock)
    if slot is None:
        return []
    return _collect_fcurves_from_layers(action, slot=slot)


def get_action_fcurves_for_slot(action, slot_identifier, datablock=None):
    if not slot_identifier or not hasattr(action, "slots"):
        return get_action_fcurves(action, datablock=datablock)
    slot = next(
        (s for s in action.slots if _resolve_slot_identifier(s) == slot_identifier),
        None,
    )
    if slot is None:
        return []
    return _collect_fcurves_from_layers(action, slot=slot, slot_identifier=slot_identifier)


def ensure_fcurve(action, datablock, data_path, index=0, group_name=""):
    if hasattr(action, "fcurve_ensure_for_datablock"):
        try:
            return action.fcurve_ensure_for_datablock(
                datablock, data_path, index=index, group_name=group_name or None
            )
        except TypeError:
            return action.fcurve_ensure_for_datablock(datablock, data_path, index=index)
    if hasattr(action, "fcurves"):
        for fc in action.fcurves:
            if fc.data_path == data_path and fc.array_index == index:
                return fc
        return action.fcurves.new(data_path=data_path, index=index)
    return None


def parse_action_enum(value):
    if not value or value == "NONE":
        return None, None
    parts = value.split("|", 1)
    return bpy.data.actions.get(parts[0]), (parts[1] if len(parts) > 1 else None)


def _actions_from_anim_data(anim_data):
    actions = set()
    if not anim_data:
        return actions
    for track in anim_data.nla_tracks:
        for strip in track.strips:
            if strip.action:
                actions.add(strip.action.name)
    if anim_data.action:
        actions.add(anim_data.action.name)
    return actions


def _collect_actions_for_object(obj):
    if not obj:
        return set()
    actions = set()
    if obj.animation_data:
        actions |= _actions_from_anim_data(obj.animation_data)
    sk = getattr(getattr(obj, "data", None), "shape_keys", None)
    if sk and sk.animation_data:
        actions |= _actions_from_anim_data(sk.animation_data)
    return actions


def _is_baked_action_name(name):
    return bool(name) and "baked" in name.casefold()


def _unlink_action_for_removal(action):
    if action is None:
        return

    def clean_animdata(anim_data):
        if not anim_data:
            return
        if anim_data.action == action:
            anim_data.action = None
        for track in anim_data.nla_tracks:
            for strip in list(track.strips):
                if strip.action == action:
                    track.strips.remove(strip)

    for ob in bpy.data.objects:
        if ob.animation_data:
            clean_animdata(ob.animation_data)
    for coll in (bpy.data.meshes, bpy.data.curves, bpy.data.lattices):
        for data in coll:
            if getattr(data, "animation_data", None):
                clean_animdata(data.animation_data)
            sk = getattr(data, "shape_keys", None)
            if sk and sk.animation_data:
                clean_animdata(sk.animation_data)


def action_enum_items(self, context):
    props = context.scene.variable_playback_props
    obj = props.source_object if props else getattr(self, "source_object", None)
    if not obj:
        return [("NONE", "No object selected", "")]
    return get_action_slot_enum_items_for_object(obj)


def get_action_slot_enum_items_for_object(obj):
    actions = _collect_actions_for_object(obj)
    if not actions:
        return [("NONE", "No actions found", "")]

    items = []
    for action_name in sorted(actions):
        if _is_baked_action_name(action_name):
            continue
        action = bpy.data.actions.get(action_name)
        if not action:
            continue
        slots = getattr(action, "slots", None)
        if slots:
            for slot in slots:
                slot_id = _resolve_slot_identifier(slot)
                slot_label = getattr(slot, "name", "") or (slot_id or "")
                if _is_baked_action_name(slot_label):
                    continue
                label = f"{action.name} ({slot_label})" if slot_label else action.name
                identifier = f"{action.name}|{slot_id}" if slot_id is not None else action.name
                items.append((identifier, label, ""))
        else:
            items.append((action.name, action.name, ""))

    return items or [("NONE", "No actions found", "")]


def keyframes_frame_range_from_fcurves(fcurves):
    min_frame = max_frame = None
    for fc in fcurves:
        for kp in fc.keyframe_points:
            frame = kp.co.x
            if min_frame is None or frame < min_frame:
                min_frame = frame
            if max_frame is None or frame > max_frame:
                max_frame = frame
    if min_frame is None:
        raise ValueError("no keyframes on F-Curves")
    return min_frame, max_frame


def is_shape_key_action(obj, action):
    if not obj or not action:
        return False
    sk = getattr(getattr(obj, "data", None), "shape_keys", None)
    if not sk or not sk.animation_data:
        return False
    if sk.animation_data.action == action:
        return True
    for track in sk.animation_data.nla_tracks:
        for strip in track.strips:
            if strip.action == action:
                return True
    return False


def target_datablock(obj, action):
    return obj.data.shape_keys if is_shape_key_action(obj, action) else obj


def _base_values_from_fcurves(fcurves, src_start):
    base_values = {}
    for fc in fcurves:
        key = (fc.data_path, fc.array_index)
        base_values[key] = fc.evaluate(src_start) if fc.keyframe_points else 0.0
    return base_values


def _fcurves_error(action, slot_id, fcurves):
    if fcurves:
        return None
    if slot_id and hasattr(action, "slots"):
        if not any(_resolve_slot_identifier(s) == slot_id for s in action.slots):
            return f"Action '{action.name}': slot not found"
    return f"Action '{action.name}': no F-Curves on selected slot"


def build_action_data(props):
    action, slot_id = parse_action_enum(props.source_action)
    if not action:
        return None, "Action not found"
    fcurves = get_action_fcurves_for_slot(
        action, slot_id, datablock=target_datablock(props.source_object, action)
    )
    err = _fcurves_error(action, slot_id, fcurves)
    if err:
        return None, err
    return {
        "action": action,
        "slot_id": slot_id,
        "fcurves": fcurves,
        "is_shape_key": is_shape_key_action(props.source_object, action),
        "base_values": {},
    }, None


def simplify_fcurve(fcurve, tolerance=0.001):
    if tolerance <= 0:
        return 0
    points = fcurve.keyframe_points
    if len(points) <= 2:
        return 0
    to_remove = []
    for i in range(1, len(points) - 1):
        kf = points[i]
        if kf.interpolation != "BEZIER":
            continue
        if kf.handle_left_type not in {"AUTO", "AUTO_CLAMPED", "VECTOR"}:
            continue
        if kf.handle_right_type not in {"AUTO", "AUTO_CLAMPED", "VECTOR"}:
            continue
        prev, nxt = points[i - 1], points[i + 1]
        frame_range = nxt.co.x - prev.co.x
        if frame_range == 0:
            continue
        t = (kf.co.x - prev.co.x) / frame_range
        if abs(kf.co.y - (prev.co.y + t * (nxt.co.y - prev.co.y))) < tolerance:
            to_remove.append(i)
    removed = len(to_remove)
    if removed:
        for i in reversed(to_remove):
            points.remove(points[i], fast=True)
        fcurve.update()
    return removed


def update_bpm_curve(self, context):
    if not self.bpm_curve and SCENE_KEY_BPM in context.scene:
        del context.scene[SCENE_KEY_BPM]


def update_strength_curve(self, context):
    if not self.strength_curve and SCENE_KEY_STRENGTH in context.scene:
        del context.scene[SCENE_KEY_STRENGTH]


def sample_curve_object_vertices(curve_obj, context):
    temp_obj = curve_obj.copy()
    temp_obj.data = curve_obj.data.copy()
    context.scene.collection.objects.link(temp_obj)
    eval_obj = None
    try:
        eval_obj = temp_obj.evaluated_get(context.evaluated_depsgraph_get())
        temp_mesh = eval_obj.to_mesh()
        if len(temp_mesh.vertices) < 2:
            return None
        return [(v.co.x, v.co.y, v.co.z) for v in temp_mesh.vertices]
    finally:
        if eval_obj is not None:
            eval_obj.to_mesh_clear()
        bpy.data.objects.remove(temp_obj, do_unlink=True)


def cycle_output_frame_count(fps, effective_bpm):
    """Output frames for one full source cycle at one beat (60/BPM seconds)."""
    return max(1, round(fps * 60.0 / effective_bpm))


def source_frame_for_cycle_offset(src_start, src_end, offset, cycle_len):
    """
    Map one output frame inside a BPM cycle to a source frame.

    Each beat spans the loop body (src_start through src_end - 1). The duplicate
    closure key at src_end is only sampled when the bake appends a final frame.
    """
    key_count = src_end - src_start + 1
    loop_body = key_count - 1
    if loop_body <= 0 or cycle_len <= 1:
        return src_start
    key_index = round(offset * (loop_body - 1) / (cycle_len - 1))
    return src_start + int(key_index)


def sample_pairs(time_seconds, pairs, default=None):
    if not pairs:
        return default
    if time_seconds <= pairs[0][0]:
        return pairs[0][1]
    if time_seconds >= pairs[-1][0]:
        return pairs[-1][1]
    for i in range(len(pairs) - 1):
        t0, v0 = pairs[i]
        t1, v1 = pairs[i + 1]
        if t0 <= time_seconds <= t1:
            return v0 + (time_seconds - t0) / (t1 - t0) * (v1 - v0)
    return pairs[-1][1]


def dedupe_time_pairs(pairs):
    clean, last_t = [], -1.0
    for t, v in sorted(pairs, key=lambda k: k[0]):
        if t > last_t:
            clean.append((t, v))
            last_t = t
    return clean


def read_curve_to_scene(context, curve_obj, scene_key, value_fn):
    coords = sample_curve_object_vertices(curve_obj, context)
    if coords is None:
        return None, "Curve resolved to fewer than 2 vertices"
    pairs = [
        (x * CURVE_TIME_SCALE, value_fn(y))
        for x, y, _z in coords
        if x * CURVE_TIME_SCALE >= 0
    ]
    clean = dedupe_time_pairs(pairs)
    context.scene[scene_key] = clean
    return clean, None


class VariablePlaybackProps(PropertyGroup):
    source_object: PointerProperty(type=bpy.types.Object)
    source_action_id: bpy.props.StringProperty(default="NONE", options={"HIDDEN"})

    def _get_source_action(self):
        items = action_enum_items(self, bpy.context)
        stored = self.source_action_id
        for i, item in enumerate(items):
            if item[0] == stored:
                return i
        return 0

    def _set_source_action(self, value):
        items = action_enum_items(self, bpy.context)
        if 0 <= value < len(items):
            self.source_action_id = items[value][0]
        else:
            self.source_action_id = "NONE"

    source_action: EnumProperty(
        name="Source Action",
        items=action_enum_items,
        get=_get_source_action,
        set=_set_source_action,
        options={"SKIP_SAVE"},
    )
    bpm_curve: PointerProperty(type=bpy.types.Object, update=update_bpm_curve)
    strength_curve: PointerProperty(type=bpy.types.Object, update=update_strength_curve)
    strength_influence_flat: FloatProperty(
        name="Flat Influence",
        default=1.0,
        min=0.0,
        max=10.0,
        soft_min=0.0,
        soft_max=2.0,
    )
    use_random_intensity: BoolProperty(name="Random Intensity per Loop", default=False)
    random_intensity_seed: IntProperty(name="Intensity Seed", default=0, min=0)
    random_intensity_min: FloatProperty(name="Min", default=0.8, min=0.0, max=10.0, soft_min=0.1, soft_max=2.0)
    random_intensity_max: FloatProperty(name="Max", default=1.2, min=0.0, max=10.0, soft_min=0.1, soft_max=2.0)
    use_random_speed: BoolProperty(name="Random Speed per Loop", default=False)
    random_speed_min: FloatProperty(name="Min", default=0.8, min=0.1, max=3.0, soft_min=0.5, soft_max=2.0)
    random_speed_max: FloatProperty(name="Max", default=1.2, min=0.1, max=3.0, soft_min=0.5, soft_max=2.0)
    bake_speed_scale: FloatProperty(name="Speed Multiplier", default=1.0, min=0.05, soft_min=0.1, soft_max=2.0)
    use_simplify_fcurve: BoolProperty(name="Simplify F-Curve", default=True)
    simplify_tolerance: FloatProperty(
        name="Tolerance",
        default=0.001,
        min=0.0,
        soft_min=0.0001,
        soft_max=0.1,
        precision=4,
    )
    bake_overwrite_existing: BoolProperty(name="Overwrite Existing Bake", default=True)


class VARIABLEPLAYBACK_PT_panel(Panel):
    bl_label = "Variable Playback Baker"
    bl_idname = "VARIABLEPLAYBACK_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Animation"

    @staticmethod
    def _object_has_anim(obj):
        if obj.animation_data:
            return True
        sk = getattr(getattr(obj, "data", None), "shape_keys", None)
        return bool(sk and sk.animation_data)

    def _draw_source(self, layout, props, context):
        layout.label(text="Source & Animation", icon="OUTLINER_OB_ARMATURE")
        layout.prop(props, "source_object", icon="OBJECT_DATA")
        obj = props.source_object
        if not obj or not self._object_has_anim(obj):
            layout.label(text="Select an object with animation data", icon="INFO")
            return

        layout.prop(props, "source_action", icon="ACTION")
        if not props.source_action or props.source_action == "NONE":
            return
        action, slot_id = parse_action_enum(props.source_action)
        if not action:
            return
        fcurves = get_action_fcurves_for_slot(
            action, slot_id, datablock=target_datablock(obj, action)
        )
        col = layout.column(align=True)
        if not fcurves:
            col.label(text="No F-Curves on selected slot", icon="ERROR")
            return
        try:
            fr = keyframes_frame_range_from_fcurves(fcurves)
        except ValueError:
            col.label(text="No keyframes on slot F-Curves", icon="ERROR")
        else:
            col.label(text=f"Frames: {fr[0]:.0f} - {fr[1]:.0f}", icon="TIME")
            fps = context.scene.render.fps or 1
            col.label(text=f"Base Duration: {(fr[1] - fr[0]) / fps:.2f}s", icon="PLAY")

    def _draw_speed(self, layout, props, context):
        box = layout.box()
        box.label(text="Speed", icon="TIME")
        box.prop(props, "bpm_curve", icon="CURVE_DATA")
        box.prop(props, "bake_speed_scale", slider=True)
        if SCENE_KEY_BPM in context.scene:
            pairs = context.scene[SCENE_KEY_BPM]
            info = box.box()
            info.label(text=f"Data Loaded: {len(pairs)} points", icon="CHECKMARK")
            for t, bpm in pairs[:3]:
                info.label(text=f"  t={t:.2f}s, BPM={bpm:.1f}")
        col = box.column(align=True)
        col.operator("variable_playback.read_curve", icon="IMPORT")
        mesh_data = props.source_object.data if props.source_object else None
        is_mesh = isinstance(mesh_data, bpy.types.Mesh)
        row = col.row(align=True)
        row.operator("variable_playback.keyframe_bpm_on_source", icon="KEYTYPE_KEYFRAME_VEC")
        row.enabled = SCENE_KEY_BPM in context.scene and props.source_object and is_mesh
        row = col.row(align=True)
        row.operator("variable_playback.copy_bpm_as_new_driver", icon="DECORATE_DRIVER")
        row.enabled = props.source_object and is_mesh and VARIABLE_PLAYBACK_BPM_PROP in mesh_data

    def _draw_strength(self, layout, props, context):
        box = layout.box()
        box.label(text="Strength / Influence", icon="FORCE_FORCE")
        box.prop(props, "strength_curve", icon="CURVE_DATA")
        row = box.row()
        sub = row.column()
        sub.enabled = SCENE_KEY_STRENGTH not in context.scene
        sub.prop(props, "strength_influence_flat", slider=True)
        if SCENE_KEY_STRENGTH in context.scene:
            pairs = context.scene[SCENE_KEY_STRENGTH]
            info = box.box()
            info.label(text=f"Strength Data: {len(pairs)} points", icon="CHECKMARK")
            for t, influence in pairs[:3]:
                info.label(text=f"  t={t:.2f}s, Influence={influence:.1%}")
        box.operator("variable_playback.read_strength_curve", icon="IMPORT")

    def _draw_variation(self, layout, props):
        box = layout.box()
        box.label(text="Random per Loop", icon="MODIFIER")
        sub = box.box()
        sub.label(text="Random Intensity", icon="SHADERFX")
        col = sub.column(align=True)
        col.prop(props, "use_random_intensity", text="Enable")
        if props.use_random_intensity:
            col.prop(props, "random_intensity_seed", text="Seed")
            row = col.row(align=True)
            row.prop(props, "random_intensity_min", text="Min")
            row.prop(props, "random_intensity_max", text="Max")
        sub = box.box()
        sub.label(text="Random Speed", icon="TIME")
        col = sub.column(align=True)
        col.prop(props, "use_random_speed", text="Enable")
        if props.use_random_speed:
            if props.random_intensity_seed == 0:
                col.label(text="Set Intensity Seed > 0 to lock speed seed", icon="ERROR")
            else:
                col.label(text=f"Uses seed: {props.random_intensity_seed + 1}", icon="INFO")
            row = col.row(align=True)
            row.prop(props, "random_speed_min", text="Min")
            row.prop(props, "random_speed_max", text="Max")

    def _draw_bake(self, layout, props, context):
        box = layout.box()
        box.label(text="Bake & Output", icon="RENDER_ANIMATION")
        col = box.column(align=True)
        col.prop(props, "use_simplify_fcurve", text="Simplify F-Curve")
        if props.use_simplify_fcurve:
            col.prop(props, "simplify_tolerance", slider=True)
        box.prop(props, "bake_overwrite_existing")
        row = box.row(align=True)
        row.operator("variable_playback.bake", icon="REC")
        row.enabled = SCENE_KEY_BPM in context.scene

    def draw(self, context):
        props = context.scene.variable_playback_props
        self._draw_source(self.layout, props, context)
        self._draw_speed(self.layout, props, context)
        self._draw_strength(self.layout, props, context)
        self._draw_variation(self.layout, props)
        self._draw_bake(self.layout, props, context)


class VARIABLEPLAYBACK_OT_read_curve(Operator):
    bl_idname = "variable_playback.read_curve"
    bl_label = "Read BPM Data"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.variable_playback_props
        if not props.bpm_curve:
            self.report({"ERROR"}, "No speed curve selected")
            return {"CANCELLED"}
        if props.bpm_curve.type != "CURVE":
            self.report({"ERROR"}, "Selected object is not a curve")
            return {"CANCELLED"}
        clean, err = read_curve_to_scene(
            context, props.bpm_curve, SCENE_KEY_BPM, lambda y: y * 100.0
        )
        if err:
            self.report({"ERROR"}, err)
            return {"CANCELLED"}
        _debug_log(f"Read BPM data: {len(clean)} points")
        for t, bpm in clean[:5]:
            _debug_log(f"  t={t:.3f}s -> BPM={bpm:.2f}")
        if len(clean) > 5:
            _debug_log(f"  ... ({len(clean) - 5} more)")
        self.report({"INFO"}, f"Sampled {len(clean)} points from curve.")
        return {"FINISHED"}


class VARIABLEPLAYBACK_OT_read_strength_curve(Operator):
    bl_idname = "variable_playback.read_strength_curve"
    bl_label = "Read Strength Data"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.variable_playback_props
        if not props.strength_curve:
            self.report({"ERROR"}, "No strength curve selected")
            return {"CANCELLED"}
        if props.strength_curve.type != "CURVE":
            self.report({"ERROR"}, "Selected object is not a curve")
            return {"CANCELLED"}
        clean, err = read_curve_to_scene(
            context,
            props.strength_curve,
            SCENE_KEY_STRENGTH,
            lambda y: max(y, 0.0),
        )
        if err:
            self.report({"ERROR"}, err)
            return {"CANCELLED"}
        self.report({"INFO"}, f"Sampled {len(clean)} strength points from curve.")
        return {"FINISHED"}


class VARIABLEPLAYBACK_OT_keyframe_bpm_on_source(Operator):
    bl_idname = "variable_playback.keyframe_bpm_on_source"
    bl_label = "Keyframe BPM on Source Mesh"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.variable_playback_props
        obj = props.source_object
        if not obj:
            self.report({"ERROR"}, "No source object selected")
            return {"CANCELLED"}
        mesh = obj.data
        if not isinstance(mesh, bpy.types.Mesh):
            self.report({"ERROR"}, "Source object has no mesh data")
            return {"CANCELLED"}
        pairs = context.scene.get(SCENE_KEY_BPM)
        if not pairs:
            self.report({"ERROR"}, "No curve data loaded")
            return {"CANCELLED"}

        prop_key = VARIABLE_PLAYBACK_BPM_PROP
        data_path = f'["{prop_key}"]'
        if prop_key in mesh and not isinstance(mesh[prop_key], (int, float)):
            self.report({"ERROR"}, f"Custom property '{prop_key}' must be numeric")
            return {"CANCELLED"}
        if prop_key not in mesh:
            mesh[prop_key] = 0.0
        if not mesh.animation_data:
            mesh.animation_data_create()
        if mesh.animation_data.action is None:
            mesh.animation_data.action = bpy.data.actions.new(
                name=f"{mesh.name}_VariablePlaybackBPM"
            )

        fps = context.scene.render.fps or 1
        frame_start, frame_end = context.scene.frame_start, context.scene.frame_end
        for frame in range(frame_start, frame_end + 1):
            mesh[prop_key] = float(sample_pairs(frame / fps, pairs))
            mesh.keyframe_insert(data_path=data_path, frame=frame)
        self.report(
            {"INFO"},
            f"Keyed BPM on mesh '{mesh.name}' ({frame_end - frame_start + 1} frames)",
        )
        return {"FINISHED"}


class VARIABLEPLAYBACK_OT_copy_bpm_as_new_driver(Operator):
    bl_idname = "variable_playback.copy_bpm_as_new_driver"
    bl_label = "Copy as New Driver…"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        props = context.scene.variable_playback_props
        mesh = props.source_object.data if props and props.source_object else None
        return isinstance(mesh, bpy.types.Mesh) and VARIABLE_PLAYBACK_BPM_PROP in mesh

    def draw(self, context):
        mesh = context.scene.variable_playback_props.source_object.data
        self.layout.label(text="Right-click the property, then Copy as New Driver")
        self.layout.prop(mesh, f'["{VARIABLE_PLAYBACK_BPM_PROP}"]', text=VARIABLE_PLAYBACK_BPM_PROP)

    def invoke(self, context, event):
        if not self.poll(context):
            self.report({"ERROR"}, "Source mesh is missing the BPM custom property")
            return {"CANCELLED"}
        return context.window_manager.invoke_popup(self, width=320)

    def execute(self, context):
        return {"FINISHED"}


class VARIABLEPLAYBACK_OT_bake(Operator):
    bl_idname = "variable_playback.bake"
    bl_label = "Bake"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.variable_playback_props
        pairs = context.scene.get(SCENE_KEY_BPM)
        strength_pairs = context.scene.get(SCENE_KEY_STRENGTH, [])
        strength_flat = props.strength_influence_flat
        speed_scale = props.bake_speed_scale

        if not pairs:
            self.report({"ERROR"}, "No curve data loaded")
            return {"CANCELLED"}

        intensity_rng = speed_rng = None
        if props.use_random_intensity:
            intensity_rng = (
                random.Random(props.random_intensity_seed)
                if props.random_intensity_seed > 0
                else random.Random()
            )
            if props.random_intensity_seed > 0:
                self.report({"INFO"}, f"Using random intensity seed: {props.random_intensity_seed}")
        if props.use_random_speed:
            speed_rng = (
                random.Random(props.random_intensity_seed + 1)
                if props.random_intensity_seed > 0
                else random.Random()
            )

        action_data, err = build_action_data(props)
        if err:
            self.report({"ERROR"}, err)
            return {"CANCELLED"}

        action = action_data["action"]
        slot_id = action_data["slot_id"]
        fcurves = action_data["fcurves"]
        is_shape_key = action_data["is_shape_key"]

        target_datablock = (
            props.source_object.data.shape_keys if is_shape_key else props.source_object
        )
        suffix = "_ShapeKeys" if is_shape_key else ""

        slot_name = ""
        if slot_id and hasattr(action, "slots") and action.slots:
            for slot in action.slots:
                if _resolve_slot_identifier(slot) == slot_id:
                    slot_name = getattr(slot, "name", "") or slot_id
                    break
        name_stem = f"{action.name}_{slot_name}" if slot_name else action.name

        base_name = (
            f"{name_stem}_Baked"
            if speed_scale == 1.0
            else f"{name_stem}_Speed{speed_scale:.2f}_Baked"
        )
        baked_name = base_name + suffix
        existing_action = bpy.data.actions.get(baked_name)
        if existing_action is not None:
            if not props.bake_overwrite_existing:
                self.report(
                    {"ERROR"},
                    f"Action '{baked_name}' already exists. Enable Overwrite Existing Bake or change the source action/slot.",
                )
                return {"CANCELLED"}
            _unlink_action_for_removal(existing_action)
            if getattr(existing_action, "use_fake_user", False):
                existing_action.use_fake_user = False
            if existing_action.users != 0:
                self.report(
                    {"ERROR"},
                    f"Cannot overwrite '{baked_name}': still in use ({existing_action.users} user(s)).",
                )
                return {"CANCELLED"}
            bpy.data.actions.remove(existing_action)

        baked_action = bpy.data.actions.new(name=baked_name)
        if not target_datablock.animation_data:
            target_datablock.animation_data_create()
        target_datablock.animation_data.action = baked_action

        baked_slot = _get_action_slot_for_datablock(baked_action, target_datablock)

        frame_start, frame_end = context.scene.frame_start, context.scene.frame_end

        try:
            src_start, src_end = keyframes_frame_range_from_fcurves(fcurves)
        except ValueError:
            self.report({"ERROR"}, f"Action '{action.name}': no keyframes on selected slot F-Curves")
            return {"CANCELLED"}
        # Rest keys on frame 0 while baking from frame 1+ skew cycle length by one frame.
        if src_start == 0 and frame_start > 0:
            src_start = frame_start
        if src_end - src_start == 0:
            self.report({"ERROR"}, f"Action '{action.name}' slot has zero duration")
            return {"CANCELLED"}
        action_data["src_start"] = src_start
        action_data["src_end"] = src_end
        action_data["base_values"] = _base_values_from_fcurves(fcurves, src_start)
        fcurve_map = {(fc.data_path, fc.array_index): fc for fc in fcurves}

        baked_fcurves = {}
        for dp, idx in fcurve_map:
            baked_fc = ensure_fcurve(baked_action, target_datablock, dp, idx)
            if baked_fc:
                baked_fcurves[(dp, idx)] = baked_fc

        fps = context.scene.render.fps or 24
        frame_count = frame_end - frame_start + 1
        key_count = src_end - src_start + 1
        _debug_log(
            f"Bake start: action='{action.name}', output={frame_start}-{frame_end} "
            f"({frame_count} frames), source={src_start}-{src_end} ({key_count} keys), fps={fps}"
        )
        _debug_log(f"  speed_scale={speed_scale}, BPM points={len(pairs)}")

        frame_data = []
        wm = context.window_manager
        wm.progress_begin(0, frame_count)

        T = frame_start
        cycle_index = 0
        while T <= frame_end:
            t_cycle = T / fps
            raw_bpm = sample_pairs(t_cycle, pairs)
            effective_bpm = max(raw_bpm * speed_scale, 1e-6)
            if props.use_random_speed:
                rng = speed_rng or random
                speed_mult = rng.uniform(props.random_speed_min, props.random_speed_max)
                effective_bpm = max(effective_bpm * speed_mult, 1e-6)
            else:
                speed_mult = 1.0
            cycle_len = cycle_output_frame_count(fps, effective_bpm)
            cycle_end = T + cycle_len - 1

            if props.use_random_intensity:
                rng = intensity_rng or random
                loop_intensity = rng.uniform(props.random_intensity_min, props.random_intensity_max)
            else:
                loop_intensity = 1.0

            influence = sample_pairs(
                t_cycle,
                strength_pairs,
                default=max(float(strength_flat), 0.0),
            )
            final_influence = influence * loop_intensity
            src_start_c, src_end_c = action_data["src_start"], action_data["src_end"]

            if cycle_end > frame_end:
                if not frame_data or frame_data[-1][0] < frame_end:
                    frame_data.append((frame_end, src_end_c, final_influence))
                _debug_log(
                    f"Cycle {cycle_index + 1} closing frame at {frame_end}: "
                    f"source={src_end_c} (needs {cycle_len} frame(s) {T}-{cycle_end}, "
                    f"BPM={effective_bpm:.2f})"
                )
                break

            for offset in range(cycle_len):
                src_frame = source_frame_for_cycle_offset(
                    src_start_c, src_end_c, offset, cycle_len
                )
                frame_data.append((T, src_frame, final_influence))
                T += 1

            cycle_index += 1
            src_first = source_frame_for_cycle_offset(src_start_c, src_end_c, 0, cycle_len)
            src_last = source_frame_for_cycle_offset(
                src_start_c, src_end_c, cycle_len - 1, cycle_len
            )
            _debug_log(
                f"Cycle {cycle_index}: output {T - cycle_len}-{T - 1}, "
                f"t={t_cycle:.3f}s, raw_bpm={raw_bpm:.2f}, effective_bpm={effective_bpm:.2f}, "
                f"speed_mult={speed_mult:.3f}, cycle_len={cycle_len}, "
                f"source {src_first}-{src_last} (loop body per beat), "
                f"influence={final_influence:.3f}"
            )
            wm.progress_update(min(T - frame_start, frame_count))

        _debug_log(
            f"Bake schedule done: {cycle_index} cycle(s), {len(frame_data)} keyed frame(s), "
            f"next T={T}"
        )

        tolerance = 1e-6
        for (dp, idx), baked_fc in baked_fcurves.items():
            src_fc = fcurve_map.get((dp, idx))
            if src_fc is None:
                continue
            first_value = action_data["base_values"].get((dp, idx), 0.0)

            count = len(frame_data)
            baked_fc.keyframe_points.add(count)
            frames_out = [0.0] * count
            values_out = [0.0] * count
            for i, (frame, src_frame, influence) in enumerate(frame_data):
                base_value = src_fc.evaluate(src_frame)
                delta = base_value - first_value
                values_out[i] = (
                    base_value
                    if abs(delta) < tolerance
                    else first_value + delta * influence
                )
                frames_out[i] = frame
            co_flat = [coord for pair in zip(frames_out, values_out) for coord in pair]
            baked_fc.keyframe_points.foreach_set("co", co_flat)
            baked_fc.update()

        _debug_log(f"Wrote {len(baked_fcurves)} F-Curve(s), {len(frame_data)} key(s) each")

        wm.progress_end()

        total_removed = 0
        if props.use_simplify_fcurve and props.simplify_tolerance > 0:
            for fcurve in get_action_fcurves(baked_action, target_datablock):
                total_removed += simplify_fcurve(fcurve, props.simplify_tolerance)
            if total_removed > 0:
                _debug_log(f"Simplified {total_removed} redundant keyframe(s)")

        actual_end_frame = frame_data[-1][0] if frame_data else frame_end
        anim = target_datablock.animation_data
        track = anim.nla_tracks.new()
        track.name = "Variable Playback"
        strip = track.strips.new(baked_name, frame_start, baked_action)
        strip.frame_end = actual_end_frame
        strip.action_frame_start = frame_start
        strip.action_frame_end = actual_end_frame
        strip.blend_type = "REPLACE"
        if baked_slot is not None and hasattr(strip, "action_slot"):
            strip.action_slot = baked_slot
        anim.action = None

        _debug_log(
            f"Bake finished: '{baked_name}' on NLA track '{track.name}', "
            f"strip frames {frame_start}-{actual_end_frame}"
        )

        mode_msg = []
        if props.use_random_intensity:
            mode_msg.append("random intensity")
        if props.use_random_speed:
            mode_msg.append("random speed")
        mode_str = " + ".join(mode_msg) or "baked"
        self.report(
            {"INFO"},
            f"Baked keys {frame_start}..{actual_end_frame} to '{baked_name}' "
            f"on NLA track '{track.name}' ({mode_str})",
        )
        return {"FINISHED"}


classes = (
    VariablePlaybackProps,
    VARIABLEPLAYBACK_PT_panel,
    VARIABLEPLAYBACK_OT_read_curve,
    VARIABLEPLAYBACK_OT_read_strength_curve,
    VARIABLEPLAYBACK_OT_keyframe_bpm_on_source,
    VARIABLEPLAYBACK_OT_copy_bpm_as_new_driver,
    VARIABLEPLAYBACK_OT_bake,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.variable_playback_props = PointerProperty(type=VariablePlaybackProps)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.variable_playback_props


if __name__ == "__main__":
    register()
