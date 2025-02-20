import bpy

def update_object_names(context):
    scene = context.scene
    selected_collection = scene.selected_collection
    
    # Hide all object names if no collection is selected
    if not selected_collection:
        for obj in bpy.data.objects:
            obj.show_name = False
        return
    
    # Show object names only for the selected collection
    for obj in bpy.data.objects:
        obj.show_name = selected_collection in obj.users_collection

def validate_selected_collection(scene):
    """Ensure the selected collection still exists."""
    if scene.selected_collection and scene.selected_collection.name not in bpy.data.collections:
        scene.selected_collection = None  # Clear the selection if the collection no longer exists

class VIEW3D_PT_ShowObjectNames(bpy.types.Panel):
    bl_label = "Show Object Names"
    bl_idname = "VIEW3D_PT_show_object_names"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tool'
    bl_context = "objectmode"
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Validate the selected collection
        validate_selected_collection(scene)
        
        # Dropdown to select collection
        row = layout.row()
        row.prop(scene, "selected_collection", text="Collection")

def register():
    bpy.types.Scene.selected_collection = bpy.props.PointerProperty(
        type=bpy.types.Collection,
        name="Selected Collection",
        description="Collection to show object names for",
        update=lambda self, context: update_object_names(context)
    )
    bpy.utils.register_class(VIEW3D_PT_ShowObjectNames)

def unregister():
    del bpy.types.Scene.selected_collection
    bpy.utils.unregister_class(VIEW3D_PT_ShowObjectNames)

if __name__ == "__main__":
    register()