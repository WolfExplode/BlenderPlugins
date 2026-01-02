bl_info = {
    "name": "My HairTools Sculpting Keymap activator",
    "author": "WXP",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "3D View > Tool",
    "description": "sets `sculpt_curves.brush_stroke` to active since hair tools plugin disables it",
    "category": "3D View",
}

import bpy
from bpy.app.handlers import persistent

def ensure_all_keymaps():
    """Ensure all 'sculpt_curves.brush_stroke' keymaps are active."""
    keymap = bpy.context.window_manager.keyconfigs.user.keymaps.get("Sculpt Curves")
    if not keymap:
        keymap = bpy.context.window_manager.keyconfigs.user.keymaps.new(name="Sculpt Curves", space_type='EMPTY')

    for keymap_item in keymap.keymap_items:
        if keymap_item.idname == "sculpt_curves.brush_stroke" and not keymap_item.active:
            keymap_item.active = True

last_mode = None

@persistent
def mode_change_handler(scene):
    """Handler that runs when the mode changes"""
    global last_mode
    current_mode = bpy.context.mode
    
    if current_mode != last_mode:
        last_mode = current_mode
        if current_mode == 'SCULPT_CURVES':
            ensure_all_keymaps()

class OBJECT_OT_restore_all_keymaps(bpy.types.Operator):
    bl_idname = "object.restore_all_keymaps"
    bl_label = "Restore Sculpt Curves Keymap"
    bl_description = "Ensure sculpt_curves.brush_stroke keymap is active"

    def execute(self, context):
        ensure_all_keymaps()
        return {'FINISHED'}

def register():
    bpy.utils.register_class(OBJECT_OT_restore_all_keymaps)
    bpy.app.handlers.depsgraph_update_post.append(mode_change_handler)

def unregister():
    bpy.app.handlers.depsgraph_update_post.remove(mode_change_handler)
    bpy.utils.unregister_class(OBJECT_OT_restore_all_keymaps)

if __name__ == "__main__":
    register()