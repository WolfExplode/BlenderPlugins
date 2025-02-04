import bpy
import os

class EXPORT_OT_GeoNodes(bpy.types.Operator):
    """Export selected Geometry Node tree to a text file"""
    bl_idname = "export.geo_nodes"
    bl_label = "Export Geometry Nodes"

    def execute(self, context):
        geo_tree = context.scene.export_geo_tree
        export_path = context.scene.export_path

        if not geo_tree:
            self.report({'ERROR'}, "No Geometry Node tree selected")
            return {'CANCELLED'}
        
        if not export_path:
            self.report({'ERROR'}, "No export path set")
            return {'CANCELLED'}

        filepath = os.path.join(bpy.path.abspath(export_path), f"{geo_tree.name}_nodes.txt")
        
        with open(filepath, 'w') as file:
            file.write(f"Geometry Node Tree: {geo_tree.name}\n\n")
            
            for node in geo_tree.nodes:
                file.write(f"Node: {node.type} ({node.name})\n")
                
                for input_socket in node.inputs:
                    value = get_socket_value(input_socket)
                    file.write(f"\t{input_socket.name}: {value}\n")
                
                for output_socket in node.outputs:
                    file.write(f"\tOutput: {output_socket.name}\n")
                
                for input_socket in node.inputs:
                    if input_socket.is_linked:
                        for link in input_socket.links:
                            file.write(f"\tConnection: {link.from_node.name} --> {node.name} ({input_socket.name})\n")
                
                file.write("\n")
        
        self.report({'INFO'}, f"Exported to {filepath}")
        return {'FINISHED'}


def get_socket_value(socket):
    if socket.is_linked:
        return "Linked"
    elif hasattr(socket, "default_value"):
        return socket.default_value
    else:
        return "Not Applicable"


class EXPORT_PT_GeoNodesPanel(bpy.types.Panel):
    """UI Panel for exporting Geometry Nodes"""
    bl_label = "Export Geometry Nodes"
    bl_idname = "EXPORT_PT_geo_nodes"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Export'

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene, "export_geo_tree")
        layout.prop(context.scene, "export_path")
        layout.operator("export.geo_nodes")


def register():
    bpy.utils.register_class(EXPORT_OT_GeoNodes)
    bpy.utils.register_class(EXPORT_PT_GeoNodesPanel)
    bpy.types.Scene.export_geo_tree = bpy.props.PointerProperty(type=bpy.types.NodeTree, poll=lambda self, node_tree: node_tree.bl_idname == 'GeometryNodeTree')
    bpy.types.Scene.export_path = bpy.props.StringProperty(name="Export Path", subtype='DIR_PATH')

def unregister():
    bpy.utils.unregister_class(EXPORT_OT_GeoNodes)
    bpy.utils.unregister_class(EXPORT_PT_GeoNodesPanel)
    del bpy.types.Scene.export_geo_tree
    del bpy.types.Scene.export_path

if __name__ == "__main__":
    register()
