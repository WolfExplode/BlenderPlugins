bl_info = {
    "name": "my Shapekey Tools",
    "author": "WXP, Deepseek R1",
    "version": (1, 0, 2),
    "blender": (4, 1, 0),
    "location": "View3D > Sidebar > Tool",
    "description": "Tools for managing and transferring shape keys",
    "category": "Object"
}

import bpy
from bpy.types import Panel, Operator
from bpy.props import PointerProperty, EnumProperty

def show_message(message: str, title: str = "Message", icon: str = 'INFO'):
    def draw(self, context):
        self.layout.label(text=message)
    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)

def transfer_shape_key_values(source_obj_name, target_obj_name=None, target_collection=None, show_messages=True):
    """
    Transfer shape key values from source object to target object(s)
    Supports both single object and selected objects
    """
    source_obj = bpy.data.objects.get(source_obj_name)
    
    if not source_obj:
        if show_messages:
            show_message(f"Cannot find source object named '{source_obj_name}'!", "Error", 'ERROR')
        return
    
    targets = []
    if target_obj_name:
        target_obj = bpy.data.objects.get(target_obj_name)
        if target_obj:
            targets.append(target_obj)
    elif target_collection:
        targets = [obj for obj in target_collection.objects if obj.type == 'MESH']
    
    valid_targets = []
    for obj in targets:
        if obj and obj.data.shape_keys:
            valid_targets.append(obj)
    
    if not valid_targets:
        if show_messages:
            show_message("No valid targets found!", "Error", 'ERROR')
        return
    
    transferred_total = 0
    for target_obj in valid_targets:
        source_keys = source_obj.data.shape_keys.key_blocks
        target_keys = target_obj.data.shape_keys.key_blocks
        
        transferred = 0
        skipped = 0
        
        for source_key in source_keys:
            if source_key.name in target_keys:
                target_key = target_keys[source_key.name]
                target_key.value = source_key.value
                # Transfer min/max range
                target_key.slider_min = source_key.slider_min
                target_key.slider_max = source_key.slider_max
                transferred += 1
            else:
                skipped += 1
        
        transferred_total += transferred
    
    if show_messages:
        message = f"Transferred to {len(valid_targets)} objects, {transferred_total} total keys"
        if skipped > 0:
            message += f", skipped {skipped} non-matching keys"
        show_message(message, "Success", 'INFO')

def reset_shape_keys(obj_name, show_messages=True):
    """Sets all shape key values to zero for the specified object"""
    obj = bpy.data.objects.get(obj_name)
    
    if not obj:
        if show_messages:
            show_message(f"Cannot find object named '{obj_name}'!", "Error", 'ERROR')
        return
        
    if not obj.data.shape_keys:
        if show_messages:
            show_message("Object has no shape keys!", "Error", 'ERROR')
        return
        
    key_blocks = obj.data.shape_keys.key_blocks
    
    if len(key_blocks) <= 1:
        if show_messages:
            show_message("No shape keys found besides basis", "Warning", 'INFO')
        return
        
    reset_count = 0
    for key_block in key_blocks[1:]:
        key_block.value = 0.0
        reset_count += 1
        
    if show_messages:
        show_message(f"Reset {reset_count} shape keys to zero", "Success", 'INFO')

def swap_basis_with_shape_key(obj, shape_key_name):
    if not obj.data.shape_keys:
        show_message("Object has no shape keys!", "Error", 'ERROR')
        return

    shape_keys = obj.data.shape_keys.key_blocks
    if shape_key_name not in shape_keys:
        show_message(f"Shape key '{shape_key_name}' not found!", "Error", 'ERROR')
        return

    # Get basis (first shape key) and target shape key
    basis_key = shape_keys[0]  # First shape key is always the basis
    target_key = shape_keys[shape_key_name]
    
    # Store the vertex positions
    basis_coords = [(v.co.x, v.co.y, v.co.z) for v in basis_key.data]
    target_coords = [(v.co.x, v.co.y, v.co.z) for v in target_key.data]
    
    # Store names
    basis_name = basis_key.name
    target_name = target_key.name
    
    # Swap the coordinates
    for i, v in enumerate(basis_key.data):
        v.co.x, v.co.y, v.co.z = target_coords[i]
    
    for i, v in enumerate(target_key.data):
        v.co.x, v.co.y, v.co.z = basis_coords[i]
    
    # Swap the names
    basis_key.name = target_name
    target_key.name = basis_name

    show_message(f"Swapped basis with '{shape_key_name}' (names and coordinates)", "Success", 'INFO')

class ShapekeyToolsPanel(bpy.types.Panel):
    bl_label = "Shapekey Tools"
    bl_idname = "PT_ShapekeyTools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tool'

    @staticmethod
    def has_valid_shape_keys(obj):
        return (obj and 
                hasattr(obj, 'data') and 
                hasattr(obj.data, 'shape_keys') and 
                obj.data.shape_keys is not None and 
                obj.data.shape_keys.key_blocks)

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Swap Shapekeys section
        box = layout.box()
        box.label(text="Swap Shapekeys")
        
        active_obj = context.active_object
        if self.has_valid_shape_keys(active_obj):
            row = box.row()
            row.prop_search(active_obj, "active_shape_key", 
                          active_obj.data.shape_keys, "key_blocks", 
                          text="Shape Key")
            box.operator("object.swap_basis_shapekey", text="Swap with Basis")
        else:
            box.label(text="No shape keys found", icon='INFO')
        
        # Copy Shapekeys section
        box = layout.box()
        box.label(text="Copy Shapekeys")
        
        # Target type selector
        row = box.row()
        row.prop(scene, "shapekey_target_type", expand=True)
        
        # Source selection
        row = box.row(align=True)
        row.prop_search(scene, "shapekey_source", scene, "objects", text="Source")
        row.operator("object.pick_source_object", text="", icon='EYEDROPPER')
        
        # Target selection based on type
        if scene.shapekey_target_type == 'SINGLE':
            row = box.row(align=True)
            row.prop_search(scene, "shapekey_target", scene, "objects", text="Target")
            row.operator("object.pick_target_object", text="", icon='EYEDROPPER')
        else:
            # Show selected objects count instead of collection picker
            valid_targets = [
                obj for obj in context.selected_objects 
                if obj != scene.shapekey_source and 
                obj.type == 'MESH' and 
                obj.data.shape_keys
            ]
            box.label(text=f"Selected Objects: {len(valid_targets)}", icon='OBJECT_DATA')
        
        # Buttons section
        if scene.shapekey_source and ((scene.shapekey_target_type == 'SINGLE' and scene.shapekey_target) or 
                                     (scene.shapekey_target_type == 'MULTIPLE' and len(context.selected_objects) > 1)):
            box.operator("object.shapekey_transfer", text="Copy Shapekeys")
            box.operator("object.transfer_shape_keys", text="Transfer Values")
        
        # Reset buttons
        if self.has_valid_shape_keys(active_obj):
            box.operator("object.reset_target_shape_keys", text="Reset Values")
            box.operator("object.remove_zero_shapekeys", text="Remove Zero Value Keys")

class ShapekeyTransferOperator(bpy.types.Operator):
    bl_idname = "object.shapekey_transfer"
    bl_label = "Transfer Shapekeys"
    bl_description = "Transfer shapekeys from source to target object(s)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        source_object = scene.shapekey_source
        targets = []
        
        if scene.shapekey_target_type == 'SINGLE':
            if scene.shapekey_target:
                targets.append(scene.shapekey_target)
        else:
            # Get valid selected targets
                targets = [
                    obj for obj in context.selected_objects 
                    if obj != source_object and 
                    obj.type == 'MESH'
                ]
        
        if not source_object or not targets:
            self.report({'ERROR'}, "Please select both source and target(s).")
            return {'CANCELLED'}

        if not source_object.data.shape_keys:
            self.report({'ERROR'}, f"'{source_object.name}' does not have shape keys.")
            return {'CANCELLED'}

        for target_object in targets:
            if target_object.type != 'MESH':
                continue
            
            bpy.context.view_layer.objects.active = target_object

            for key in source_object.data.shape_keys.key_blocks:
                if target_object.data.shape_keys is None:
                    bpy.ops.object.shape_key_add(from_mix=False)

                if key.name not in target_object.data.shape_keys.key_blocks:
                    bpy.ops.object.shape_key_add(from_mix=False)
                    target_object.data.shape_keys.key_blocks[-1].name = key.name

                target_object.data.shape_keys.key_blocks[key.name].value = 1.0
                
                target_key = target_object.data.shape_keys.key_blocks[key.name]
                target_key.slider_min = key.slider_min
                target_key.slider_max = key.slider_max
                
                for vert_src, vert_tgt in zip(key.data, target_key.data):
                    vert_tgt.co = vert_src.co

            for key in target_object.data.shape_keys.key_blocks:
                key.value = 0.0

        self.report({'INFO'}, f"Shape keys copied from '{source_object.name}' to {len(targets)} target(s). All shape key values set to 0.")
        return {'FINISHED'}

class RemoveZeroShapekeysOperator(bpy.types.Operator):
    bl_idname = "object.remove_zero_shapekeys"
    bl_label = "Remove Zero Value Shapekeys"
    bl_description = "Remove all shape keys with a value of 0 from the selected object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        active_obj = context.active_object

        if not active_obj:
            self.report({'ERROR'}, "No active object selected.")
            return {'CANCELLED'}

        if not active_obj.data.shape_keys:
            self.report({'ERROR'}, f"'{active_obj.name}' does not have any shape keys.")
            return {'CANCELLED'}

        keys_to_remove = [key.name for key in active_obj.data.shape_keys.key_blocks[1:] 
                         if abs(key.value) < 0.0001]
        
        for key_name in keys_to_remove:
            active_obj.shape_key_remove(active_obj.data.shape_keys.key_blocks[key_name])

        self.report({'INFO'}, f"Removed {len(keys_to_remove)} zero-value shape keys from '{active_obj.name}'.")
        return {'FINISHED'}

class OBJECT_OT_transfer_shape_keys(Operator):
    bl_idname = "object.transfer_shape_keys"
    bl_label = "Transfer Values"
    bl_description = "Transfer shape key values from source to target(s)"
    
    def execute(self, context):
        scene = context.scene
        source = scene.shapekey_source
        targets = []
        
        if scene.shapekey_target_type == 'SINGLE':
            if scene.shapekey_target:
                targets.append(scene.shapekey_target)
        else:
            # Get all selected objects excluding source
                targets = [
                    obj for obj in context.selected_objects 
                    if obj != source and 
                    obj.type == 'MESH' and 
                    obj.data.shape_keys
                ]
        
        if not source or not targets:
            self.report({'ERROR'}, "Missing source or valid targets")
            return {'CANCELLED'}
        
        for target in targets:
            transfer_shape_key_values(source.name, target_obj_name=target.name)
        
        self.report({'INFO'}, f"Transferred values to {len(targets)} objects")
        return {'FINISHED'}

class OBJECT_OT_reset_shape_keys(Operator):
    bl_idname = "object.reset_target_shape_keys"
    bl_label = "Reset Values"
    bl_description = "Reset all shape key values to zero on selected object"
    
    def execute(self, context):
        active_obj = context.active_object
        if active_obj:
            reset_shape_keys(active_obj.name)
        return {'FINISHED'}

class PICK_OT_source_object(Operator):
    bl_idname = "object.pick_source_object"
    bl_label = "Pick Source"
    bl_description = "Pick the source object from the 3D viewport"
    
    def execute(self, context):
        if context.active_object:
            context.scene.shapekey_source = context.active_object
            show_message(f"Selected source: {context.active_object.name}", "Success", 'INFO')
        return {'FINISHED'}

class PICK_OT_target_object(Operator):
    bl_idname = "object.pick_target_object"
    bl_label = "Pick Target"
    bl_description = "Pick the target object from the 3D viewport"
    
    def execute(self, context):
        if context.active_object:
            context.scene.shapekey_target = context.active_object
            show_message(f"Selected target: {context.active_object.name}", "Success", 'INFO')
        return {'FINISHED'}

class SwapBasisShapekeyOperator(bpy.types.Operator):
    bl_idname = "object.swap_basis_shapekey"
    bl_label = "Swap with Basis"
    bl_description = "Swap selected shape key with basis shape key"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if not obj or not obj.data.shape_keys:
            self.report({'ERROR'}, "Active object must have shape keys")
            return {'CANCELLED'}
            
        active_key = obj.active_shape_key
        if not active_key:
            self.report({'ERROR'}, "Select a non-basis shape key to swap")
            return {'CANCELLED'}
            
        swap_basis_with_shape_key(obj, active_key.name)
        return {'FINISHED'}

classes = (
    ShapekeyToolsPanel,
    ShapekeyTransferOperator,
    RemoveZeroShapekeysOperator,
    OBJECT_OT_transfer_shape_keys,
    OBJECT_OT_reset_shape_keys,
    PICK_OT_source_object,
    PICK_OT_target_object,
    SwapBasisShapekeyOperator,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.shapekey_source = PointerProperty(type=bpy.types.Object, name="Source Object")
    bpy.types.Scene.shapekey_target = PointerProperty(type=bpy.types.Object, name="Target Object")
    bpy.types.Scene.shapekey_target_type = EnumProperty(
        name="Target Type",
        items=[
            ('SINGLE', 'Single Object', 'Transfer to a single object'),
            ('MULTIPLE', 'Multiple Objects', 'Transfer to all selected objects')
        ],
        default='SINGLE'
    )

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.shapekey_source
    del bpy.types.Scene.shapekey_target
    del bpy.types.Scene.shapekey_target_type

if __name__ == "__main__":
    register()
