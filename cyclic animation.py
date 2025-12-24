import bpy
import random
from bpy.props import PointerProperty, EnumProperty, BoolProperty, FloatProperty, CollectionProperty, IntProperty
from bpy.types import PropertyGroup, Operator, Panel

# ============================================================================ #
# HELPER FUNCTIONS (Pre-4.4 and 4.4+/5.0 Layered/Slotted Actions)
# ============================================================================ #

def _get_action_slot_for_datablock(action, datablock):
    """Best-effort lookup of the ActionSlot that belongs to a given datablock."""
    anim = getattr(datablock, "animation_data", None)
    if anim and getattr(anim, "action", None) == action:
        slot = getattr(anim, "action_slot", None)
        if slot is not None:
            return slot
    
    # Fallback: search slots by id or name
    slots = getattr(action, "slots", None)
    if slots is not None:
        for slot in slots:
            if getattr(slot, "id", None) is datablock:
                return slot
        for slot in slots:
            if getattr(slot, "name", None) == getattr(datablock, "name", None):
                return slot
    return None


def get_action_fcurves(action, datablock=None):
    """
    Retrieve F-Curves from an Action.
    
    - Pre-4.4 / legacy: returns action.fcurves directly.
    - 4.4+/5.0 slotted/layered: if a datablock is provided, only returns curves
      that belong to the appropriate slot for that datablock.
    """
    # Legacy / non-slotted API path
    if hasattr(action, "fcurves") and not hasattr(action, "slots"):
        return action.fcurves
    
    # If we don't have layered API, fall back to any fcurves attribute
    if not hasattr(action, "layers"):
        return getattr(action, "fcurves", []) or []
    
    # Layered/slotted path – require datablock to pick the correct slot
    if datablock is None:
        # Fallback: collect all fcurves from all strips
        fcurves = []
        for layer in action.layers:
            for strip in layer.strips:
                if hasattr(strip, "fcurves"):
                    fcurves.extend(strip.fcurves)
        return fcurves
    
    slot = _get_action_slot_for_datablock(action, datablock)
    if slot is None:
        # No slot found; fall back to whatever curves we can see
        return getattr(action, "fcurves", []) or []
    
    fcurves = []
    for layer in action.layers:
        for strip in layer.strips:
            # Newer API: strip.channelbag(slot, ensure=False)
            channelbag = getattr(strip, "channelbag", None)
            if callable(channelbag):
                bag = channelbag(slot, ensure=False)
                if bag is not None:
                    fcurves.extend(getattr(bag, "fcurves", []))
            elif hasattr(strip, "fcurves"):
                # Older layered API before channelbag helper existed
                fcurves.extend(strip.fcurves)
    return fcurves


def ensure_fcurve(action, datablock, data_path, index=0, group_name=""):
    """
    Creates/ensures an F-Curve exists, handling both legacy and slotted APIs.
    
    - Pre-4.4: uses action.fcurves.
    - 4.4+/5.0: uses action.fcurve_ensure_for_datablock when available.
    """
    # Newer API: let Blender choose correct slot/channelbag for this datablock
    if hasattr(action, "fcurve_ensure_for_datablock"):
        try:
            return action.fcurve_ensure_for_datablock(
                datablock, data_path, index=index, group_name=group_name or None
            )
        except TypeError:
            # Older signature without group_name
            return action.fcurve_ensure_for_datablock(datablock, data_path, index=index)
    
    # Legacy fallback: operate directly on action.fcurves
    if hasattr(action, "fcurves"):
        for fc in action.fcurves:
            if fc.data_path == data_path and fc.array_index == index:
                return fc
        return action.fcurves.new(data_path=data_path, index=index)
    
    return None


def _resolve_slot_identifier(slot):
    """Return a stable identifier for an ActionSlot (identifier or name)."""
    if not slot:
        return None
    return getattr(slot, "identifier", None) or getattr(slot, "name", None)


def parse_action_enum(value):
    """Parse an enum value like 'ActionName|SlotId' into (Action, slot_id)."""
    if not value or value == "NONE":
        return None, None
    parts = value.split("|", 1)
    action = bpy.data.actions.get(parts[0])
    slot_id = parts[1] if len(parts) > 1 else None
    return action, slot_id


def _collect_actions_for_object(obj):
    """Collect unique action names used by the object and its shape keys."""
    actions = set()
    if not obj:
        return actions

    # Object-level animation
    if obj.animation_data:
        if obj.animation_data.nla_tracks:
            for track in obj.animation_data.nla_tracks:
                for strip in track.strips:
                    if strip.action:
                        actions.add(strip.action.name)
        if obj.animation_data.action:
            actions.add(obj.animation_data.action.name)

    # Shape-key animation
    if (obj.data and hasattr(obj.data, 'shape_keys') and
        obj.data.shape_keys and obj.data.shape_keys.animation_data):
        sk_anim = obj.data.shape_keys.animation_data
        if sk_anim.nla_tracks:
            for track in sk_anim.nla_tracks:
                for strip in track.strips:
                    if strip.action:
                        actions.add(strip.action.name)
        if sk_anim.action:
            actions.add(sk_anim.action.name)

    return actions


def get_action_slot_enum_items_for_object(obj):
    """
    Build enum items for all (action, slot) combinations on this object.
    - For legacy actions (no slots): one entry per action.
    - For slotted actions: one entry per slot, labelled 'Action (Slot)'.
    """
    items = []
    actions = _collect_actions_for_object(obj)
    if not actions:
        items.append(("NONE", "No actions found", ""))
        return items

    for action_name in sorted(actions):
        action = bpy.data.actions.get(action_name)
        if not action:
            continue

        slots = getattr(action, "slots", None)
        if slots:
            for slot in slots:
                slot_id = _resolve_slot_identifier(slot)
                slot_label = getattr(slot, "name", "") or (slot_id or "")
                label = f"{action.name} ({slot_label})" if slot_label else action.name
                identifier = f"{action.name}|{slot_id}" if slot_id is not None else action.name
                items.append((identifier, label, ""))
        else:
            # Legacy / non-slotted action
            items.append((action.name, action.name, ""))

    return items


def get_action_fcurves_for_slot(action, slot_identifier, datablock=None):
    """
    Retrieve F-Curves for a specific slot of an Action.
    - If slot_identifier is None, falls back to get_action_fcurves.
    - On slotted actions, restricts to the chosen slot's channelbag(s).
    """
    # No explicit slot requested: use existing helper
    if not slot_identifier:
        return get_action_fcurves(action, datablock=datablock)

    # Legacy / non-slotted actions
    if not hasattr(action, "slots"):
        return get_action_fcurves(action, datablock=datablock)

    # Find the matching slot on this action
    slot = None
    for s in action.slots:
        if _resolve_slot_identifier(s) == slot_identifier:
            slot = s
            break

    if slot is None:
        # Fallback: default behavior
        return get_action_fcurves(action, datablock=datablock)

    fcurves = []
    # Prefer layered/channelbag API when available
    if hasattr(action, "layers"):
        for layer in action.layers:
            for strip in layer.strips:
                channelbag = getattr(strip, "channelbag", None)
                if callable(channelbag):
                    bag = channelbag(slot, ensure=False)
                    if bag:
                        fcurves.extend(getattr(bag, "fcurves", []))
                elif hasattr(strip, "channelbags"):
                    # Older layered API with channelbags collection
                    for bag in strip.channelbags:
                        bag_slot = getattr(bag, "slot", None)
                        if _resolve_slot_identifier(bag_slot) == slot_identifier:
                            fcurves.extend(getattr(bag, "fcurves", []))

    # If nothing found via channelbags, fall back to generic helper
    if not fcurves:
        return get_action_fcurves(action, datablock=datablock)

    return fcurves
def is_shape_key_action(obj, action):
    """Check if an action belongs to shape keys of the given object."""
    if not obj or not action:
        return False
    if not (obj.data and hasattr(obj.data, 'shape_keys') and obj.data.shape_keys):
        return False
    
    sk = obj.data.shape_keys
    if not sk.animation_data:
        return False
    
    # Check active action
    if sk.animation_data.action == action:
        return True
    
    # Check NLA tracks
    if hasattr(sk.animation_data, 'nla_tracks'):
        for track in sk.animation_data.nla_tracks:
            for strip in track.strips:
                if strip.action == action:
                    return True
    return False

def select_weighted_index(weights):
    """Select a random index based on normalized weights."""
    if len(weights) == 1:
        return 0
    r = random.random()
    cumulative = 0.0
    for i, w in enumerate(weights):
        cumulative += w
        if r <= cumulative:
            return i
    return len(weights) - 1


def is_fcurve_constant(fcurve, tolerance=1e-6):
    """
    Check if an F-Curve has effectively no variation in value.
    Returns True if all keyframe values are identical (within tolerance).
    """
    if not fcurve or not fcurve.keyframe_points:
        return True

    if len(fcurve.keyframe_points) == 1:
        return True

    first_value = fcurve.keyframe_points[0].co[1]
    for kp in fcurve.keyframe_points:
        if abs(kp.co[1] - first_value) > tolerance:
            return False

    return True


def simplify_fcurve(fcurve, tolerance=0.001):
    """
    Remove redundant keyframes from an F-Curve.
    """
    if tolerance <= 0:
        return 0
    
    points = fcurve.keyframe_points
    if len(points) <= 2:
        return 0
    
    to_remove = []
    
    for i in range(1, len(points) - 1):
        kf = points[i]
        if kf.interpolation != 'BEZIER':
            continue
        if kf.handle_left_type not in {'AUTO', 'AUTO_CLAMPED', 'VECTOR'}:
            continue
        if kf.handle_right_type not in {'AUTO', 'AUTO_CLAMPED', 'VECTOR'}:
            continue
        
        prev = points[i - 1]
        next = points[i + 1]
        frame_range = next.co.x - prev.co.x
        if frame_range == 0:
            continue
        t = (kf.co.x - prev.co.x) / frame_range
        linear_value = prev.co.y + t * (next.co.y - prev.co.y)
        
        if abs(kf.co.y - linear_value) < tolerance:
            to_remove.append(i)
    
    removed = len(to_remove)
    if removed:
        for i in reversed(to_remove):
            points.remove(points[i], fast=True)
        fcurve.update()
    
    return removed

def update_bpm_curve(self, context):
    """Clear parsed BPM data when curve is removed"""
    if not self.bpm_curve:
        if "variable_playback_time_rate_pairs" in context.scene:
            del context.scene["variable_playback_time_rate_pairs"]

def update_strength_curve(self, context):
    """Clear parsed strength data when curve is removed"""
    if not self.strength_curve:
        if "variable_playback_strength_influence_pairs" in context.scene:
            del context.scene["variable_playback_strength_influence_pairs"]

# ============================================================================ #
# PROPERTY GROUPS
# ============================================================================ #

class AnimationSlot(PropertyGroup):
    """Individual animation slot for weighted random selection."""
    
    action: EnumProperty(
        name="Action",
        description="Select action for this slot",
        items=lambda self, context: self.get_action_items(context)
    )
    
    weight: FloatProperty(
        name="Weight %",
        description="Probability weight for this animation",
        default=100.0,
        min=0.0,
        max=100.0,
        subtype='PERCENTAGE'
    )
    
    def get_action_items(self, context):
        props = context.scene.variable_playback_props
        if not props or not props.source_object:
            return [("NONE", "No object selected", "")]
        return get_action_slot_enum_items_for_object(props.source_object)


class VariablePlaybackProps(PropertyGroup):
    source_object: PointerProperty(
        name="Source Object",
        type=bpy.types.Object,
        description="Object containing the cyclic actions to bake"
    )
    
    source_action: EnumProperty(
        name="Source Action",
        description="Select action to remap",
        items=lambda self, context: self.get_action_items(context)
    )
    
    # Multiple animation mode
    use_multiple_animations: BoolProperty(
        name="Use Multiple Animations",
        description="Enable weighted random selection between animations",
        default=False
    )
    
    animation_slots: CollectionProperty(type=AnimationSlot)
    animation_slots_index: IntProperty(default=0)
    
    bpm_curve: PointerProperty(
        name="BPM Curve",
        type=bpy.types.Object,
        description="Curve object with X=time(min), Y=rate(BPM)",
        update=update_bpm_curve
    )
    
    strength_curve: PointerProperty(
        name="Strength Curve",
        type=bpy.types.Object,
        description="Curve object with X=time(min), Y=influence (1m = 100%)",
        update=update_strength_curve
    )

    # Random Intensity Controls
    use_random_intensity: BoolProperty(
        name="Random Intensity per Loop",
        description="Apply a random intensity multiplier to each loop cycle for extra variation",
        default=False
    )

    random_intensity_seed: IntProperty(
        name="Intensity Seed",
        description="Seed for random intensity generation (0 = random each time)",
        default=0,
        min=0
    )

    random_intensity_min: FloatProperty(
        name="Min",
        description="Minimum random intensity multiplier",
        default=0.8,
        min=0.0,
        max=10.0,
        soft_min=0.1,
        soft_max=2.0
    )

    random_intensity_max: FloatProperty(
        name="Max",
        description="Maximum random intensity multiplier",
        default=1.2,
        min=0.0,
        max=10.0,
        soft_min=0.1,
        soft_max=2.0
    )

    # Random Speed Controls (uses seed+1)
    use_random_speed: BoolProperty(
        name="Random Speed per Loop",
        description="Randomly multiply playback speed for each loop cycle",
        default=False
    )

    random_speed_min: FloatProperty(
        name="Min",
        description="Minimum random speed multiplier",
        default=0.8,
        min=0.1,
        max=3.0,
        soft_min=0.5,
        soft_max=2.0
    )

    random_speed_max: FloatProperty(
        name="Max",
        description="Maximum random speed multiplier",
        default=1.2,
        min=0.1,
        max=3.0,
        soft_min=0.5,
        soft_max=2.0
    )

    bake_speed_scale: FloatProperty(
        name="Baked Speed",
        description="Global speed multiplier for the baked animation (1.0 = original, >1.0 = faster, <1.0 = slower)",
        default=1.0,
        min=0.05,
        soft_min=0.1,
        soft_max=2.0
    )
    
    simplify_tolerance: FloatProperty(
        name="Simplify F-Curve Tolerance",
        description="Remove keyframes deviating less than this from linear. 0 = disabled",
        default=0.001,
        min=0.0,
        soft_min=0.0001,
        soft_max=0.1,
        precision=4
    )
    
    def get_action_items(self, context):
        if not self.source_object:
            return [("NONE", "No object selected", "")]
        return get_action_slot_enum_items_for_object(self.source_object)


# ============================================================================ #
# UI PANEL
# ============================================================================ #

class VARIABLEPLAYBACK_PT_panel(Panel):
    bl_label = "Variable Playback Baker"
    bl_idname = "VARIABLEPLAYBACK_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Animation"
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.variable_playback_props
        
        layout.prop(props, "source_object", icon='OBJECT_DATA')
        
        has_anim_data = False
        if props.source_object:
            if props.source_object.animation_data: 
                has_anim_data = True
            if (props.source_object.data and hasattr(props.source_object.data, 'shape_keys') and
                props.source_object.data.shape_keys and props.source_object.data.shape_keys.animation_data):
                has_anim_data = True
        
        if props.source_object and has_anim_data:
            # Multiple animation toggle
            row = layout.row(align=True)
            row.prop(props, "use_multiple_animations", icon='RADIOBUT_ON', text="Multi-Animation Mode")
            
            if props.use_multiple_animations:
                box = layout.box()
                box.label(text="Animation Slots", icon='ANIM')
                
                # Total weight indicator
                total_weight = sum(slot.weight for slot in props.animation_slots)
                if abs(total_weight - 100.0) > 0.1:
                    box.label(text=f"Total: {total_weight:.1f}%", icon='ERROR')
                else:
                    box.label(text=f"Total: 100%", icon='CHECKMARK')
                
                # Slots list
                for i, slot in enumerate(props.animation_slots):
                    row = box.row(align=True)
                    row.prop(slot, "action", text=f"#{i+1}")
                    row.prop(slot, "weight", text="")
                
                # Add/Remove buttons
                row = box.row(align=True)
                row.operator("variable_playback.add_slot", icon='ADD')
                row.operator("variable_playback.remove_slot", icon='REMOVE')
                
                # Disable single action selector
                layout.label(text="Single action disabled in multi-mode", icon='INFO')
            else:
                # Original single action UI
                layout.prop(props, "source_action", icon='ACTION')
                if props.source_action and props.source_action != "NONE":
                    action, slot_id = parse_action_enum(props.source_action)
                    if action:
                        # Determine target datablock (object or shape keys)
                        target_db = (props.source_object.data.shape_keys if 
                                     is_shape_key_action(props.source_object, action) 
                                     else props.source_object)
                        
                        # Get fcurves for the SPECIFIC SLOT, not the entire action
                        slot_fcurves = get_action_fcurves_for_slot(action, slot_id, datablock=target_db)
                        
                        # Calculate frame range from slot's actual keyframes
                        fr = (0, 0)
                        if slot_fcurves:
                            min_frame = float('inf')
                            max_frame = -float('inf')
                            for fc in slot_fcurves:
                                if fc.keyframe_points:
                                    for kp in fc.keyframe_points:
                                        frame = kp.co.x
                                        if frame < min_frame:
                                            min_frame = frame
                                        if frame > max_frame:
                                            max_frame = frame
                            if min_frame != float('inf'):
                                fr = (min_frame, max_frame)
                        
                        # Fallback to action range if slot has no keyframes
                        if fr == (0, 0):
                            if hasattr(action, "frame_range"): fr = action.frame_range
                            elif hasattr(action, "curve_frame_range"): fr = action.curve_frame_range
                            else: fr = (0,0)

                        col = layout.column(align=True)
                        col.label(text=f"Frames: {fr[0]:.0f} - {fr[1]:.0f}", icon='TIME')
                        dur = (fr[1] - fr[0]) / context.scene.render.fps if context.scene.render.fps else 0
                        col.label(text=f"Base Duration: {dur:.2f}s", icon='PLAY')  # Fixed: was fr[2]
        else:
            layout.label(text="Select an object with animation data", icon='INFO')
        
        layout.separator()
        layout.prop(props, "bpm_curve", icon='CURVE_DATA')
        
        box = layout.box()
        box.label(text="Output Frame Range", icon='PREVIEW_RANGE')
        col = box.column(align=True)
        col.prop(context.scene, "frame_start", text="Start")
        col.prop(context.scene, "frame_end", text="End")
        
        if "variable_playback_time_rate_pairs" in context.scene:
            pairs = context.scene["variable_playback_time_rate_pairs"]
            box = layout.box()
            box.label(text=f"Data Loaded: {len(pairs)} points", icon='CHECKMARK')
            if len(pairs) > 0:
                col = box.column(align=True)
                col.label(text="First points:", icon='DOT')
                for i in range(min(3, len(pairs))):
                    t, bpm = pairs[i]
                    col.label(text=f"  t={t:.2f}s, BPM={bpm:.1f}")
        
        col = layout.column(align=True)
        col.operator("variable_playback.read_curve", icon='IMPORT')
        
        layout.separator()
        layout.prop(props, "strength_curve", icon='CURVE_DATA')

        if "variable_playback_strength_influence_pairs" in context.scene:
            strength_pairs = context.scene["variable_playback_strength_influence_pairs"]
            box = layout.box()
            box.label(text=f"Strength Data: {len(strength_pairs)} points", icon='CHECKMARK')
            if len(strength_pairs) > 0:
                strength_col = box.column(align=True)
                strength_col.label(text="First points:", icon='DOT')
                for i in range(min(3, len(strength_pairs))):
                    t, influence = strength_pairs[i]
                    strength_col.label(text=f"  t={t:.2f}s, Influence={influence:.1%}")

        strength_col = layout.column(align=True)
        strength_col.operator("variable_playback.read_strength_curve", icon='IMPORT')

        layout.separator()
        box = layout.box()
        box.label(text="Random Intensity per Loop", icon='SHADERFX')
        col = box.column(align=True)
        col.prop(props, "use_random_intensity", text="Enable")
        if props.use_random_intensity:
            col.prop(props, "random_intensity_seed", text="Seed")
            row = col.row(align=True)
            row.prop(props, "random_intensity_min", text="Min")
            row.prop(props, "random_intensity_max", text="Max")
        # Random Speed UI
        box = layout.box()
        box.label(text="Random Speed per Loop", icon='TIME')
        col = box.column(align=True)
        col.prop(props, "use_random_speed", text="Enable")
        if props.use_random_speed:
            if props.random_intensity_seed == 0:
                col.label(text="Set Intensity Seed > 0 to lock speed seed", icon='ERROR')
            else:
                col.label(text=f"Uses seed: {props.random_intensity_seed + 1}", icon='INFO')
            row = col.row(align=True)
            row.prop(props, "random_speed_min", text="Min")
            row.prop(props, "random_speed_max", text="Max")
        layout.prop(props, "bake_speed_scale", slider=True)
        
        col = layout.column(align=True)
        col.prop(props, "simplify_tolerance", slider=True)
        col.label(text="0 = disabled • Higher = fewer keyframes", icon='INFO')
        
        col = layout.column(align=True)
        row = col.row(align=True)
        row.operator("variable_playback.preview", icon='MONKEY')
        row.enabled = "variable_playback_time_rate_pairs" in context.scene
        row = col.row(align=True)
        row.operator("variable_playback.bake", icon='REC')
        row.enabled = "variable_playback_time_rate_pairs" in context.scene


# ============================================================================ #
# OPERATORS
# ============================================================================ #

class VARIABLEPLAYBACK_OT_read_curve(Operator):
    """Read BPM/time data from selected curve by converting to mesh"""
    bl_idname = "variable_playback.read_curve"
    bl_label = "Read BPM Data"
    bl_description = "Duplicate curve, convert to mesh, and read high-res data"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        props = context.scene.variable_playback_props
        
        if not props.bpm_curve:
            self.report({'ERROR'}, "No BPM curve selected")
            return {'CANCELLED'}
            
        src_obj = props.bpm_curve
        if src_obj.type != 'CURVE':
            self.report({'ERROR'}, "Selected object is not a curve")
            return {'CANCELLED'}

        prev_active = context.view_layer.objects.active
        prev_selected = context.selected_objects
        
        temp_obj = None
        temp_mesh = None
        
        try:
            temp_obj = src_obj.copy()
            temp_obj.data = src_obj.data.copy() 
            context.scene.collection.objects.link(temp_obj)
            
            bpy.ops.object.select_all(action='DESELECT')
            temp_obj.select_set(True)
            context.view_layer.objects.active = temp_obj
            
            bpy.ops.object.convert(target='MESH')
            
            mesh = temp_obj.data
            temp_mesh = mesh
            verts = mesh.vertices
            
            if len(verts) < 2:
                self.report({'ERROR'}, "Curve resolved to fewer than 2 vertices")
                return {'CANCELLED'}
            
            IMPORT_X_SCALE = 1 / 60.0
            IMPORT_Y_SCALE = 1 / 100.0
            
            time_rate_pairs = []
            for v in verts:
                x, y = v.co.x, v.co.y
                time_seconds = x / IMPORT_X_SCALE
                bpm = y / IMPORT_Y_SCALE
                if time_seconds >= 0:
                    time_rate_pairs.append((time_seconds, bpm))
            
            time_rate_pairs.sort(key=lambda k: k[0])
            
            # Remove duplicates
            clean_pairs = []
            last_t = -1.0
            for t, bpm in time_rate_pairs:
                if t > last_t:
                    clean_pairs.append((t, bpm))
                    last_t = t
            
            context.scene["variable_playback_time_rate_pairs"] = clean_pairs
            self.report({'INFO'}, f"Sampled {len(clean_pairs)} points from curve.")
            
        except Exception as e:
            self.report({'ERROR'}, f"Error processing curve: {str(e)}")
            return {'CANCELLED'}
            
        finally:
            if temp_obj:
                bpy.data.objects.remove(temp_obj, do_unlink=True)
            if temp_mesh:
                bpy.data.meshes.remove(temp_mesh, do_unlink=True)
            
            if prev_selected:
                for obj in prev_selected:
                    try: obj.select_set(True)
                    except: pass
            if prev_active:
                context.view_layer.objects.active = prev_active

        return {'FINISHED'}


class VARIABLEPLAYBACK_OT_read_strength_curve(Operator):
    """Read strength/influence data from selected curve by converting to mesh"""
    bl_idname = "variable_playback.read_strength_curve"
    bl_label = "Read Strength Data"
    bl_description = "Duplicate curve, convert to mesh, and read high-res influence data (1m = 100%)"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        props = context.scene.variable_playback_props
        
        if not props.strength_curve:
            self.report({'ERROR'}, "No strength curve selected")
            return {'CANCELLED'}
            
        src_obj = props.strength_curve
        if src_obj.type != 'CURVE':
            self.report({'ERROR'}, "Selected object is not a curve")
            return {'CANCELLED'}

        prev_active = context.view_layer.objects.active
        prev_selected = context.selected_objects
        
        temp_obj = None
        temp_mesh = None
        
        try:
            temp_obj = src_obj.copy()
            temp_obj.data = src_obj.data.copy() 
            context.scene.collection.objects.link(temp_obj)
            
            bpy.ops.object.select_all(action='DESELECT')
            temp_obj.select_set(True)
            context.view_layer.objects.active = temp_obj
            
            bpy.ops.object.convert(target='MESH')
            
            mesh = temp_obj.data
            temp_mesh = mesh
            verts = mesh.vertices
            
            if len(verts) < 2:
                self.report({'ERROR'}, "Curve resolved to fewer than 2 vertices")
                return {'CANCELLED'}
            
            IMPORT_X_SCALE = 1 / 60.0
            # 1m = 100% influence = 1.0, so scale factor is 1.0
            
            time_influence_pairs = []
            for v in verts:
                x, y = v.co.x, v.co.y
                time_seconds = x / IMPORT_X_SCALE
                influence = max(y, 0.0)  # Clamp negative values to 0
                if time_seconds >= 0:
                    time_influence_pairs.append((time_seconds, influence))
            
            time_influence_pairs.sort(key=lambda k: k[0])
            
            # Remove duplicates
            clean_pairs = []
            last_t = -1.0
            for t, influence in time_influence_pairs:
                if t > last_t:
                    clean_pairs.append((t, influence))
                    last_t = t
            
            context.scene["variable_playback_strength_influence_pairs"] = clean_pairs
            self.report({'INFO'}, f"Sampled {len(clean_pairs)} strength points from curve.")
            
        except Exception as e:
            self.report({'ERROR'}, f"Error processing strength curve: {str(e)}")
            return {'CANCELLED'}
            
        finally:
            if temp_obj:
                bpy.data.objects.remove(temp_obj, do_unlink=True)
            if temp_mesh:
                bpy.data.meshes.remove(temp_mesh, do_unlink=True)
            
            if prev_selected:
                for obj in prev_selected:
                    try: obj.select_set(True)
                    except: pass
            if prev_active:
                context.view_layer.objects.active = prev_active

        return {'FINISHED'}


class VARIABLEPLAYBACK_OT_preview(Operator):
    """Create preview visualization showing phase and rate"""
    bl_idname = "variable_playback.preview"
    bl_label = "Preview"
    bl_description = "Create empty that visualizes loop phase (X), rate (Y), and active animation (Z)"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        props = context.scene.variable_playback_props
        pairs = context.scene.get("variable_playback_time_rate_pairs")
        speed_scale = getattr(props, "bake_speed_scale", 1.0)
        
        if not pairs:
            self.report({'ERROR'}, "No curve data loaded")
            return {'CANCELLED'}
        
        # Setup action data
        if props.use_multiple_animations:
            action_data_list = []
            total_weight = 0.0
            for slot in props.animation_slots:
                if slot.action and slot.action != "NONE":
                    action, slot_id = parse_action_enum(slot.action)
                    if action:
                        action_data_list.append({
                            'action': action,
                            'slot_id': slot_id,
                            'weight': slot.weight
                        })
                        total_weight += slot.weight
            
            if not action_data_list:
                self.report({'ERROR'}, "No valid actions selected")
                return {'CANCELLED'}
            
            # Normalize
            for data in action_data_list:
                data['normalized_weight'] = data['weight'] / total_weight
        else:
            src_action, src_slot_id = parse_action_enum(props.source_action)
            if not src_action:
                self.report({'ERROR'}, "Action not found")
                return {'CANCELLED'}
            action_data_list = [{
                'action': src_action,
                'slot_id': src_slot_id,
                'weight': 100.0,
                'normalized_weight': 1.0
            }]
        
        # Create preview object
        name = "VariablePlayback_Preview"
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
        
        bpy.ops.object.empty_add()
        preview_obj = context.active_object
        preview_obj.name = name
        preview_obj.empty_display_size = 2.0
        
        # Create action
        action_name = "VariablePlayback_Preview_Action"
        if action_name in bpy.data.actions:
            bpy.data.actions.remove(bpy.data.actions[action_name])
        
        preview_action = bpy.data.actions.new(name=action_name)
        if not preview_obj.animation_data:
            preview_obj.animation_data_create()
        preview_obj.animation_data.action = preview_action
        
        # Create curves (let Blender choose correct slot/channelbag for preview_obj)
        phase_fcurve = ensure_fcurve(preview_action, preview_obj, "location", 0)
        rate_fcurve = ensure_fcurve(preview_action, preview_obj, "location", 1)
        idx_fcurve = ensure_fcurve(preview_action, preview_obj, "location", 2)
        
        if not all([phase_fcurve, rate_fcurve, idx_fcurve]):
            self.report({'ERROR'}, "Could not create F-Curves")
            return {'CANCELLED'}
        
        # Prepare weighted selection
        cumulative_weights = []
        cw = 0.0
        for data in action_data_list:
            cw += data['normalized_weight']
            cumulative_weights.append(cw)
        
        def select_action():
            if len(action_data_list) == 1:
                return 0
            r = random.random()
            for i, cw in enumerate(cumulative_weights):
                if r <= cw:
                    return i
            return len(action_data_list) - 1
        
        # Sample animation
        def sample_bpm(time_seconds):
            if time_seconds <= pairs[0][0]: return pairs[0][1]
            if time_seconds >= pairs[-1][0]: return pairs[-1][1]
            for i in range(len(pairs) - 1):
                t0, bpm0 = pairs[i]
                t1, bpm1 = pairs[i + 1]
                if t0 <= time_seconds <= t1:
                    factor = (time_seconds - t0) / (t1 - t0)
                    return bpm0 + factor * (bpm1 - bpm0)
            return pairs[-1][1]
        
        fps = context.scene.render.fps
        phase = 0.0
        frame_start = context.scene.frame_start
        frame_end = context.scene.frame_end
        current_action_idx = 0
        prev_normalized_phase = 0.0
        
        for frame in range(frame_start, frame_end + 1):
            t = frame / fps
            bpm = sample_bpm(t)
            rate = max(bpm, 0.0) / 60.0
            phase += rate * (1.0 / fps) * speed_scale
            
            normalized_phase = phase % 1.0
            
            # Detect phase wrap
            if frame == frame_start or normalized_phase < prev_normalized_phase:
                current_action_idx = select_action()
            
            # Insert keyframes
            phase_fcurve.keyframe_points.insert(frame, normalized_phase * 5.0, options={'FAST'})
            # Store effective rate (after speed scaling) in Y for clearer preview
            rate_fcurve.keyframe_points.insert(frame, min(rate * speed_scale, 2.0), options={'FAST'})
            idx_fcurve.keyframe_points.insert(frame, current_action_idx * 2.0, options={'FAST'})
            
            prev_normalized_phase = normalized_phase
        
        self.report({'INFO'}, f"Preview created: {name} (X=phase, Y=rate, Z=action_idx)")
        return {'FINISHED'}


class VARIABLEPLAYBACK_OT_bake(Operator):
    """Bake variable-rate animation with optional weighted random selection"""
    bl_idname = "variable_playback.bake"
    bl_label = "Bake"
    bl_description = "Bake variable playback into new action"
    bl_options = {'REGISTER', 'UNDO'}
    
    def sample_strength(self, time_seconds, strength_pairs):
        """Sample strength influence from time/influence pairs."""
        if not strength_pairs:
            return 1.0  # Default to 100% influence if no curve provided
        
        if time_seconds <= strength_pairs[0][0]: 
            return strength_pairs[0][1]
        if time_seconds >= strength_pairs[-1][0]: 
            return strength_pairs[-1][1]
        
        for i in range(len(strength_pairs) - 1):
            t0, inf0 = strength_pairs[i]
            t1, inf1 = strength_pairs[i + 1]
            if t0 <= time_seconds <= t1:
                factor = (time_seconds - t0) / (t1 - t0)
                return inf0 + factor * (inf1 - inf0)
        
        return strength_pairs[-1][1]
    
    def execute(self, context):
        props = context.scene.variable_playback_props
        pairs = context.scene.get("variable_playback_time_rate_pairs")
        strength_pairs = context.scene.get("variable_playback_strength_influence_pairs", [])
        speed_scale = getattr(props, "bake_speed_scale", 1.0)
        
        if not pairs:
            self.report({'ERROR'}, "No curve data loaded")
            return {'CANCELLED'}

        # Initialize random intensity generator
        intensity_rng = None
        speed_rng = None
        if props.use_random_intensity:
            if props.random_intensity_seed > 0:
                intensity_rng = random.Random(props.random_intensity_seed)
                self.report({'INFO'}, f"Using random intensity seed: {props.random_intensity_seed}")
            else:
                intensity_rng = random.Random()

        # Prepare random speed generator (seed+1)
        if props.use_random_speed:
            if props.random_intensity_seed > 0:
                speed_seed = props.random_intensity_seed + 1
                speed_rng = random.Random(speed_seed)
            else:
                speed_rng = random.Random()
        
        # Prepare action data
        if props.use_multiple_animations:
            if not props.animation_slots:
                self.report({'ERROR'}, "No animation slots defined")
                return {'CANCELLED'}
            
            action_data_list = []
            total_weight = 0.0
            
            for slot in props.animation_slots:
                if slot.action and slot.action != "NONE":
                    action, slot_id = parse_action_enum(slot.action)
                    if action:
                        target_db = (props.source_object.data.shape_keys if
                                     is_shape_key_action(props.source_object, action)
                                     else props.source_object)
                        fcurves = get_action_fcurves_for_slot(action, slot_id, datablock=target_db)
                        if not fcurves:
                            self.report({'WARNING'}, f"Action '{action.name}' has no curves for selected slot, skipping")
                            continue

                        # Store first-keyframe baseline values per F-Curve
                        base_values = {}
                        for fc in fcurves:
                            key = (fc.data_path, fc.array_index)
                            if fc.keyframe_points:
                                base_values[key] = fc.keyframe_points[0].co[1]
                            else:
                                base_values[key] = 0.0

                        is_sk = is_shape_key_action(props.source_object, action)
                        action_data_list.append({
                            'action': action,
                            'slot_id': slot_id,
                            'weight': slot.weight,
                            'fcurves': fcurves,
                            'is_shape_key': is_sk,
                            'base_values': base_values
                        })
                        total_weight += slot.weight
            
            if not action_data_list:
                self.report({'ERROR'}, "No valid actions selected")
                return {'CANCELLED'}
            
            if total_weight <= 0:
                self.report({'ERROR'}, "Total weight must be greater than 0")
                return {'CANCELLED'}
            
            # Normalize weights
            for data in action_data_list:
                data['normalized_weight'] = data['weight'] / total_weight
        else:
            # Single action mode
            src_action, src_slot_id = parse_action_enum(props.source_action)
            if not src_action:
                self.report({'ERROR'}, "Action not found")
                return {'CANCELLED'}
            
            target_db = (props.source_object.data.shape_keys if
                         is_shape_key_action(props.source_object, src_action)
                         else props.source_object)
            src_fcurves = get_action_fcurves_for_slot(src_action, src_slot_id, datablock=target_db)
            if not src_fcurves:
                self.report({'ERROR'}, "Action has no animation curves for selected slot")
                return {'CANCELLED'}

            # Store first-keyframe baseline values per F-Curve
            base_values = {}
            for fc in src_fcurves:
                key = (fc.data_path, fc.array_index)
                if fc.keyframe_points:
                    base_values[key] = fc.keyframe_points[0].co[1]
                else:
                    base_values[key] = 0.0

            is_sk = is_shape_key_action(props.source_object, src_action)
            action_data_list = [{
                'action': src_action,
                'slot_id': src_slot_id,
                'weight': 100.0,
                'normalized_weight': 1.0,
                'fcurves': src_fcurves,
                'is_shape_key': is_sk,
                'base_values': base_values
            }]
        
        # Verify all actions are same type (object or shape key)
        first_is_shape_key = action_data_list[0]['is_shape_key']
        for i, data in enumerate(action_data_list):
            if data['is_shape_key'] != first_is_shape_key:
                self.report({'ERROR'}, 
                    f"Action '{data['action'].name}' type mismatch. All animations must be same type (object or shape key)")
                return {'CANCELLED'}
        
        # Prepare target datablock
        target_datablock = (props.source_object.data.shape_keys if first_is_shape_key 
                           else props.source_object)
        
        # Create baked action
        suffix = "_ShapeKeys" if first_is_shape_key else ""

        if props.use_multiple_animations:
            # Multi-animation mode: ActionName_Blend_Baked
            highest_weight_data = max(action_data_list, key=lambda x: x['normalized_weight'])
            action_name = highest_weight_data['action'].name
            base_name = f"{action_name}_Blend_Baked"
        else:
            # Single animation mode: ActionName_SlotName_Baked
            action = action_data_list[0]['action']
            action_name = action.name
            slot_id = action_data_list[0]['slot_id']

            slot_name = ""
            if slot_id and hasattr(action, "slots") and action.slots:
                for slot in action.slots:
                    if _resolve_slot_identifier(slot) == slot_id:
                        slot_name = getattr(slot, "name", "") or slot_id
                        break

            if slot_name:
                base_name = f"{action_name}_{slot_name}_Baked"
            else:
                base_name = f"{action_name}_Baked"

        baked_name = base_name + suffix
        if baked_name in bpy.data.actions:
            bpy.data.actions.remove(bpy.data.actions[baked_name])
        
        baked_action = bpy.data.actions.new(name=baked_name)
        if not target_datablock.animation_data:
            target_datablock.animation_data_create()
        
        # Temporarily assign to create curves
        prev_action = target_datablock.animation_data.action
        target_datablock.animation_data.action = baked_action

        # Ensure the baked action's slot is named to match the action
        baked_slot = _get_action_slot_for_datablock(baked_action, target_datablock)
        if baked_slot is not None and hasattr(baked_slot, "name"):
            try:
                baked_slot.name = baked_action.name
            except Exception:
                pass
        
        # Pre-calculate action data and collect all data paths
        all_data_paths = set()
        for data in action_data_list:
            action = data['action']
            # Get frame range from slot-specific curves
            slot_fcurves = data['fcurves']
            src_start, src_end = (0, 100)  # defaults

            if slot_fcurves:
                min_frame = float('inf')
                max_frame = -float('inf')
                for fc in slot_fcurves:
                    if fc.keyframe_points:
                        for kp in fc.keyframe_points:
                            frame = kp.co.x
                            if frame < min_frame:
                                min_frame = frame
                            if frame > max_frame:
                                max_frame = frame
                if min_frame != float('inf'):
                    src_start, src_end = (min_frame, max_frame)

            # Fallback to action range if slot has no keyframes
            if src_start == 0 and src_end == 100:
                if hasattr(action, "frame_range"): 
                    src_start, src_end = action.frame_range
                elif hasattr(action, "curve_frame_range"): 
                    src_start, src_end = action.curve_frame_range

            src_duration = src_end - src_start
            if src_duration == 0:
                self.report({'ERROR'}, f"Action '{action.name}' slot has zero duration")
                return {'CANCELLED'}

            data['src_start'] = src_start
            data['src_end'] = src_end
            data['src_duration'] = src_duration
            
            # Collect data paths
            for fc in data['fcurves']:
                all_data_paths.add((fc.data_path, fc.array_index))
        
        # Create baked fcurves
        baked_fcurves = {}
        for dp, idx in all_data_paths:
            baked_fc = ensure_fcurve(baked_action, target_datablock, dp, idx)
            if baked_fc:
                baked_fcurves[(dp, idx)] = baked_fc
        
        # Prepare weighted selection
        cumulative_weights = []
        cw = 0.0
        for data in action_data_list:
            cw += data['normalized_weight']
            cumulative_weights.append(cw)
        
        fps = context.scene.render.fps
        frame_start = context.scene.frame_start
        frame_end = context.scene.frame_end
        frame_count = frame_end - frame_start + 1
        # Random multipliers tracking
        current_loop_intensity = 1.0
        current_loop_speed = 1.0
        
        # Precompute per-frame metadata (phase, selected action, source frame, influence)
        # Store as tuples (frame, src_frame, action_idx, influence) to avoid dict overhead.
        phase = 0.0
        prev_normalized_phase = 0.0
        current_action_idx = 0
        frame_data = []
        
        wm = context.window_manager
        wm.progress_begin(0, frame_count)
        
        for i, frame in enumerate(range(frame_start, frame_end + 1)):
            wm.progress_update(i)
            t = frame / fps
            bpm = self.sample_bpm(t, pairs)
            base_rate = max(bpm, 0.0) / 60.0
            adjusted_rate = base_rate * current_loop_speed
            phase += adjusted_rate * (1.0 / fps) * speed_scale
            
            normalized_phase = phase % 1.0
            influence = self.sample_strength(t, strength_pairs)
            
            # Detect phase wrap or first frame
            if frame == frame_start or normalized_phase < prev_normalized_phase:
                if props.use_random_intensity:
                    rng = intensity_rng if intensity_rng is not None else random
                    current_loop_intensity = rng.uniform(
                        props.random_intensity_min,
                        props.random_intensity_max
                    )

                if props.use_random_speed:
                    rng = speed_rng if speed_rng is not None else random
                    current_loop_speed = rng.uniform(
                        props.random_speed_min,
                        props.random_speed_max
                    )

                if props.use_multiple_animations and len(action_data_list) > 1:
                    r = random.random()
                    for idx, cw_val in enumerate(cumulative_weights):
                        if r <= cw_val:
                            current_action_idx = idx
                            break
                else:
                    current_action_idx = 0
            
            final_influence = influence * current_loop_intensity

            current_data = action_data_list[current_action_idx]
            src_frame = current_data['src_start'] + normalized_phase * current_data['src_duration']
            
            # (frame, src_frame, action_idx, influence)
            frame_data.append((frame, src_frame, current_action_idx, final_influence))
            
            prev_normalized_phase = normalized_phase
        
        tolerance = 1e-6
        
        # Build per-action fcurve lookup maps to avoid repeated scans
        for data in action_data_list:
            fc_map = {}
            for src_fc in data['fcurves']:
                fc_map[(src_fc.data_path, src_fc.array_index)] = src_fc
            data['fcurve_map'] = fc_map
        
        # For each destination curve, evaluate only where source data exists
        for (dp, idx), baked_fc in baked_fcurves.items():
            # Pre-cache source fcurves and base values per action index
            src_fc_per_action = {}
            base_val_per_action = {}
            for action_idx, data in enumerate(action_data_list):
                fc = data['fcurve_map'].get((dp, idx))
                if fc is not None:
                    src_fc_per_action[action_idx] = fc
                    base_val_per_action[action_idx] = data['base_values'].get((dp, idx), 0.0)
            
            # Collect frames that actually have a source curve
            # Each entry: (frame, src_frame, influence, action_idx, src_fc)
            relevant_frames = []
            for frame, src_frame, action_idx, influence in frame_data:
                src_fc = src_fc_per_action.get(action_idx)
                if src_fc is None:
                    continue
                relevant_frames.append((frame, src_frame, influence, action_idx, src_fc))
            
            if not relevant_frames:
                continue
            
            count = len(relevant_frames)
            baked_fc.keyframe_points.add(count)
            
            # Build flat arrays and push to Blender in one call for better performance
            frames_out = [0.0] * count
            values_out = [0.0] * count
            
            for i, (frame, src_frame, influence, action_idx, src_fc) in enumerate(relevant_frames):
                try:
                    base_value = src_fc.evaluate(src_frame)
                    first_value = base_val_per_action.get(action_idx, base_value)
                    delta = base_value - first_value
                    if abs(delta) < tolerance:
                        # No effective change from the first keyframe; leave value unscaled
                        final_value = base_value
                    else:
                        # Scale only the deviation from the first keyframe by strength
                        final_value = first_value + delta * influence
                    frames_out[i] = frame
                    values_out[i] = final_value
                except Exception:
                    # Skip problematic points but continue baking
                    continue
            
            # Interleave frames and values: [f0, v0, f1, v1, ...]
            co_flat = [coord for pair in zip(frames_out, values_out) for coord in pair]
            baked_fc.keyframe_points.foreach_set("co", co_flat)
        
        wm.progress_end()

        # === SIMPLIFICATION PASS ===
        if props.simplify_tolerance > 0:
            total_removed = 0
            baked_fcurves_list = get_action_fcurves(baked_action, target_datablock)
            for fcurve in baked_fcurves_list:
                removed = simplify_fcurve(fcurve, props.simplify_tolerance)
                total_removed += removed
            
            if total_removed > 0:
                print(f"VariablePlayback: Simplified {total_removed} redundant keyframes")

        target_datablock.animation_data.action = prev_action  # Restore previous action
        baked_action.use_fake_user = True

        mode_msg = []
        if props.use_multiple_animations:
            mode_msg.append("multiple animations")
        if props.use_random_intensity:
            mode_msg.append("random intensity")
        if props.use_random_speed:
            mode_msg.append("random speed")
        mode_str = " + ".join(mode_msg) or "single animation"
        self.report({'INFO'}, f"Baked {frame_end - frame_start + 1} frames to '{baked_name}' ({mode_str})")
        return {'FINISHED'}
    
    def sample_bpm(self, time_seconds, pairs):
        """Sample BPM from time/rate pairs."""
        if time_seconds <= pairs[0][0]: return pairs[0][1]
        if time_seconds >= pairs[-1][0]: return pairs[-1][1]
        for i in range(len(pairs) - 1):
            t0, bpm0 = pairs[i]
            t1, bpm1 = pairs[i + 1]
            if t0 <= time_seconds <= t1:
                factor = (time_seconds - t0) / (t1 - t0)
                return bpm0 + factor * (bpm1 - bpm0)
        return pairs[-1][1]


class VARIABLEPLAYBACK_OT_add_slot(Operator):
    """Add a new animation slot for weighted random selection"""
    bl_idname = "variable_playback.add_slot"
    bl_label = "Add Animation Slot"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        props = context.scene.variable_playback_props
        slot = props.animation_slots.add()
        slot.weight = 100.0 / max(len(props.animation_slots), 1)
        return {'FINISHED'}


class VARIABLEPLAYBACK_OT_remove_slot(Operator):
    """Remove the last animation slot"""
    bl_idname = "variable_playback.remove_slot"
    bl_label = "Remove Animation Slot"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        props = context.scene.variable_playback_props
        if props.animation_slots:
            props.animation_slots.remove(len(props.animation_slots) - 1)
            # Redistribute weights
            if props.animation_slots:
                equal_weight = 100.0 / len(props.animation_slots)
                for slot in props.animation_slots:
                    slot.weight = equal_weight
        return {'FINISHED'}


# ============================================================================ #
# REGISTRATION
# ============================================================================ #

classes = (
    AnimationSlot,
    VariablePlaybackProps,
    VARIABLEPLAYBACK_PT_panel,
    VARIABLEPLAYBACK_OT_read_curve,
    VARIABLEPLAYBACK_OT_read_strength_curve,
    VARIABLEPLAYBACK_OT_preview,
    VARIABLEPLAYBACK_OT_bake,
    VARIABLEPLAYBACK_OT_add_slot,
    VARIABLEPLAYBACK_OT_remove_slot,
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
