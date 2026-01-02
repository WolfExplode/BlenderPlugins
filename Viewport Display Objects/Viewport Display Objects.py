import bpy
import json

def get_all_objects_in_collection(coll):
    """Get all objects in a collection and its child collections"""
    objects = []
    if not coll:
        return objects
    objects.extend(coll.objects)
    for child in coll.children:
        objects.extend(get_all_objects_in_collection(child))
    return objects

def update_object_display(context):
    scene = context.scene
    selected_collection = scene.selected_collection
    color_collection = scene.color_collection
    
    # Reset all objects' display properties
    for obj in bpy.data.objects:
        obj.show_name = False
        obj.show_bounds = False
        obj.color = (1, 1, 1, 1)  # Reset to default color
    
    # Update main collection display properties
    if selected_collection and (scene.show_object_names or scene.show_bounding_boxes):
        for obj in selected_collection.objects:
            obj.show_name = scene.show_object_names
            obj.show_bounds = scene.show_bounding_boxes
    
    # Update color mapping
    if color_collection and scene.show_display_colors:
        for obj in get_all_objects_in_collection(color_collection):
            obj_name_lower = obj.name.lower()
            for pair in scene.tag_color_pairs:
                tag = pair.tag.strip().lower()
                if tag and tag in obj_name_lower:
                    obj.color = pair.color
                    break

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

class TagColorPair(bpy.types.PropertyGroup):
    tag: bpy.props.StringProperty(
        name="Tag",
        description="Text fragment to look for in object names",
        default=""
    )
    color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        size=4,
        default=(1, 1, 1, 1),
        min=0.0,
        max=1.0
    )

class TAGCOLOR_UL_List(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.prop(item, "tag", text="", emboss=False)
        row.prop(item, "color", text="")

class TAGCOLOR_OT_AddEntry(bpy.types.Operator):
    bl_idname = "tagcolor.add_entry"
    bl_label = "Add Tag-Color Pair"
    
    def execute(self, context):
        context.scene.tag_color_pairs.add()
        return {'FINISHED'}

class TAGCOLOR_OT_RemoveEntry(bpy.types.Operator):
    bl_idname = "tagcolor.remove_entry"
    bl_label = "Remove Tag-Color Pair"
    
    def execute(self, context):
        pairs = context.scene.tag_color_pairs
        index = context.scene.active_tag_color_index
        if 0 <= index < len(pairs):
            pairs.remove(index)
            context.scene.active_tag_color_index = min(max(0, index - 1), len(pairs) - 1)
        return {'FINISHED'}

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
        
        # Main collection selection
        row = layout.row(align=True)
        row.prop(scene, "selected_collection", text="Main Collection", icon='OUTLINER_COLLECTION')
        row.operator(OBJECT_OT_CollectionPicker.bl_idname, icon='EYEDROPPER', text="")
        
        # Display toggles
        row = layout.row(align=True)
        row.prop(scene, "show_object_names", 
                icon='HIDE_OFF' if scene.show_object_names else 'HIDE_ON',
                text="Names")
        row.prop(scene, "show_bounding_boxes", 
                icon='CUBE' if scene.show_bounding_boxes else 'MESH_CUBE',
                text="Bounds")
        row.prop(scene, "show_display_colors",
                icon='COLOR' if scene.show_display_colors else 'COLOR',
                text="Colors")
        
        # Color collection selection
        layout.separator()
        layout.label(text="Color Mapping Settings:")
        row = layout.row(align=True)
        row.prop(scene, "color_collection", text="Color Collection", icon='OUTLINER_COLLECTION')
        
        # Tag-color pairs
        layout.separator()
        layout.label(text="Tag-Color Mapping:")
        row = layout.row()
        row.template_list(
            "TAGCOLOR_UL_List", 
            "", 
            scene, 
            "tag_color_pairs", 
            scene, 
            "active_tag_color_index"
        )
        col = row.column(align=True)
        col.operator(TAGCOLOR_OT_AddEntry.bl_idname, icon='ADD', text="")
        col.operator(TAGCOLOR_OT_RemoveEntry.bl_idname, icon='REMOVE', text="")
        
        # Add copy/paste buttons after the list
        row = layout.row(align=True)
        row.operator(TAGCOLOR_OT_CopySettings.bl_idname, icon='COPYDOWN')
        row.operator(TAGCOLOR_OT_PasteSettings.bl_idname, icon='PASTEDOWN')

class TAGCOLOR_OT_CopySettings(bpy.types.Operator):
    bl_idname = "tagcolor.copy_settings"
    bl_label = "Copy Color Mappings"
    
    def execute(self, context):
        pairs = context.scene.tag_color_pairs
        data = [{"tag": p.tag, "color": list(p.color)} for p in pairs]
        context.window_manager.clipboard = json.dumps(data)
        self.report({'INFO'}, "Copied color mappings to clipboard")
        return {'FINISHED'}

class TAGCOLOR_OT_PasteSettings(bpy.types.Operator):
    bl_idname = "tagcolor.paste_settings"
    bl_label = "Paste Color Mappings"
    
    def execute(self, context):
        try:
            data = json.loads(context.window_manager.clipboard)
            pairs = context.scene.tag_color_pairs
            pairs.clear()
            
            for item in data:
                new_pair = pairs.add()
                new_pair.tag = item.get('tag', '')
                color = item.get('color', [1, 1, 1, 1])
                new_pair.color = [max(0.0, min(1.0, c)) for c in color][:4]
                
            self.report({'INFO'}, "Pasted color mappings from clipboard")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, "Invalid clipboard data")
            return {'CANCELLED'}

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

    bpy.types.Scene.color_collection = bpy.props.PointerProperty(
        type=bpy.types.Collection,
        name="Color Collection",
        update=lambda self, context: update_object_display(context)
    )
    
    bpy.types.Scene.show_display_colors = bpy.props.BoolProperty(
        name="Show Colors",
        default=True,
        update=lambda self, context: update_object_display(context)
    )

    bpy.utils.register_class(TagColorPair)
    bpy.types.Scene.tag_color_pairs = bpy.props.CollectionProperty(type=TagColorPair)
    bpy.types.Scene.active_tag_color_index = bpy.props.IntProperty()
    bpy.utils.register_class(TAGCOLOR_OT_CopySettings)
    bpy.utils.register_class(TAGCOLOR_OT_PasteSettings)
    
    bpy.utils.register_class(TAGCOLOR_UL_List)
    bpy.utils.register_class(TAGCOLOR_OT_AddEntry)
    bpy.utils.register_class(TAGCOLOR_OT_RemoveEntry)
    bpy.utils.register_class(VIEW3D_PT_ShowObjectDisplay)
    bpy.utils.register_class(OBJECT_OT_CollectionPicker)

def unregister():
    del bpy.types.Scene.selected_collection
    del bpy.types.Scene.show_object_names
    del bpy.types.Scene.show_bounding_boxes
    del bpy.types.Scene.tag_color_pairs
    del bpy.types.Scene.active_tag_color_index
    del bpy.types.Scene.color_collection
    del bpy.types.Scene.show_display_colors
    
    bpy.utils.unregister_class(TagColorPair)
    bpy.utils.unregister_class(TAGCOLOR_UL_List)
    bpy.utils.unregister_class(TAGCOLOR_OT_AddEntry)
    bpy.utils.unregister_class(TAGCOLOR_OT_RemoveEntry)
    bpy.utils.unregister_class(VIEW3D_PT_ShowObjectDisplay)
    bpy.utils.unregister_class(OBJECT_OT_CollectionPicker)
    bpy.utils.unregister_class(TAGCOLOR_OT_CopySettings)
    bpy.utils.unregister_class(TAGCOLOR_OT_PasteSettings)

if __name__ == "__main__":
    register()
