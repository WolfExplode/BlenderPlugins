import bpy
import random
from bpy.props import PointerProperty, EnumProperty, BoolProperty, FloatProperty, CollectionProperty, IntProperty
from bpy.types import PropertyGroup, Operator, Panel

# ============================================================================ #
# HELPER FUNCTIONS (Blender 5.0 Compatibility)
# ============================================================================ #

def get_action_fcurves(action):
    """Retrieves F-Curves handling both legacy and Blender 5.0+ Layered Actions."""
    if hasattr(action, "fcurves"):
        return action.fcurves
    
    fcurves = []
    if hasattr(action, "layers"):
        for layer in action.layers:
            for strip in layer.strips:
                if hasattr(strip, "channelbags"):
                    for bag in strip.channelbags:
                        fcurves.extend(bag.fcurves)
                elif hasattr(strip, "fcurves"):
                    fcurves.extend(strip.fcurves)
    return fcurves

def ensure_fcurve(action, datablock, data_path, index=0):
    """Creates/Ensures an F-Curve exists, handling API differences."""
    if hasattr(action, "fcurves"):
        for fc in action.fcurves:
            if fc.data_path == data_path and fc.array_index == index:
                return fc
        return action.fcurves.new(data_path=data_path, index=index)
    
    if hasattr(action, "fcurve_ensure_for_datablock"):
        return action.fcurve_ensure_for_datablock(datablock, data_path, index=index)
    return None

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
        items = []
        props = context.scene.variable_playback_props
        if not props or not props.source_object:
            items.append(("NONE", "No object selected", ""))
            return items
        
        obj = props.source_object
        actions = set()
        
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
        
        if actions:
            for action_name in sorted(actions):
                items.append((action_name, action_name, ""))
        else:
            items.append(("NONE", "No actions found", ""))
        return items


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
        description="Curve object with X=time(min), Y=rate(BPM)"
    )
    
    strength_curve: PointerProperty(
        name="Strength Curve",
        type=bpy.types.Object,
        description="Curve object with X=time(min), Y=influence (1m = 100%)"
    )
    
    speed_multiplier: FloatProperty(
        name="Speed Multiplier",
        description="Additional multiplier for playback speed (100% = normal, 200% = double)",
        default=100.0,
        min=0.0,
        max=1000.0,
        subtype='PERCENTAGE'
    )
    
    def get_action_items(self, context):
        items = []
        if not self.source_object:
            items.append(("NONE", "No object selected", ""))
            return items
        
        actions = set()
        obj = self.source_object
        
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
        
        if actions:
            for action_name in sorted(actions):
                items.append((action_name, action_name, ""))
        else:
            items.append(("NONE", "No actions found", ""))
        return items


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
                    action = bpy.data.actions.get(props.source_action)
                    if action:
                        col = layout.column(align=True)
                        if hasattr(action, "frame_range"): fr = action.frame_range
                        elif hasattr(action, "curve_frame_range"): fr = action.curve_frame_range
                        else: fr = (0,0)
                        
                        col.label(text=f"Frames: {fr[0]:.0f} - {fr[1]:.0f}", icon='TIME')
                        dur = (fr[1] - fr[0]) / context.scene.render.fps if context.scene.render.fps else 0
                        col.label(text=f"Duration: {dur:.2f}s", icon='PLAY')
        else:
            layout.label(text="Select an object with animation data", icon='INFO')
        
        layout.separator()
        layout.prop(props, "bpm_curve", icon='CURVE_DATA')
        
        col = layout.column(align=True)
        col.prop(props, "speed_multiplier", icon='TIME')
        col.label(text="100% = Curve speed, 200% = Double speed", icon='INFO')
        
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
        rate_factor = props.speed_multiplier / 100.0
        
        if not pairs:
            self.report({'ERROR'}, "No curve data loaded")
            return {'CANCELLED'}
        
        # Setup action data
        if props.use_multiple_animations:
            action_data_list = []
            total_weight = 0.0
            for slot in props.animation_slots:
                if slot.action and slot.action != "NONE":
                    action = bpy.data.actions.get(slot.action)
                    if action:
                        action_data_list.append({
                            'action': action,
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
            src_action = bpy.data.actions.get(props.source_action)
            if not src_action:
                self.report({'ERROR'}, "Action not found")
                return {'CANCELLED'}
            action_data_list = [{
                'action': src_action,
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
        
        # Create curves
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
            rate = max(bpm, 0.0) / 60.0 * rate_factor
            phase += rate * (1.0 / fps)
            
            normalized_phase = phase % 1.0
            
            # Detect phase wrap
            if frame == frame_start or normalized_phase < prev_normalized_phase:
                current_action_idx = select_action()
            
            # Insert keyframes
            phase_fcurve.keyframe_points.insert(frame, normalized_phase * 5.0, options={'FAST'})
            rate_fcurve.keyframe_points.insert(frame, min(rate, 2.0), options={'FAST'})
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
        rate_factor = props.speed_multiplier / 100.0
        
        if not pairs:
            self.report({'ERROR'}, "No curve data loaded")
            return {'CANCELLED'}
        
        # Prepare action data
        if props.use_multiple_animations:
            if not props.animation_slots:
                self.report({'ERROR'}, "No animation slots defined")
                return {'CANCELLED'}
            
            action_data_list = []
            total_weight = 0.0
            
            for slot in props.animation_slots:
                if slot.action and slot.action != "NONE":
                    action = bpy.data.actions.get(slot.action)
                    if action:
                        fcurves = get_action_fcurves(action)
                        if not fcurves:
                            self.report({'WARNING'}, f"Action '{action.name}' has no curves, skipping")
                            continue
                        
                        is_sk = is_shape_key_action(props.source_object, action)
                        action_data_list.append({
                            'action': action,
                            'weight': slot.weight,
                            'fcurves': fcurves,
                            'is_shape_key': is_sk
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
            src_action = bpy.data.actions.get(props.source_action)
            if not src_action:
                self.report({'ERROR'}, "Action not found")
                return {'CANCELLED'}
            
            src_fcurves = get_action_fcurves(src_action)
            if not src_fcurves:
                self.report({'ERROR'}, "Action has no animation curves")
                return {'CANCELLED'}
            
            is_sk = is_shape_key_action(props.source_object, src_action)
            action_data_list = [{
                'action': src_action,
                'weight': 100.0,
                'normalized_weight': 1.0,
                'fcurves': src_fcurves,
                'is_shape_key': is_sk
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
        mode_suffix = "_Multi" if props.use_multiple_animations else ""
        baked_name = f"{props.source_object.name}_{action_data_list[0]['action'].name}_Baked{mode_suffix}{suffix}"
        if baked_name in bpy.data.actions:
            bpy.data.actions.remove(bpy.data.actions[baked_name])
        
        baked_action = bpy.data.actions.new(name=baked_name)
        if not target_datablock.animation_data:
            target_datablock.animation_data_create()
        
        # Temporarily assign to create curves
        prev_action = target_datablock.animation_data.action
        target_datablock.animation_data.action = baked_action
        
        # Pre-calculate action data and collect all data paths
        all_data_paths = set()
        for data in action_data_list:
            action = data['action']
            # Get frame range
            if hasattr(action, "frame_range"): 
                src_start, src_end = action.frame_range
            elif hasattr(action, "curve_frame_range"): 
                src_start, src_end = action.curve_frame_range
            else: 
                src_start, src_end = (0, 100)
            
            src_duration = src_end - src_start
            if src_duration == 0:
                self.report({'ERROR'}, f"Action '{action.name}' has zero duration")
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
        
        # Bake frames
        fps = context.scene.render.fps
        phase = 0.0
        frame_start = context.scene.frame_start
        frame_end = context.scene.frame_end
        current_action_idx = 0
        prev_normalized_phase = 0.0
        
        wm = context.window_manager
        wm.progress_begin(0, frame_end - frame_start)
        
        for frame in range(frame_start, frame_end + 1):
            wm.progress_update(frame - frame_start)
            t = frame / fps
            bpm = self.sample_bpm(t, pairs)
            rate = max(bpm, 0.0) / 60.0 * rate_factor
            phase += rate * (1.0 / fps)
            
            normalized_phase = phase % 1.0
            
            influence = self.sample_strength(t, strength_pairs)
            
            # Detect phase wrap or first frame
            if frame == frame_start or normalized_phase < prev_normalized_phase:
                # Select new action
                if props.use_multiple_animations and len(action_data_list) > 1:
                    r = random.random()
                    for i, cw in enumerate(cumulative_weights):
                        if r <= cw:
                            current_action_idx = i
                            break
            
            # Sample from current action
            current_data = action_data_list[current_action_idx]
            src_frame = current_data['src_start'] + normalized_phase * current_data['src_duration']
            
            for src_fc in current_data['fcurves']:
                key = (src_fc.data_path, src_fc.array_index)
                if key in baked_fcurves:
                    try:
                        base_value = src_fc.evaluate(src_frame)
                        final_value = base_value * influence
                        baked_fc = baked_fcurves[key]
                        baked_fc.keyframe_points.insert(frame, final_value, options={'FAST'})
                    except:
                        pass
            
            prev_normalized_phase = normalized_phase
        
        wm.progress_end()
        target_datablock.animation_data.action = prev_action  # Restore previous action
        baked_action.use_fake_user = True
        
        mode_msg = "multiple animations" if props.use_multiple_animations else "single animation"
        self.report({'INFO'}, f"Baked {frame_end - frame_start + 1} frames to '{baked_name}' ({mode_msg})")
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
