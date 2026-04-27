bl_info = {
    "name": "HDRi Maker",
    "author": "WXP",
    "version": (1, 0, 0),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > Hdri Maker",
    "description": "Browse and apply HDRIs with world controls",
    "category": "3D View",
}

import os
from math import radians

import bpy
import bpy.utils.previews
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import AddonPreferences, Operator, Panel, PropertyGroup, Scene, WindowManager


hdri_preview_collection = {}
HDRI_WORLD_NAME = "HDRi Maker World"
HDRI_ENV_NODE_NAME = "HDRi Maker Background"


def get_addon_prefs():
    return bpy.context.preferences.addons[__name__].preferences


def tools_lib_path():
    return os.path.join(os.path.dirname(__file__), "HDRi_tools_lib")


def resolve_library_root(context):
    prefs = get_addon_prefs()
    return bpy.path.abspath(prefs.hdri_maker_library)


def category_root(context):
    root = resolve_library_root(context)
    if not root:
        return ""
    return os.path.join(root, "preview_hdri")


def refresh_preview_cache():
    if "HDRiCol" not in hdri_preview_collection:
        return
    collection = hdri_preview_collection["HDRiCol"]
    collection.hdri_category = ()
    collection.hdri_category_dir = ""


def enum_categories(self, context):
    if context is None:
        return [("Empty Collection...", "Empty Collection...", "")]

    root = category_root(context)
    categories = []
    for item in sorted(os.listdir(root)):
        full = os.path.join(root, item)
        if os.path.isdir(full):
            categories.append(item)
    enum_categories.index = categories
    return [(name, name, "") for name in categories]


def enum_hdri_previews(self, context):
    items = []
    if context is None:
        return items

    props = context.scene.hdri_prop_scn
    category = props.up_category
    preview_dir = os.path.join(category_root(context), category)

    collection = hdri_preview_collection["HDRiCol"]
    if preview_dir == collection.hdri_category_dir:
        return collection.hdri_category

    image_files = []
    for fn in sorted(os.listdir(preview_dir)):
        if fn.lower().endswith(".png"):
            image_files.append(fn)

    for i, name in enumerate(image_files):
        filepath = os.path.join(preview_dir, name)
        thumb = collection.get(name)
        if not thumb:
            thumb = collection.load(name, filepath, "IMAGE")
        items.append((name[:-4], name[:-4], "", thumb.icon_id, i))

    enum_hdri_previews.index = image_files
    collection.hdri_category = items
    collection.hdri_category_dir = preview_dir
    return collection.hdri_category


def update_first_preview(self, context):
    refresh_preview_cache()
    items = enum_hdri_previews(self, context)
    wm = context.window_manager
    if items:
        wm.hdri_category = items[0][0]
    else:
        wm.hdri_category = ""


def update_category(self, context):
    update_first_preview(self, context)


def find_hdri_file(context, hdri_name):
    root = resolve_library_root(context)

    exts = (".hdr", ".exr")
    candidates = []

    for subdir, _dirs, files in os.walk(root):
        for fn in files:
            low = fn.lower()
            if low.endswith(exts) and low.startswith(hdri_name.lower()):
                candidates.append(os.path.join(subdir, fn))

    if not candidates:
        return None
    candidates.sort()
    return candidates[-1]


def ensure_world_with_nodes(scene):
    def has_hdri_node(world):
        if not world or not world.use_nodes or not world.node_tree:
            return False
        return HDRI_ENV_NODE_NAME in world.node_tree.nodes

    if has_hdri_node(scene.world):
        return scene.world

    existing_world = bpy.data.worlds.get(HDRI_WORLD_NAME)
    if has_hdri_node(existing_world):
        scene.world = existing_world
        return existing_world

    template_path = os.path.join(tools_lib_path(), "Files", "Background Node v1.blend")
    with bpy.data.libraries.load(template_path, link=False) as (data_from, data_to):
        data_to.worlds = data_from.worlds
    world = data_to.worlds[0]
    world.name = HDRI_WORLD_NAME
    scene.world = world
    world.use_nodes = True

    nt = world.node_tree
    nodes = nt.nodes

    blurry = nodes["BLURRY_Value"]
    blurry.name = "Blur"
    blurry.label = "Blur"

    mix_node = nodes["HDRI_COLORIZE_MIX"]
    multiply_node = next(
        n
        for n in nodes
        if n != mix_node and n.bl_idname in {"ShaderNodeMix", "ShaderNodeMixRGB"}
    )
    multiply_node.name = "HDRI_COLORIZE_MULTIPLY"
    multiply_node.label = "Colorize Mix"

    return world


def update_world_shader(self, context):
    scn = context.scene
    props = scn.hdri_prop_scn
    world = scn.world

    for n in world.node_tree.nodes:
        if n.name == "World Rotation":
            n.inputs["Rotation"].default_value[0] = radians(props.rot_world_x)
            n.inputs["Rotation"].default_value[1] = radians(props.rot_world_y)
            n.inputs["Rotation"].default_value[2] = radians(props.rot_world_z)
            n.inputs["Location"].default_value[2] = -props.menu_bottom
        elif n.name == "Background light":
            n.inputs["Strength"].default_value = props.emission_force
        elif n.name == "Hdri hue_sat":
            n.inputs["Saturation"].default_value = props.hue_saturation
        elif n.name == "HDRI_COLORIZE":
            n.outputs["Color"].default_value = props.colorize
        elif n.name == "Blur":
            n.outputs[0].default_value = props.blur_value / 2
        elif n.name == "HDRI_COLORIZE_MIX":
            n.inputs[0].default_value = props.colorize_mix
        elif n.name == "HDRI_COLORIZE_MULTIPLY":
            n.inputs[0].default_value = props.colorize_mix


class HDRIMAKER_Preferences(AddonPreferences):
    bl_idname = __name__

    hdri_maker_library: StringProperty(
        name="HDRI_MAKER_LIB",
        subtype="DIR_PATH",
        description="Path to HDRI_MAKER_LIB",
    )
    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.label(text="Minimal HDRI browser setup")
        col.prop(self, "hdri_maker_library")


class HdriPropertyScene(PropertyGroup):
    up_category: EnumProperty(name="Category", items=enum_categories, update=update_category)
    menu_label: BoolProperty(default=True, description="Show labels in HDRI picker")
    menu_icon_popup: FloatProperty(default=6, min=1, max=10)

    rot_world_x: FloatProperty(default=0, update=update_world_shader)
    rot_world_y: FloatProperty(default=0, update=update_world_shader)
    rot_world_z: FloatProperty(default=0, update=update_world_shader)
    menu_bottom: FloatProperty(default=0, min=-1, max=1, update=update_world_shader)
    emission_force: FloatProperty(default=2, min=0, max=20, update=update_world_shader)
    hue_saturation: FloatProperty(default=1, min=0, max=5, update=update_world_shader)
    blur_value: FloatProperty(default=0, min=0, max=0.5, update=update_world_shader)
    colorize_mix: FloatProperty(default=0, min=0, max=1, update=update_world_shader)
    colorize: FloatVectorProperty(
        subtype="COLOR",
        default=(0, 0, 0, 1),
        min=0.0,
        max=1.0,
        size=4,
        update=update_world_shader,
    )


class HDRIMAKER_OT_Add(Operator):
    bl_idname = "hdrimaker.add"
    bl_label = "Apply HDRI"
    bl_options = {"UNDO"}

    def execute(self, context):
        wm = context.window_manager
        hdri_name = wm.hdri_category
        if not hdri_name or hdri_name == "Empty":
            self.report({"WARNING"}, "No HDRI selected.")
            return {"CANCELLED"}

        hdri_path = find_hdri_file(context, hdri_name)
        if not hdri_path:
            self.report({"ERROR"}, f"HDR file not found for: {hdri_name}")
            return {"CANCELLED"}

        world = ensure_world_with_nodes(context.scene)
        env = world.node_tree.nodes[HDRI_ENV_NODE_NAME]

        env.image = bpy.data.images.load(hdri_path, check_existing=True)
        return {"FINISHED"}


class HDRIMAKER_OT_Prev(Operator):
    bl_idname = "hdri.prev"
    bl_label = "Previous HDRI"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        wm = context.window_manager
        items = [i[0] for i in enum_hdri_previews(self, context)]
        if not items:
            return {"CANCELLED"}
        current = wm.hdri_category if wm.hdri_category in items else items[0]
        idx = items.index(current)
        wm.hdri_category = items[(idx - 1) % len(items)]
        return {"FINISHED"}


class HDRIMAKER_OT_Next(Operator):
    bl_idname = "hdri.next"
    bl_label = "Next HDRI"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        wm = context.window_manager
        items = [i[0] for i in enum_hdri_previews(self, context)]
        if not items:
            return {"CANCELLED"}
        current = wm.hdri_category if wm.hdri_category in items else items[0]
        idx = items.index(current)
        wm.hdri_category = items[(idx + 1) % len(items)]
        return {"FINISHED"}


class HDRIMAKER_PT_Panel(Panel):
    bl_label = "HDRi Maker"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Hdri Maker"

    def draw(self, context):
        layout = self.layout
        scn = context.scene
        props = scn.hdri_prop_scn
        wm = context.window_manager

        col = layout.column(align=True)
        col.prop(props, "up_category", text="Category")

        row = layout.row(align=True)
        row.operator("hdri.prev", text="", icon="TRIA_LEFT")
        row.template_icon_view(
            wm,
            "hdri_category",
            show_labels=True if props.menu_label else False,
            scale_popup=props.menu_icon_popup,
        )
        row.operator("hdri.next", text="", icon="TRIA_RIGHT")

        layout.operator("hdrimaker.add", icon="WORLD")

        box = layout.box()
        box.label(text="World Shader")
        box.prop(props, "emission_force", text="HDRI light")
        box.prop(props, "hue_saturation", text="Saturation")
        box.prop(props, "blur_value", text="Blur", slider=True)
        row = box.row(align=True)
        split = row.split(factor=0.82, align=True)
        split.prop(props, "colorize_mix", text="Colorize mix")
        split.prop(props, "colorize", text="")
        box.prop(props, "rot_world_z", text="Rotate Z")
        box.prop(context.scene.render, "film_transparent", text="Transparent Background")


classes = (
    HDRIMAKER_Preferences,
    HdriPropertyScene,
    HDRIMAKER_OT_Add,
    HDRIMAKER_OT_Prev,
    HDRIMAKER_OT_Next,
    HDRIMAKER_PT_Panel,
)


def register():
    collezione = bpy.utils.previews.new()
    collezione.hdri_category = ()
    collezione.hdri_category_dir = ""
    hdri_preview_collection["HDRiCol"] = collezione

    for cls in classes:
        bpy.utils.register_class(cls)

    Scene.hdri_prop_scn = PointerProperty(type=HdriPropertyScene)
    WindowManager.hdri_category = EnumProperty(
        items=enum_hdri_previews,
        description="Select HDRI by preview",
    )


def unregister():
    del WindowManager.hdri_category
    del Scene.hdri_prop_scn

    for collezione in hdri_preview_collection.values():
        bpy.utils.previews.remove(collezione)
    hdri_preview_collection.clear()

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
