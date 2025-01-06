bl_info = {
    "name": "myShapekey Copy",
    "version": (1, 0, 1),
    "blender": (4, 1, 0),
    "category": "Tool",
    "author": "Blender Bob, Chat GPT, WXP, Claude",
}

import bpy
from bpy.props import PointerProperty

class ShapekeyTransferPanel(bpy.types.Panel):
    bl_label = "Shapekeys Copy"
    bl_idname = "PT_ShapekeyTransfer"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tool'

    def draw(self, context):
        layout = self.layout
        layout.prop_search(context.scene, "shapekey_source", context.scene, "objects", text="Source")
        layout.prop_search(context.scene, "shapekey_target", context.scene, "objects", text="Target")
        layout.operator("object.shapekey_transfer", text="Copy")
        layout.operator("object.shapekey_copy_with_values", text="Copy Shape & Values")

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
    bl_description = "Copy shapekeys, values, and drivers from source to target object"
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

            # Check for and copy drivers
            try:
                source_anim_data = source_object.data.shape_keys.animation_data
                if source_anim_data and source_anim_data.drivers:
                    for driver in source_anim_data.drivers:
                        if driver.data_path.startswith('key_blocks["' + key.name + '"]'):
                            # Create target driver
                            target_driver = target_key.driver_add("value")
                            # Copy driver expression
                            target_driver.driver.expression = driver.driver.expression
                            
                            # Copy driver variables
                            for var in driver.driver.variables:
                                new_var = target_driver.driver.variables.new()
                                new_var.name = var.name
                                new_var.type = var.type
                                for i, target in enumerate(var.targets):
                                    new_var_target = new_var.targets[i]
                                    new_var_target.id = target.id
                                    new_var_target.data_path = target.data_path
            except Exception as e:
                self.report({'WARNING'}, f"Could not copy driver for shape key '{key.name}': {str(e)}")

        self.report({'INFO'}, f"Shape keys, values, custom min/max, and drivers transferred from '{source_object.name}' to '{target_object.name}'.")
        return {'FINISHED'}

def register():
    bpy.utils.register_class(ShapekeyTransferPanel)
    bpy.utils.register_class(ShapekeyTransferOperator)
    bpy.utils.register_class(ShapekeyCopyWithValuesOperator)
    bpy.types.Scene.shapekey_source = PointerProperty(type=bpy.types.Object, name="Source Object")
    bpy.types.Scene.shapekey_target = PointerProperty(type=bpy.types.Object, name="Target Object")

def unregister():
    bpy.utils.unregister_class(ShapekeyTransferPanel)
    bpy.utils.unregister_class(ShapekeyTransferOperator)
    bpy.utils.unregister_class(ShapekeyCopyWithValuesOperator)
    del bpy.types.Scene.shapekey_source
    del bpy.types.Scene.shapekey_target

if __name__ == "__main__":
    register()