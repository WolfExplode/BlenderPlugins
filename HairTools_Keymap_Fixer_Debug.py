bl_info = {
    "name": "My HairTools Sculpting Keymap activator",
    "author": "WXP",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "3D View > Tool > Keymap Debugger",
    "description": "sets `sculpt_curves.brush_stroke` to active since hair tools plugin disables it",
    "category": "3D View",
}

import bpy
from bpy.app.handlers import persistent

def show_message(message: str, title: str = "Message", icon: str = 'INFO'):
    """Display a popup message."""
    def draw(self, context):
        self.layout.label(text=message)
    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)

def debug_all_keymaps():
    """Detect and report all keymap items with the name 'sculpt_curves.brush_stroke'."""
    wm = bpy.context.window_manager
    keyconfigs = wm.keyconfigs

    # Get the Sculpt Curves keymap
    keymap = keyconfigs.user.keymaps.get("Sculpt Curves")
    if not keymap:
        show_message("Keymap 'Sculpt Curves' not found!", "Debug Info", 'ERROR')
        return

    keymap_items = []
    for keymap_item in keymap.keymap_items:
        if keymap_item.idname == "sculpt_curves.brush_stroke":
            keymap_items.append({
                "idname": keymap_item.idname,
                "type": keymap_item.type,
                "value": keymap_item.value,
                "ctrl": keymap_item.ctrl,
                "shift": keymap_item.shift,
                "alt": keymap_item.alt,
                "active": keymap_item.active,
                "properties": {prop.identifier: getattr(keymap_item.properties, prop.identifier)
                               for prop in keymap_item.properties.rna_type.properties if prop.is_runtime}
            })

    if keymap_items:
        message = f"Detected {len(keymap_items)} 'sculpt_curves.brush_stroke' keymap items:\n"
        for idx, item in enumerate(keymap_items, start=1):
            message += (
                f"Keymap Item {idx}:\n"
                f"  - Type: {item['type']}\n"
                f"  - Value: {item['value']}\n"
                f"  - Ctrl: {item['ctrl']}\n"
                f"  - Shift: {item['shift']}\n"
                f"  - Alt: {item['alt']}\n"
                f"  - Active: {item['active']}\n"
                f"  - Properties: {item['properties']}\n\n"
            )
        print(message)
        show_message(message, "Debug Info", 'INFO')
    else:
        show_message("No 'sculpt_curves.brush_stroke' keymap items found!", "Debug Info", 'ERROR')

def ensure_all_keymaps(show_messages=True):
    """Ensure all 'sculpt_curves.brush_stroke' keymaps are active."""
    wm = bpy.context.window_manager
    keyconfigs = wm.keyconfigs

    # Get the Sculpt Curves keymap
    keymap = keyconfigs.user.keymaps.get("Sculpt Curves")
    if not keymap:
        keymap = keyconfigs.user.keymaps.new(name="Sculpt Curves", space_type='EMPTY')
        print("Created new 'Sculpt Curves' keymap.")

    updated_count = 0
    for keymap_item in keymap.keymap_items:
        if keymap_item.idname == "sculpt_curves.brush_stroke":
            if not keymap_item.active:
                keymap_item.active = True
                updated_count += 1
                print(f"Activated keymap item: {keymap_item.type} (Ctrl: {keymap_item.ctrl}, Shift: {keymap_item.shift})")

    if show_messages:
        if updated_count > 0:
            show_message(f"Activated {updated_count} 'sculpt_curves.brush_stroke' keymap items.", "Success", 'INFO')

# Store the last known mode
last_mode = None

@persistent
def mode_change_handler(scene):
    """Handler that runs when the mode changes"""
    global last_mode
    
    current_mode = bpy.context.mode
    
    # Only proceed if the mode has actually changed
    if current_mode != last_mode:
        last_mode = current_mode
        
        # Check if we're entering sculpt mode
        if current_mode == 'SCULPT_CURVES':
            # Don't show messages for automatic checks
            ensure_all_keymaps(show_messages=False)

class OBJECT_OT_debug_all_keymaps(bpy.types.Operator):
    bl_idname = "object.debug_all_keymaps"
    bl_label = "Debug All Keymaps"
    bl_description = "Debug and report all 'sculpt_curves.brush_stroke' keymap items"

    def execute(self, context):
        debug_all_keymaps()
        return {'FINISHED'}

class OBJECT_OT_restore_all_keymaps(bpy.types.Operator):
    bl_idname = "object.restore_all_keymaps"
    bl_label = "Restore All Keymaps"
    bl_description = "Ensure all 'sculpt_curves.brush_stroke' keymaps are added and active"

    def execute(self, context):
        # Show messages when manually triggered
        ensure_all_keymaps(show_messages=True)
        return {'FINISHED'}

class VIEW3D_PT_keymap_debugger(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tool'
    bl_label = "Keymap Debugger"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Keymap Debugging Tools:")
        layout.operator("object.debug_all_keymaps", text="Debug All Keymaps")
        layout.operator("object.restore_all_keymaps", text="Restore All Keymaps")

# Registration
classes = (
    OBJECT_OT_debug_all_keymaps,
    OBJECT_OT_restore_all_keymaps,
    VIEW3D_PT_keymap_debugger,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    # Add the mode change handler
    bpy.app.handlers.depsgraph_update_post.append(mode_change_handler)
    # Initialize last_mode
    global last_mode
    last_mode = bpy.context.mode

def unregister():
    # Remove the mode change handler
    bpy.app.handlers.depsgraph_update_post.remove(mode_change_handler)
    for cls in classes:
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()