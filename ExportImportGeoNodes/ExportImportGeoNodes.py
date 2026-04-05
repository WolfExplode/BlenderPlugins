bl_info = {
    "name": "Import Export Geo Nodes",
    "author": "WolfExplode + Codex",
    "version": (1, 0, 0),
    "blender": (5, 1, 0),
    "location": "Geometry Node Editor > Sidebar > Import/Export",
    "description": "Import and export Geometry Nodes using a shared JSON format",
    "category": "Node",
}

# Instructions for AI when writing Geo nodes: (do not erase this comment)
# If something isn't in the docs, say so
# Before responding to any Blender-related request, always read the relevant files in the docs first.
# Documentation is located at C:\Users\WXP\Documents\GitHub\BlenderPlugins\Blender Documentation
# Do not rely on training memory for node names, socket types, or parameter values

import json
import os
import bpy

EXCLUDED_NODE_PROPS = {
    "rna_type", "type", "dimensions", "inputs", "outputs", "internal_links",
    "location", "name", "label", "parent", "width", "width_hidden", "height",
    "select", "mute", "hide", "show_options", "show_preview", "show_texture",
    "color", "use_custom_color", "warning_propagation",
}


def _extract_json_block(raw_text: str) -> str:
    text = raw_text.strip()
    if not text:
        return ""
    if text[:1] == "{" and text[-1:] == "}":
        return text
    for chunk in text.split("```"):
        candidate = chunk.strip()
        if candidate.lower().startswith("json"):
            candidate = candidate[4:].strip()
        if candidate[:1] == "{" and candidate[-1:] == "}":
            return candidate
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        return text[start:end + 1]
    return ""


def _resolve_socket(node, socket_ref, is_output: bool):
    sockets = node.outputs if is_output else node.inputs
    if isinstance(socket_ref, int) and 0 <= socket_ref < len(sockets):
        return sockets[socket_ref]
    return next((socket for socket in sockets if socket.name == socket_ref), None)


def _build_tree_from_spec(tree, spec: dict):
    node_map = {}
    for node_spec in spec.get("nodes", []):
        node_type = node_spec.get("type")
        if not node_type:
            continue
        node = tree.nodes.new(node_type)
        node_id = str(node_spec.get("id", node.name))
        node_map[node_id] = node
        if "name" in node_spec:
            node.name = str(node_spec["name"])
        if "label" in node_spec:
            node.label = str(node_spec["label"])
        if "location" in node_spec:
            loc = node_spec["location"]
            if isinstance(loc, (list, tuple)) and len(loc) >= 2:
                node.location = (float(loc[0]), float(loc[1]))
        for prop_name, prop_value in node_spec.get("props", {}).items():
            if not hasattr(node, prop_name):
                continue
            prop_meta = node.bl_rna.properties.get(prop_name)
            if prop_meta and prop_meta.is_readonly:
                continue
            try:
                setattr(node, prop_name, prop_value)
            except Exception:
                pass
        for input_spec in node_spec.get("inputs", []):
            socket_key = input_spec.get("socket")
            if socket_key is None:
                continue
            socket = _resolve_socket(node, socket_key, is_output=False)
            if socket is None or socket.is_linked or not hasattr(socket, "default_value"):
                continue
            try:
                socket.default_value = input_spec.get("value")
            except Exception:
                pass
    links = tree.links
    for link_spec in spec.get("links", []):
        from_node = node_map.get(str(link_spec.get("from_node", "")))
        to_node = node_map.get(str(link_spec.get("to_node", "")))
        if from_node is None or to_node is None:
            continue
        from_socket = _resolve_socket(from_node, link_spec.get("from_socket"), is_output=True)
        to_socket = _resolve_socket(to_node, link_spec.get("to_socket"), is_output=False)
        if from_socket is None or to_socket is None:
            continue
        try:
            links.new(from_socket, to_socket)
        except Exception:
            pass

def _to_jsonable(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bpy.types.ID):
        return value.name
    if hasattr(value, "to_list"):
        try:
            return [_to_jsonable(v) for v in value.to_list()]
        except Exception:
            return None
    if hasattr(value, "__iter__") and not isinstance(value, (dict, bytes, bytearray)):
        try:
            return [_to_jsonable(v) for v in value]
        except Exception:
            return None
    return None


def _export_tree_to_spec(geo_tree):
    nodes_out = []
    links_out = []
    for node in geo_tree.nodes:
        node_spec = {
            "id": node.name,
            "type": node.bl_idname,
            "name": node.name,
            "location": [float(node.location.x), float(node.location.y)],
        }
        if node.label:
            node_spec["label"] = node.label

        props = {}
        for prop in node.bl_rna.properties:
            prop_name = prop.identifier
            if prop_name in EXCLUDED_NODE_PROPS or prop_name.startswith("bl_") or prop.is_readonly or not hasattr(node, prop_name):
                continue
            try:
                value = getattr(node, prop_name)
            except Exception:
                continue
            json_value = _to_jsonable(value)
            if json_value is not None:
                props[prop_name] = json_value
        if props:
            node_spec["props"] = props
        inputs = []
        for socket_idx, socket in enumerate(node.inputs):
            if socket.is_linked or not hasattr(socket, "default_value"):
                continue
            json_value = _to_jsonable(socket.default_value)
            if json_value is None:
                continue
            inputs.append({
                "socket": socket_idx,
                "value": json_value,
            })
        if inputs:
            node_spec["inputs"] = inputs
        nodes_out.append(node_spec)
    for link in geo_tree.links:
        from_node = link.from_node
        to_node = link.to_node
        if from_node is None or to_node is None:
            continue
        from_socket_idx = next((i for i, s in enumerate(from_node.outputs) if s == link.from_socket), None)
        to_socket_idx = next((i for i, s in enumerate(to_node.inputs) if s == link.to_socket), None)
        if from_socket_idx is None or to_socket_idx is None:
            continue
        links_out.append({
            "from_node": from_node.name,
            "from_socket": from_socket_idx,
            "to_node": to_node.name,
            "to_socket": to_socket_idx,
        })
    return {"tree_name": geo_tree.name, "nodes": nodes_out, "links": links_out}


def _get_open_geo_tree(context):
    space = context.space_data
    if not (space and getattr(space, "tree_type", "") == 'GeometryNodeTree'):
        return None, "Open a Geometry Node Editor first"
    tree = getattr(space, "edit_tree", None)
    if tree is None or tree.bl_idname != 'GeometryNodeTree':
        return None, "No editable Geometry Node tree is open"
    return tree, None


class AI_GEO_OT_build_from_text(bpy.types.Operator):
    """Create Geometry Nodes from JSON"""
    bl_idname = "ai_geo.build_from_text"
    bl_label = "Build Geo Nodes From Text"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        tree, error = _get_open_geo_tree(context)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        source_mode = scene.ai_geo_source_mode
        if source_mode == 'CLIPBOARD':
            raw = context.window_manager.clipboard
        else:
            text_block = scene.ai_geo_textblock
            raw = text_block.as_string() if text_block else ""

        json_text = _extract_json_block(raw)
        if not json_text:
            self.report({'ERROR'}, "No JSON object found in input text")
            return {'CANCELLED'}

        try:
            spec = json.loads(json_text)
        except Exception as exc:
            self.report({'ERROR'}, f"Invalid JSON: {exc}")
            return {'CANCELLED'}

        _build_tree_from_spec(tree, spec)
        self.report({'INFO'}, f"Added nodes to '{tree.name}'")
        return {'FINISHED'}


class AI_GEO_OT_export_geo_nodes_json(bpy.types.Operator):
    """Export current Geometry Node tree to JSON"""
    bl_idname = "ai_geo.export_geo_nodes_json"
    bl_label = "Export"

    def execute(self, context):
        scene = context.scene
        geo_tree, error = _get_open_geo_tree(context)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        export_path = scene.ai_geo_export_path

        if not export_path:
            self.report({'ERROR'}, "No export path set")
            return {'CANCELLED'}
        filepath = os.path.join(
            bpy.path.abspath(export_path),
            f"{geo_tree.name}_nodes.json",
        )
        with open(filepath, "w", encoding="utf-8") as file:
            json.dump(_export_tree_to_spec(geo_tree), file, indent=2)
        self.report({'INFO'}, f"Exported JSON to {filepath}")
        return {'FINISHED'}


class AI_GEO_PT_panel(bpy.types.Panel):
    bl_label = "Import/Export Geo Nodes"
    bl_idname = "AI_GEO_PT_panel"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Import/Export'

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return bool(space and getattr(space, "tree_type", "") == 'GeometryNodeTree')

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        col = layout.column(align=True)
        col.prop(scene, "ai_geo_source_mode", text="Source")
        if scene.ai_geo_source_mode == 'TEXTBLOCK':
            col.prop(scene, "ai_geo_textblock", text="Text")
        col.operator("ai_geo.build_from_text", icon='NODETREE')

        layout.separator()
        box = layout.box()
        box.label(text="Export")
        box.prop(scene, "ai_geo_export_path", text="Path")
        box.operator("ai_geo.export_geo_nodes_json", icon='EXPORT')


CLASSES = (
    AI_GEO_OT_build_from_text,
    AI_GEO_OT_export_geo_nodes_json,
    AI_GEO_PT_panel,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)

    bpy.types.Scene.ai_geo_source_mode = bpy.props.EnumProperty(
        name="Geo Source",
        items=[
            ('CLIPBOARD', "Clipboard", "Read JSON from clipboard"),
            ('TEXTBLOCK', "Text Block", "Read JSON from a Blender text block"),
        ],
        default='CLIPBOARD',
    )

    bpy.types.Scene.ai_geo_textblock = bpy.props.PointerProperty(
        name="Geo Text",
        type=bpy.types.Text,
    )

    bpy.types.Scene.ai_geo_export_path = bpy.props.StringProperty(
        name="Export Path",
        subtype='DIR_PATH',
    )


def unregister():
    del bpy.types.Scene.ai_geo_export_path
    del bpy.types.Scene.ai_geo_textblock
    del bpy.types.Scene.ai_geo_source_mode

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
