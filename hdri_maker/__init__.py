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
from math import pi, radians

import bpy
import bpy.utils.previews
import gpu
import numpy as np
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import AddonPreferences, Operator, Panel, PropertyGroup, Scene, WindowManager
from gpu.types import Buffer


hdri_preview_collection = {}
HDRI_WORLD_NAME = "HDRi Maker World"
HDRI_ENV_NODE_NAME = "HDRi Maker Background"
addon_keymaps = []

# msgbus owner must be a stable object for clear_by_owner on unregister
_HDRI_MAKER_MSGBUS_OWNER = object()
# SpaceView3D pointer -> (shading.type, shading.use_scene_world) last seen
_last_shading_key = {}

_STUDIO_SHADING_TYPES = frozenset({"MATERIAL", "RENDERED"})


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

    blurry = nodes["Blur_Value"]
    blurry.name = "Blur"

    multiply_node = nodes["HDRI Colorize Mix"]
    multiply_node.name = "HDRI Colorize Mix"

    return world


def update_world_shader(self, context):
    scn = context.scene
    props = scn.hdri_prop_scn
    world = scn.world
    if not world or not world.use_nodes or not world.node_tree:
        return

    def normalize_name(name):
        return name.strip().lower().replace(" ", "_")

    for n in world.node_tree.nodes:
        node_name = normalize_name(n.name)
        if node_name == "world_rotation":
            n.inputs["Rotation"].default_value[0] = radians(props.rot_world_x)
            n.inputs["Rotation"].default_value[1] = radians(props.rot_world_y)
            n.inputs["Rotation"].default_value[2] = radians(props.rot_world_z)
            n.inputs["Location"].default_value[2] = -props.menu_bottom
        elif node_name == "background_light":
            n.inputs["Strength"].default_value = props.emission_force
        elif node_name in {"hdri_hue_sat", "hue_sat", "huesat"}:
            n.inputs["Saturation"].default_value = props.hue_saturation
        elif node_name in {"hdri_contrast", "contrast"}:
            n.inputs["Contrast"].default_value = props.hdri_contrast
        elif node_name == "hdri_colorize":
            n.outputs["Color"].default_value = props.colorize
        elif node_name in {"blur_value", "blur"}:
            n.outputs[0].default_value = props.blur_value / 2
        elif node_name in {"hdri_colorize_mix", "hdri_colorize_multiply"}:
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
    rot_studio_material_z: FloatProperty(
        default=0.0,
        description="Viewport studio HDRI Z rotation (radians) for Material Preview when Scene World is off",
    )
    rot_studio_rendered_z: FloatProperty(
        default=0.0,
        description="Viewport studio HDRI Z rotation (radians) for Rendered Preview when Scene World is off",
    )
    menu_bottom: FloatProperty(default=0, min=-1, max=1, update=update_world_shader)
    emission_force: FloatProperty(default=2, min=0, max=20, update=update_world_shader)
    hue_saturation: FloatProperty(default=1, min=0, max=2, update=update_world_shader)
    hdri_contrast: FloatProperty(default=0, min=-1, max=1, update=update_world_shader)
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


def _modal_exit(context):
    context.window.cursor_set("DEFAULT")
    if context.area:
        context.area.header_text_set(None)


def _is_rotation_preview(space_data):
    if not space_data or not hasattr(space_data, "shading"):
        return False
    return space_data.shading.type in {"MATERIAL", "RENDERED"}


def _is_supported_mode(context):
    return context.mode in {"OBJECT", "SCULPT", "PAINT_TEXTURE"}


def _is_orthographic_view(context):
    region_3d = getattr(context.space_data, "region_3d", None)
    if not region_3d:
        return False
    return region_3d.view_perspective == "ORTHO"


def _wrap_studiolight_z(value):
    while value > pi:
        value -= 2 * pi
    while value < -pi:
        value += 2 * pi
    return value


def _studio_rotation_prop_name(shading_type):
    if shading_type == "MATERIAL":
        return "rot_studio_material_z"
    if shading_type == "RENDERED":
        return "rot_studio_rendered_z"
    return None


def _scene_for_window(window):
    return getattr(window, "scene", None) or bpy.context.scene


def _iter_view3d_spaces():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                yield window, area.spaces.active


def _sync_shading_transition_for_space(window, space, old_key, new_key):
    scene = _scene_for_window(window)
    if not scene or not hasattr(scene, "hdri_prop_scn"):
        return
    props = scene.hdri_prop_scn
    shading = space.shading
    old_type, old_sw = old_key
    new_type, new_sw = new_key

    if (not old_sw) and old_type in _STUDIO_SHADING_TYPES:
        z = shading.studiolight_rotate_z
        if old_type == "MATERIAL":
            props.rot_studio_material_z = z
        else:
            props.rot_studio_rendered_z = z

    if (not new_sw) and new_type in _STUDIO_SHADING_TYPES:
        if new_type == "MATERIAL":
            shading.studiolight_rotate_z = _wrap_studiolight_z(props.rot_studio_material_z)
        else:
            shading.studiolight_rotate_z = _wrap_studiolight_z(props.rot_studio_rendered_z)


def _on_view3d_shading_notify(*_args):
    for window, space in _iter_view3d_spaces():
        ptr = space.as_pointer()
        shading = space.shading
        new_key = (shading.type, shading.use_scene_world)
        old_key = _last_shading_key.get(ptr)
        if old_key is None:
            _last_shading_key[ptr] = new_key
        elif old_key != new_key:
            _sync_shading_transition_for_space(window, space, old_key, new_key)
            _last_shading_key[ptr] = new_key


def _bootstrap_studio_rotation_props_from_viewports():
    for window in bpy.context.window_manager.windows:
        scene = _scene_for_window(window)
        if not scene or not hasattr(scene, "hdri_prop_scn"):
            continue
        props = scene.hdri_prop_scn
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            shading = area.spaces.active.shading
            if shading.use_scene_world:
                continue
            if shading.type == "MATERIAL":
                props.rot_studio_material_z = shading.studiolight_rotate_z
            elif shading.type == "RENDERED":
                props.rot_studio_rendered_z = shading.studiolight_rotate_z


def _init_shading_type_cache():
    _last_shading_key.clear()
    for _window, space in _iter_view3d_spaces():
        shading = space.shading
        _last_shading_key[space.as_pointer()] = (shading.type, shading.use_scene_world)


def _subscribe_shading_msgbus():
    bpy.msgbus.clear_by_owner(_HDRI_MAKER_MSGBUS_OWNER)
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.View3DShading, "type"),
        owner=_HDRI_MAKER_MSGBUS_OWNER,
        args=(),
        notify=_on_view3d_shading_notify,
    )
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.View3DShading, "use_scene_world"),
        owner=_HDRI_MAKER_MSGBUS_OWNER,
        args=(),
        notify=_on_view3d_shading_notify,
    )


@bpy.app.handlers.persistent
def _hdri_maker_load_post(_dummy):
    """Blender clears msgbus subscribers on file load; restore subscriptions and caches."""
    _bootstrap_studio_rotation_props_from_viewports()
    _init_shading_type_cache()
    _subscribe_shading_msgbus()


class HDRIMAKER_OT_RotateHDRI(Operator):
    bl_idname = "hdrimaker.rotate_hdri"
    bl_label = "Rotate HDRI"
    bl_options = {"INTERNAL"}
    start_x = 0
    start_rotation_angle = 0.0
    _use_studiolight_rotation = False
    _studio_rotation_attr = None
    DEPTH_EPSILON = 1e-4

    @staticmethod
    def get_gpu_buffer(xy, wh=(1, 1), centered=False) -> Buffer:
        if isinstance(wh, (int, float)):
            wh = (wh, wh)
        elif len(wh) < 2:
            wh = (wh[0], wh[0])

        x, y, w, h = int(xy[0]), int(xy[1]), int(wh[0]), int(wh[1])
        if centered:
            x -= w // 2
            y -= h // 2

        return gpu.state.active_framebuffer_get().read_depth(x, y, w, h)

    @classmethod
    def gpu_depth_ray_cast(cls, x, y, data):
        size = 1
        buffer = cls.get_gpu_buffer([x, y], wh=[size, size], centered=True)
        depth_samples = np.asarray(buffer, dtype=np.float32).ravel()
        depth_value = float(depth_samples[0]) if depth_samples.size else 1.0
        is_empty = (depth_value >= (1.0 - cls.DEPTH_EPSILON)) or (depth_value <= cls.DEPTH_EPSILON)
        data["is_in_model"] = not is_empty

    def get_mouse_location_ray_cast(self, context, event):
        x, y = event.mouse_region_x, event.mouse_region_y
        view3d = context.space_data
        show_xray = view3d.shading.show_xray
        view3d.shading.show_xray = False
        data = {}
        space_view_3d = bpy.types.SpaceView3D
        handle = space_view_3d.draw_handler_add(
            self.gpu_depth_ray_cast,
            (x, y, data),
            "WINDOW",
            "POST_PIXEL",
        )
        bpy.ops.wm.redraw_timer(type="DRAW", iterations=1)
        space_view_3d.draw_handler_remove(handle, "WINDOW")
        view3d.shading.show_xray = show_xray
        return data.get("is_in_model", False)

    def invoke(self, context, event):
        if not context.area or context.area.type != "VIEW_3D":
            return {"PASS_THROUGH"}
        if not _is_supported_mode(context):
            return {"PASS_THROUGH"}
        if context.mode != "SCULPT" and not _is_rotation_preview(context.space_data):
            return {"PASS_THROUGH"}
        if not _is_orthographic_view(context) and self.get_mouse_location_ray_cast(context, event):
            return {"FINISHED", "PASS_THROUGH"}

        shading = context.space_data.shading
        self.start_x = event.mouse_region_x
        self._use_studiolight_rotation = _is_rotation_preview(context.space_data) and not shading.use_scene_world
        if self._use_studiolight_rotation:
            props = context.scene.hdri_prop_scn
            self._studio_rotation_attr = _studio_rotation_prop_name(shading.type)
            if self._studio_rotation_attr:
                self.start_rotation_angle = getattr(props, self._studio_rotation_attr)
            else:
                self._studio_rotation_attr = None
                self.start_rotation_angle = shading.studiolight_rotate_z
        else:
            self._studio_rotation_attr = None
            self.start_rotation_angle = context.scene.hdri_prop_scn.rot_world_z

        context.window_manager.modal_handler_add(self)
        context.window.cursor_set("MOVE_X")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "RIGHTMOUSE" and event.value == "RELEASE":
            _modal_exit(context)
            return {"FINISHED"}
        if event.type == "ESC":
            _modal_exit(context)
            return {"CANCELLED"}

        if event.type == "MOUSEMOVE":
            dx = event.mouse_region_x - self.start_x
            if self._use_studiolight_rotation:
                shading = context.space_data.shading
                attr = _studio_rotation_prop_name(shading.type) or self._studio_rotation_attr
                value = _wrap_studiolight_z(self.start_rotation_angle + radians(dx * 0.1))
                shading.studiolight_rotate_z = value
                if attr:
                    setattr(context.scene.hdri_prop_scn, attr, value)
            else:
                delta = dx * 0.1
                value = self.start_rotation_angle + delta
                while value > 180:
                    value -= 360
                while value < -180:
                    value += 360
                context.scene.hdri_prop_scn.rot_world_z = value

        return {"RUNNING_MODAL"}


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
        box.prop(props, "hdri_contrast", text="Contrast")
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
    HDRIMAKER_OT_RotateHDRI,
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

    _bootstrap_studio_rotation_props_from_viewports()
    _init_shading_type_cache()
    _subscribe_shading_msgbus()
    if _hdri_maker_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_hdri_maker_load_post)

    wm = bpy.context.window_manager
    if wm.keyconfigs.addon:
        km = wm.keyconfigs.addon.keymaps.new(name="3D View", space_type="VIEW_3D", region_type="WINDOW")
        kmi = km.keymap_items.new(
            idname=HDRIMAKER_OT_RotateHDRI.bl_idname,
            type="RIGHTMOUSE",
            value="PRESS",
            shift=True,
        )
        addon_keymaps.append((km, kmi))

        sculpt_km = wm.keyconfigs.addon.keymaps.new(name="Sculpt", space_type="EMPTY", region_type="WINDOW")
        sculpt_kmi = sculpt_km.keymap_items.new(
            idname=HDRIMAKER_OT_RotateHDRI.bl_idname,
            type="RIGHTMOUSE",
            value="PRESS",
            shift=True,
        )
        addon_keymaps.append((sculpt_km, sculpt_kmi))


def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

    if _hdri_maker_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_hdri_maker_load_post)

    bpy.msgbus.clear_by_owner(_HDRI_MAKER_MSGBUS_OWNER)
    _last_shading_key.clear()

    del WindowManager.hdri_category
    del Scene.hdri_prop_scn

    for collezione in hdri_preview_collection.values():
        bpy.utils.previews.remove(collezione)
    hdri_preview_collection.clear()

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
