import os
import time

import bpy

bl_info = {
    "name": "Compositor Save",
    "author": "WXP",
    "version": (0, 1, 0),
    "blender": (5, 1, 0),
    "location": "Compositor > Sidebar > Node tab (File Output node selected)",
    "description": "Adds a Save button to the File Output node so the compositor can be used as a photo editor "
                   "without pressing F12.",
    "category": "Node",
}


class NODE_OT_save_file_output(bpy.types.Operator):
    bl_idname = "node.save_file_output"
    bl_label = "Save File Output"
    bl_description = "Run the compositor so every File Output node writes its files"

    @classmethod
    def poll(cls, context):
        return context.scene.compositing_node_group is not None

    def execute(self, context):
        render = context.scene.render
        was_compositing = render.use_compositing
        render.use_compositing = True  # the File Output node only runs when the render composites
        started = time.time()
        try:
            bpy.ops.render.render()
        except RuntimeError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        finally:
            render.use_compositing = was_compositing

        # The node logs its own write failures and the render still succeeds, so check what landed on disk.
        node = context.active_node
        if node is None or node.bl_idname != "CompositorNodeOutputFile":
            return {'FINISHED'}
        target = os.path.join(bpy.path.abspath(node.directory), os.path.dirname(node.file_name))
        written = []
        if os.path.isdir(target):
            written = [f for f in os.listdir(target) if os.path.getmtime(os.path.join(target, f)) >= started]
        if not written:
            self.report({'ERROR'}, "Nothing was written to " + target + " - see the Info log for the reason")
            return {'CANCELLED'}
        self.report({'INFO'}, "Saved " + ", ".join(sorted(written)) + " to " + target)
        return {'FINISHED'}


class NODE_PT_save_file_output(bpy.types.Panel):
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Node"
    bl_label = "Save"

    @classmethod
    def poll(cls, context):
        node = context.active_node
        return node is not None and node.bl_idname == "CompositorNodeOutputFile"

    def draw(self, context):
        self.layout.operator(NODE_OT_save_file_output.bl_idname, icon='FILE_TICK')


classes = (NODE_OT_save_file_output, NODE_PT_save_file_output)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
