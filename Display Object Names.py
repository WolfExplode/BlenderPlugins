import bpy

def update_object_display(context):
    scene = context.scene
    selected_collection = scene.selected_collection
    
    # Reset all objects if no collection is selected
    if not selected_collection or (not scene.show_object_names and not scene.show_bounding_boxes):
        for obj in bpy.data.objects:
            obj.show_name = False
            obj.show_bounds = False
        return
    
    # Update objects in the selected collection
    for obj in bpy.data.objects:
        in_collection = selected_collection in obj.users_collection
        
        # Update name visibility
        obj.show_name = in_collection and scene.show_object_names
        
        # Update bounding box display
        obj.show_bounds = in_collection and scene.show_bounding_boxes

def validate_selected_collection(scene):
    """Ensure the selected collection still exists."""
    if scene.selected_collection and scene.selected_collection.name not in bpy.data.collections:
        scene.selected_collection = None

def get_collection_depth(coll):
    """Calculate collection depth in hierarchy"""
    depth = 0
    current = coll
    while True:
        # Find parent collection by checking all collections' children
        parent = next((c for c in bpy.data.collections if current.name in c.children), None)
        if not parent:
            break
        depth += 1
        current = parent
    return depth

def get_deepest_collection(obj):
    """Find the deepest collection in hierarchy for an object"""
    if not obj.users_collection:
        return None
    
    deepest_coll = None
    max_depth = -1
    
    for coll in obj.users_collection:
        depth = get_collection_depth(coll)
        if depth > max_depth or (depth == max_depth and coll.name > (deepest_coll.name if deepest_coll else "")):
            max_depth = depth
            deepest_coll = coll
    
    return deepest_coll

class OBJECT_OT_CollectionPicker(bpy.types.Operator):
    bl_idname = "object.collection_picker"
    bl_label = "Pick Collection from Object"
    bl_description = "Click on an object to select its deepest collection"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj:
            self.report({'ERROR'}, "No object selected")
            return {'CANCELLED'}

        deepest_coll = get_deepest_collection(obj)
        if deepest_coll:
            context.scene.selected_collection = deepest_coll
            self.report({'INFO'}, f"Selected collection: {deepest_coll.name}")
            return {'FINISHED'}
        
        self.report({'ERROR'}, "Object not in any collection")
        return {'CANCELLED'}

class VIEW3D_PT_ShowObjectDisplay(bpy.types.Panel):
    bl_label = "Object Display Tools"
    bl_idname = "VIEW3D_PT_show_object_display"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tool'
    bl_context = "objectmode"
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        validate_selected_collection(scene)
        
        # Collection selection row
        row = layout.row(align=True)
        row.prop(scene, "selected_collection", text="", icon='OUTLINER_COLLECTION')
        row.operator(OBJECT_OT_CollectionPicker.bl_idname, 
                    text="", 
                    icon='EYEDROPPER')
        
        # Toggle buttons row
        row = layout.row(align=True)
        row.prop(scene, "show_object_names", 
                icon='HIDE_OFF' if scene.show_object_names else 'HIDE_ON',
                text="Names")
        row.prop(scene, "show_bounding_boxes", 
                icon='CUBE' if scene.show_bounding_boxes else 'MESH_CUBE',
                text="Bounds")

def register():
    bpy.types.Scene.selected_collection = bpy.props.PointerProperty(
        type=bpy.types.Collection,
        name="Selected Collection",
        update=lambda self, context: update_object_display(context)
    )
    
    bpy.types.Scene.show_object_names = bpy.props.BoolProperty(
        name="Show Names",
        default=True,
        update=lambda self, context: update_object_display(context)
    )
    
    bpy.types.Scene.show_bounding_boxes = bpy.props.BoolProperty(
        name="Show Bounds",
        default=False,
        update=lambda self, context: update_object_display(context)
    )
    
    bpy.utils.register_class(OBJECT_OT_CollectionPicker)
    bpy.utils.register_class(VIEW3D_PT_ShowObjectDisplay)

def unregister():
    del bpy.types.Scene.selected_collection
    del bpy.types.Scene.show_object_names
    del bpy.types.Scene.show_bounding_boxes
    bpy.utils.unregister_class(VIEW3D_PT_ShowObjectDisplay)
    bpy.utils.unregister_class(OBJECT_OT_CollectionPicker)

if __name__ == "__main__":
    register()
