__version__ = "1.0.0"

bl_info = {
    "name": "Target, Please!",
    "author": "Ilyasse L",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "3D View",
    "description": (
        "Executes with default settings on all selected objects (if at least one non-light object is selected) via Shift+T. "
        "Use Ctrl+Shift+T to open a dialog that lets you choose the axes, the Target Z option, and whether the temporary Empty should be deleted after validation. "
        "If the Empty is not deleted, the constraint remains for live tracking."
    ),
    "warning": "",
    "wiki_url": "",
    "category": "Object",
}

import bpy
from mathutils import Vector
from bpy_extras import view3d_utils

# Global variable to hold registered keymaps
addon_keymaps = []

# ---------------------------------------------------------------------
# Functions for hotkey registration and update
# ---------------------------------------------------------------------
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
        # Hotkey for direct execution (e.g., Shift+T)
        kmi1 = km.keymap_items.new(
            OBJECT_OT_live_set_target.bl_idname, 
            type=prefs.key_direct, 
            value='PRESS', 
            shift=prefs.key_direct_shift, 
            ctrl=prefs.key_direct_ctrl
        )
        # Hotkey for opening the dialog (here Ctrl+Shift+T)
        kmi2 = km.keymap_items.new(
            OBJECT_OT_live_set_target.bl_idname, 
            type=prefs.key_dialog, 
            value='PRESS', 
            shift=prefs.key_dialog_shift, 
            ctrl=prefs.key_dialog_ctrl
        )
        addon_keymaps.append((km, kmi1))
        addon_keymaps.append((km, kmi2))

def update_hotkeys(self, context):
    unregister_keymaps()
    register_keymaps()

# ------------------------------------------------------------------------------
# Addon Preferences for configuring hotkeys and the "delete empty" option
# ------------------------------------------------------------------------------
class TargetAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__
    
    # Hotkeys for direct execution (e.g., Shift+T)
    key_direct: bpy.props.StringProperty(
         name="Key (Direct Execution)",
         description="Key for direct execution (with Shift only)",
         default="T",
         update=update_hotkeys
    )
    key_direct_shift: bpy.props.BoolProperty(
         name="Shift",
         description="Use Shift for direct execution",
         default=True,
         update=update_hotkeys
    )
    key_direct_ctrl: bpy.props.BoolProperty(
         name="Ctrl",
         description="Use Ctrl for direct execution",
         default=False,
         update=update_hotkeys
    )
    
    # Hotkeys for dialog execution (e.g., Ctrl+Shift+T)
    key_dialog: bpy.props.StringProperty(
         name="Key (Dialog)",
         description="Key for opening the dialog (with Ctrl+Shift)",
         default="T",
         update=update_hotkeys
    )
    key_dialog_shift: bpy.props.BoolProperty(
         name="Shift",
         description="Use Shift for dialog",
         default=True,
         update=update_hotkeys
    )
    key_dialog_ctrl: bpy.props.BoolProperty(
         name="Ctrl",
         description="Use Ctrl for dialog",
         default=True,
         update=update_hotkeys
    )
    
    # Option for deleting the Empty after validation
    delete_empty_after: bpy.props.BoolProperty(
         name="Delete Empty After Validation",
         description="If enabled, the temporary Empty will be deleted and the final transformation applied (constraints removed). "
                     "Otherwise, the Empty and constraints are kept for live tracking.",
         default=True
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


# ------------------------------------------------------------------------------
# Operator: Define and execute the target
# ------------------------------------------------------------------------------
class OBJECT_OT_live_set_target(bpy.types.Operator):
    """
    Dynamically defines a target using surface snapping for the selected objects.
    If the selection contains at least one non-light object, all objects (including lights) are affected.
    
    Pressing Ctrl opens a dialog to configure the axes, the Target Z option, and the 
    "Delete Empty After Validation" setting. If this option is disabled, the Empty and 
    constraint remain in place for live tracking.
    """
    bl_idname = "object.live_set_target"
    bl_label = "Set Live Target (Dual Mode with Target Z)"
    bl_options = {'UNDO'}

    # Properties for axes and the Target Z option
    track_axis: bpy.props.EnumProperty(
        name="Track Axis",
        description="Axis used to point toward the target",
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
        description="Axis used as 'up'",
        items=[
            ('UP_X', "Up X", ""),
            ('UP_Y', "Up Y", ""),
            ('UP_Z', "Up Z", ""),
        ],
        default='UP_Y'
    )
    
    target_z: bpy.props.BoolProperty(
        name="Target Z",
        description="If enabled, the target's Z axis is taken into account",
        default=False
    )
    
    # Option configurable in the dialog
    delete_empty_after: bpy.props.BoolProperty(
        name="Delete Empty After Validation",
        description="If enabled, the temporary Empty will be deleted and the final transformation applied (constraints removed). "
                    "Otherwise, the Empty and constraints are kept for live tracking.",
        default=True
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "track_axis")
        layout.prop(self, "up_axis")
        layout.prop(self, "target_z")
        layout.prop(self, "delete_empty_after")

    def invoke(self, context, event):
        if context.area.type != 'VIEW_3D':
            self.report({'WARNING'}, "3D View not found, operation cancelled")
            return {'CANCELLED'}
        # Retrieve the saved setting from the addon preferences
        prefs = context.preferences.addons[__name__].preferences
        self.delete_empty_after = prefs.delete_empty_after
        # If Ctrl is pressed, open the dialog to modify options
        if event.ctrl:
            return context.window_manager.invoke_props_dialog(self, width=300)
        else:
            return self.execute(context)

    def execute(self, context):
        # Verify that the selection contains at least one non-light object
        if all(obj.type == 'LIGHT' for obj in context.selected_objects):
            self.report({'WARNING'}, "Selection contains only lights. Operation cancelled.")
            return {'CANCELLED'}

        # Create the temporary Empty to serve as the target
        self.empty = bpy.data.objects.new("LiveTarget", None)
        self.empty.empty_display_size = 0.5
        self.empty.empty_display_type = 'PLAIN_AXES'
        context.collection.objects.link(self.empty)

        # Reference point: the active object's location or the origin
        if context.active_object:
            self.ref_point = context.active_object.location.copy()
        else:
            self.ref_point = Vector((0, 0, 0))

        # Apply the "Track To" constraint to each selected object (except the Empty)
        self.constrained_objects = []
        for obj in context.selected_objects:
            if obj == self.empty:
                continue
            constraint = obj.constraints.new(type='TRACK_TO')
            constraint.name = "LiveTarget_TrackTo"
            constraint.target = self.empty
            constraint.track_axis = self.track_axis
            constraint.up_axis = self.up_axis
            constraint.use_target_z = self.target_z
            self.constrained_objects.append((obj, constraint))

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        # Update constraints in real time according to current properties
        for obj, constraint in self.constrained_objects:
            constraint.track_axis = self.track_axis
            constraint.up_axis = self.up_axis
            constraint.use_target_z = self.target_z

        if event.type == 'MOUSEMOVE':
            region = context.region
            rv3d = context.region_data
            coord = (event.mouse_region_x, event.mouse_region_y)
            view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
            ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
            result, location, normal, index, hit_obj, matrix = context.scene.ray_cast(
                context.view_layer.depsgraph, ray_origin, view_vector)
            if result:
                self.empty.location = location
            else:
                self.empty.location = view3d_utils.region_2d_to_location_3d(region, rv3d, coord, self.ref_point)
            return {'RUNNING_MODAL'}

        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            # Save the setting in the preferences unconditionally
            prefs = context.preferences.addons[__name__].preferences
            prefs.delete_empty_after = self.delete_empty_after

            if self.delete_empty_after:
                # Finalize by applying the final transformation: copy the matrix, remove constraints, and delete the Empty.
                depsgraph = context.evaluated_depsgraph_get()
                for obj, constraint in self.constrained_objects:
                    eval_obj = obj.evaluated_get(depsgraph)
                    obj.matrix_world = eval_obj.matrix_world.copy()
                    try:
                        obj.constraints.remove(constraint)
                    except Exception as e:
                        self.report({'WARNING'}, f"Error removing constraint: {str(e)}")
                bpy.data.objects.remove(self.empty, do_unlink=True)
                self.report({'INFO'}, "Target validated and applied (baked)")
            else:
                # Finalize by leaving the Empty and constraints in place for live tracking.
                self.report({'INFO'}, "Target validated and maintained live (constraints kept)")
            return {'FINISHED'}

        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            # Cancel: remove constraints and delete the Empty
            for obj, constraint in self.constrained_objects:
                try:
                    obj.constraints.remove(constraint)
                except Exception as e:
                    self.report({'WARNING'}, f"Error removing constraint: {str(e)}")
            bpy.data.objects.remove(self.empty, do_unlink=True)
            self.report({'INFO'}, "Operation cancelled")
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}


# ------------------------------------------------------------------------------
# Registration
# ------------------------------------------------------------------------------
def register():
    bpy.utils.register_class(TargetAddonPreferences)
    bpy.utils.register_class(OBJECT_OT_live_set_target)
    register_keymaps()

def unregister():
    unregister_keymaps()
    bpy.utils.unregister_class(OBJECT_OT_live_set_target)
    bpy.utils.unregister_class(TargetAddonPreferences)

if __name__ == "__main__":
    register()
