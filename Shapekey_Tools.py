﻿bl_info = {
    "name": "Shapekey Tools",
    "blender": (4, 1, 0),
    "category": "Tool",
    "author": "WXP, Claude"
}

import bpy
from bpy.types import Panel, Operator
from bpy.props import PointerProperty

def show_message(message: str, title: str = "Message", icon: str = 'INFO'):
    def draw(self, context):
        self.layout.label(text=message)
    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)

def transfer_shape_key_values(source_obj_name, target_obj_name, show_messages=True):
    """
    Transfer shape key values from source object to target object
    Both objects must have shape keys with matching names
    """
    source_obj = bpy.data.objects.get(source_obj_name)
    target_obj = bpy.data.objects.get(target_obj_name)
    
    if not source_obj:
        if show_messages:
            show_message(f"Cannot find source object named '{source_obj_name}'!", "Error", 'ERROR')
        return
        
    if not target_obj:
        if show_messages:
            show_message(f"Cannot find target object named '{target_obj_name}'!", "Error", 'ERROR')
        return
    
    if not (source_obj.data.shape_keys and target_obj.data.shape_keys):
        if show_messages:
            show_message("Both objects must have shape keys!", "Error", 'ERROR')
        return
    
    source_keys = source_obj.data.shape_keys.key_blocks
    target_keys = target_obj.data.shape_keys.key_blocks
    
    transferred = 0
    skipped = 0
    
    for source_key in source_keys:
        if source_key.name in target_keys:
            target_keys[source_key.name].value = source_key.value
            transferred += 1
        else:
            skipped += 1
    
    if show_messages:
        message = f"Transferred {transferred} shape keys"
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

class ShapekeyToolsPanel(bpy.types.Panel):
    bl_label = "Shapekey Tools"
    bl_idname = "PT_ShapekeyTools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tool'

    def draw(self, context):
        layout = self.layout
        
        # Copy section
        box = layout.box()
        box.label(text="Copy Shapekeys")
        row = box.row(align=True)
        row.prop_search(context.scene, "shapekey_source", context.scene, "objects", text="Source")
        row.operator("object.pick_source_object", text="", icon='EYEDROPPER')
        
        row = box.row(align=True)
        row.prop_search(context.scene, "shapekey_target", context.scene, "objects", text="Target")
        row.operator("object.pick_target_object", text="", icon='EYEDROPPER')
        
        box.operator("object.shapekey_transfer", text="Copy")
        box.operator("object.shapekey_copy_with_values", text="Copy Shape & Values")
        
        # Value Transfer section
        box = layout.box()
        box.label(text="Value Management")
        box.operator("object.transfer_shape_keys", text="Transfer Values")
        box.operator("object.reset_target_shape_keys", text="Reset Values")
        
        # Remove zero values section
        box = layout.box()
        box.label(text="Remove Zero Values")
        row = box.row(align=True)
        row.prop_search(context.scene, "zero_shapekey_target", context.scene, "objects", text="Target")
        row.operator("object.pick_zero_target_object", text="", icon='EYEDROPPER')
        box.operator("object.remove_zero_shapekeys", text="Remove Zero Value Keys")

class ShapekeyTransferOperator(bpy.types.Operator):
    bl_idname = "object.shapekey_transfer"
    bl_label = "Transfer Shapekeys"
    bl_description = "Transfer shapekeys from source to target object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        source_object = context.scene.shapekey_source
        target_object = context.scene.shapekey_target

        if source_object is None or target_object is None:
            self.report({'ERROR'}, "Please select both source and target objects.")
            return {'CANCELLED'}

        if not source_object.data.shape_keys:
            self.report({'ERROR'}, f"'{source_object.name}' does not have shape keys.")
            return {'CANCELLED'}

        bpy.context.view_layer.objects.active = target_object

        for key in source_object.data.shape_keys.key_blocks:
            if target_object.data.shape_keys is None:
                bpy.ops.object.shape_key_add(from_mix=False)

            if key.name not in target_object.data.shape_keys.key_blocks:
                bpy.ops.object.shape_key_add(from_mix=False)
                target_object.data.shape_keys.key_blocks[-1].name = key.name

            target_object.data.shape_keys.key_blocks[key.name].value = 1.0

            for vert_src, vert_tgt in zip(key.data, target_object.data.shape_keys.key_blocks[key.name].data):
                vert_tgt.co = vert_src.co

        for key in target_object.data.shape_keys.key_blocks:
            key.value = 0.0

        self.report({'INFO'}, f"Shape keys copied from '{source_object.name}' to '{target_object.name}'. All shape key values set to 0.")
        return {'FINISHED'}

class ShapekeyCopyWithValuesOperator(bpy.types.Operator):
    bl_idname = "object.shapekey_copy_with_values"
    bl_label = "Copy Shape & Values"
    bl_description = "Copy shapekeys and set values to match source object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        source_object = context.scene.shapekey_source
        target_object = context.scene.shapekey_target

        if source_object is None or target_object is None:
            self.report({'ERROR'}, "Please select both source and target objects.")
            return {'CANCELLED'}

        if not source_object.data.shape_keys:
            self.report({'ERROR'}, f"'{source_object.name}' does not have shape keys.")
            return {'CANCELLED'}

        bpy.context.view_layer.objects.active = target_object

        for key in source_object.data.shape_keys.key_blocks:
            if target_object.data.shape_keys is None:
                bpy.ops.object.shape_key_add(from_mix=False)

            if key.name not in target_object.data.shape_keys.key_blocks:
                bpy.ops.object.shape_key_add(from_mix=False)
                target_object.data.shape_keys.key_blocks[-1].name = key.name

            target_key = target_object.data.shape_keys.key_blocks[key.name]
            target_key.value = key.value
            target_key.slider_min = key.slider_min
            target_key.slider_max = key.slider_max

            for vert_src, vert_tgt in zip(key.data, target_key.data):
                vert_tgt.co = vert_src.co

        self.report({'INFO'}, f"Shape keys, values, and custom min/max transferred from '{source_object.name}' to '{target_object.name}'.")
        return {'FINISHED'}

class RemoveZeroShapekeysOperator(bpy.types.Operator):
    bl_idname = "object.remove_zero_shapekeys"
    bl_label = "Remove Zero Value Shapekeys"
    bl_description = "Remove all shape keys with a value of 0 from the target object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        target_object = context.scene.zero_shapekey_target

        if target_object is None:
            self.report({'ERROR'}, "Please select a target object.")
            return {'CANCELLED'}

        if not target_object.data.shape_keys:
            self.report({'ERROR'}, f"'{target_object.name}' does not have any shape keys.")
            return {'CANCELLED'}

        keys_to_remove = [key.name for key in target_object.data.shape_keys.key_blocks[1:] 
                         if abs(key.value) < 0.0001]
        
        bpy.context.view_layer.objects.active = target_object
        
        for key_name in keys_to_remove:
            target_object.shape_key_remove(target_object.data.shape_keys.key_blocks[key_name])

        self.report({'INFO'}, f"Removed {len(keys_to_remove)} zero-value shape keys from '{target_object.name}'.")
        return {'FINISHED'}

class OBJECT_OT_transfer_shape_keys(Operator):
    bl_idname = "object.transfer_shape_keys"
    bl_label = "Transfer Values"
    bl_description = "Transfer shape key values from source to target"
    
    def execute(self, context):
        source_object = context.scene.shapekey_source
        target_object = context.scene.shapekey_target
        if source_object and target_object:
            transfer_shape_key_values(source_object.name, target_object.name)
        return {'FINISHED'}

class OBJECT_OT_reset_shape_keys(Operator):
    bl_idname = "object.reset_target_shape_keys"
    bl_label = "Reset Target Values"
    bl_description = "Reset all shape key values to zero on target object"
    
    def execute(self, context):
        target_object = context.scene.shapekey_target
        if target_object:
            reset_shape_keys(target_object.name)
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

class PICK_OT_zero_target_object(Operator):
    bl_idname = "object.pick_zero_target_object"
    bl_label = "Pick Zero Target"
    bl_description = "Pick the target object for zero value removal from the 3D viewport"
    
    def execute(self, context):
        if context.active_object:
            context.scene.zero_shapekey_target = context.active_object
            show_message(f"Selected zero target: {context.active_object.name}", "Success", 'INFO')
        return {'FINISHED'}

classes = (
    ShapekeyToolsPanel,
    ShapekeyTransferOperator,
    ShapekeyCopyWithValuesOperator,
    RemoveZeroShapekeysOperator,
    OBJECT_OT_transfer_shape_keys,
    OBJECT_OT_reset_shape_keys,
    PICK_OT_source_object,
    PICK_OT_target_object,
    PICK_OT_zero_target_object,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.shapekey_source = PointerProperty(type=bpy.types.Object, name="Source Object")
    bpy.types.Scene.shapekey_target = PointerProperty(type=bpy.types.Object, name="Target Object")
    bpy.types.Scene.zero_shapekey_target = PointerProperty(type=bpy.types.Object, name="Zero Target Object")

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.shapekey_source
    del bpy.types.Scene.shapekey_target
    del bpy.types.Scene.zero_shapekey_target

if __name__ == "__main__":
    register()