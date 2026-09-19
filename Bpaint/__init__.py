import bpy

bl_info = {
    "name": "Bpaint",
    "author": "WXP",
    "version": (0, 2, 0),
    "blender": (5, 1, 0),
    "location": "Texture Paint mode",
    "description": "Bbrush-style modifier brushes for Texture Paint: hold Shift for Blur, hold Ctrl for Mask "
                   "(stencil image created automatically). Alt+LMB inverts the stroke instead of Ctrl.",
    "category": "Paint",
}

_ESSENTIALS_TEXTURE = "brushes/essentials_brushes-mesh_texture.blend/Brush/"

# One slot per modifier. "default" is used until the user picks another brush while holding that modifier.
_slots = {
    "SHIFT": {"default": ("ESSENTIALS", "", _ESSENTIALS_TEXTURE + "Blur"), "secondary": None},
    "CTRL": {"default": ("ESSENTIALS", "", _ESSENTIALS_TEXTURE + "Mask"), "secondary": None},
}

_MODIFIER_KEYS = {
    "SHIFT": ("LEFT_SHIFT", "RIGHT_SHIFT"),
    "CTRL": ("LEFT_CTRL", "RIGHT_CTRL"),
}

# Only one slot can be engaged at a time. primary/applied are only set while it is engaged.
_state = {"slot": None, "primary": None, "applied": None}

STENCIL_NAME = "Bpaint Mask"

addon_keymaps = []


def _read_ref(context):
    ref = context.tool_settings.image_paint.brush_asset_reference
    if ref is None:
        return None
    return (ref.asset_library_type, ref.asset_library_identifier, ref.relative_asset_identifier)


def _activate(triple):
    try:
        return "FINISHED" in bpy.ops.brush.asset_activate(
            asset_library_type=triple[0],
            asset_library_identifier=triple[1],
            relative_asset_identifier=triple[2],
        )
    except RuntimeError:
        return False


def _modifier_held(event, slot):
    return event.shift if slot == "SHIFT" else event.ctrl


def _engage(context, slot):
    if _state["slot"] is not None:
        return
    primary = _read_ref(context)
    if primary is None:
        return
    target = _slots[slot]["secondary"] or _slots[slot]["default"]
    if primary == target:
        # Already on the secondary brush, so nothing to swap and nothing to restore.
        return
    if _activate(target):
        _state.update(slot=slot, primary=primary, applied=_read_ref(context))


def _release(context):
    slot = _state["slot"]
    if slot is None:
        return
    current = _read_ref(context)
    # A brush picked while the modifier was held becomes that slot's new secondary.
    if current is not None and current != _state["applied"]:
        _slots[slot]["secondary"] = current
    _activate(_state["primary"])
    _state.update(slot=None, primary=None, applied=None)


def _paint_canvas(context):
    ip = context.tool_settings.image_paint
    if ip.mode == "IMAGE":
        return ip.canvas
    mat = context.object.active_material if context.object else None
    if mat is None or not mat.texture_paint_images:
        return None
    return mat.texture_paint_images[min(mat.paint_active_slot, len(mat.texture_paint_images) - 1)]


def _fill_udim_tiles(context, image, canvas):
    """Give every UDIM tile of the stencil a black buffer sized like the canvas tile.

    image.tiles.new() only adds an empty tile, and image.tile_fill needs an Image Editor,
    so another area is borrowed for the duration of the call.
    """
    area = next((a for a in context.screen.areas if a != context.area), None)
    if area is None:
        return False
    old_type = area.ui_type
    try:
        area.ui_type = "IMAGE_EDITOR"
        space = area.spaces.active
        prev_image = space.image
        space.image = image
        region = next(r for r in area.regions if r.type == "WINDOW")
        with context.temp_override(area=area, space_data=space, region=region):
            for tile in image.tiles:
                if tile.size[0]:
                    continue
                src = canvas.tiles.get(tile.number)
                width, height = src.size if src else canvas.size
                image.tiles.active = tile
                bpy.ops.image.tile_fill(
                    color=(0, 0, 0, 1), generated_type="BLANK",
                    width=width, height=height, float=False, alpha=False,
                )
        space.image = prev_image
    finally:
        area.ui_type = old_type
    return True


def _ensure_stencil(context):
    """The Mask brush paints into the stencil image, so make sure one exists and is enabled."""
    ip = context.tool_settings.image_paint
    if ip.stencil_image is None:
        canvas = _paint_canvas(context)
        width, height = canvas.size if canvas and canvas.size[0] else (2048, 2048)
        tiled = canvas is not None and canvas.source == "TILED"
        image = bpy.data.images.new(STENCIL_NAME, width, height, alpha=False, tiled=tiled)
        if tiled:
            for tile in canvas.tiles:
                if tile.number != 1001:
                    image.tiles.new(tile_number=tile.number)
            _fill_udim_tiles(context, image, canvas)
        ip.stencil_image = image
    ip.use_stencil_layer = True


class PAINT_OT_bpaint_modifier(bpy.types.Operator):
    bl_idname = "paint.bpaint_modifier"
    bl_label = "Bpaint Modifier Brush"
    bl_options = {"INTERNAL"}

    slot: bpy.props.EnumProperty(items=(("SHIFT", "Shift", ""), ("CTRL", "Ctrl", "")))
    press: bpy.props.BoolProperty(default=True)

    @classmethod
    def poll(cls, context):
        return context.mode == "PAINT_TEXTURE"

    def invoke(self, context, event):
        if self.press:
            if self.slot == "SHIFT" and event.shift and not event.ctrl and not event.alt:
                _engage(context, "SHIFT")
            elif self.slot == "CTRL" and event.ctrl and not event.shift:
                _engage(context, "CTRL")
        elif _state["slot"] == self.slot and not _modifier_held(event, self.slot):
            _release(context)
        return {"PASS_THROUGH"}


class PAINT_OT_bpaint_mask_stroke(bpy.types.Operator):
    """Runs before a Ctrl+LMB stroke: make sure the Ctrl brush is active and has a stencil to paint into."""

    bl_idname = "paint.bpaint_mask_stroke"
    bl_label = "Bpaint Mask Stroke"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        return context.mode == "PAINT_TEXTURE"

    def invoke(self, context, event):
        if _state["slot"] is None:
            _engage(context, "CTRL")
        ip = context.tool_settings.image_paint
        if ip.brush is not None and ip.brush.image_brush_type == "MASK":
            _ensure_stencil(context)
        return {"PASS_THROUGH"}


classes = (PAINT_OT_bpaint_modifier, PAINT_OT_bpaint_mask_stroke)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:
        return

    km = kc.keymaps.new(name="Window", space_type="EMPTY")
    for slot, keys in _MODIFIER_KEYS.items():
        for key in keys:
            for value, press in (("PRESS", True), ("RELEASE", False)):
                kmi = km.keymap_items.new(
                    "paint.bpaint_modifier", key, value, shift=-1, ctrl=-1, alt=-1, oskey=-1
                )
                kmi.properties.slot = slot
                kmi.properties.press = press
                addon_keymaps.append((km, kmi))

    # Add-on items run before the default Image Paint ones, so these take over Ctrl+LMB
    # (normally the inverted stroke) and move inversion to Alt+LMB.
    # Each add-on item lands at the top of the user keymap, so they are added in reverse:
    # the mask setup must end up first so it runs before the stroke starts.
    km = kc.keymaps.new(name="Image Paint", space_type="EMPTY")
    kmi = km.keymap_items.new("paint.image_paint", "LEFTMOUSE", "PRESS", alt=True, ctrl=-1)
    kmi.properties.mode = "INVERT"
    addon_keymaps.append((km, kmi))
    kmi = km.keymap_items.new("paint.image_paint", "LEFTMOUSE", "PRESS", ctrl=True)
    kmi.properties.mode = "NORMAL"
    addon_keymaps.append((km, kmi))
    kmi = km.keymap_items.new("paint.bpaint_mask_stroke", "LEFTMOUSE", "PRESS", ctrl=True, alt=-1)
    addon_keymaps.append((km, kmi))


def unregister():
    if _state["slot"] is not None:
        _release(bpy.context)
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
