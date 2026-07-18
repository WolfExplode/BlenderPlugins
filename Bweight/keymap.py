import bpy

addon_keymaps = []

# (filter_type, key, ctrl, shift)
BINDINGS = (
    ('GROW', 'EQUAL', True, False),
    ('GROW', 'NUMPAD_PLUS', True, False),
    ('SHRINK', 'MINUS', True, False),
    ('SHRINK', 'NUMPAD_MINUS', True, False),
    ('SMOOTH', 'EQUAL', True, True),
    ('SMOOTH', 'NUMPAD_PLUS', True, True),
    ('SHARPEN', 'MINUS', True, True),
    ('SHARPEN', 'NUMPAD_MINUS', True, True),
)

# Restores Blender's own Shift+LMB = Blur brush behavior for Weight Paint,
# same mechanism Bbrush relies on for Shift-smooth in sculpt mode. Some
# keymap presets/addons strip brush_toggle back to 'None'; we patch it back
# on and remember the prior value so unregister() can undo it cleanly.
# The keymap item itself is re-located by search each time rather than
# cached, since adding/removing addon keymap items rebuilds Blender's
# merged user keymap and invalidates any previously held kmi reference.
_shift_smooth_original = None
_shift_smooth_patched = False


def _find_shift_lmb_weight_paint_kmi():
    km = bpy.context.window_manager.keyconfigs.user.keymaps.get("Weight Paint")
    if km is None:
        return None
    for kmi in km.keymap_items:
        if (
            kmi.idname == "paint.weight_paint"
            and kmi.type == 'LEFTMOUSE'
            and kmi.value == 'PRESS'
            and kmi.shift and not kmi.ctrl and not kmi.alt
        ):
            return kmi
    return None


def _patch_shift_smooth():
    global _shift_smooth_original, _shift_smooth_patched
    if _shift_smooth_patched:
        return
    kmi = _find_shift_lmb_weight_paint_kmi()
    if kmi is None:
        return
    current = kmi.properties.brush_toggle
    if current == 'SMOOTH':
        return
    _shift_smooth_original = current or 'None'
    kmi.properties.brush_toggle = 'SMOOTH'
    _shift_smooth_patched = True


def _unpatch_shift_smooth():
    global _shift_smooth_original, _shift_smooth_patched
    if not _shift_smooth_patched:
        return
    kmi = _find_shift_lmb_weight_paint_kmi()
    if kmi is not None:
        kmi.properties.brush_toggle = _shift_smooth_original
    _shift_smooth_patched = False
    _shift_smooth_original = None


def register():
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is not None:
        km = kc.keymaps.new(name="Weight Paint", space_type='EMPTY')
        for filter_type, key, ctrl, shift in BINDINGS:
            kmi = km.keymap_items.new(
                "paint.bweight_filter", key, 'PRESS',
                ctrl=ctrl, shift=shift, repeat=True,
            )
            kmi.properties.filter_type = filter_type
            addon_keymaps.append((km, kmi))

    _patch_shift_smooth()


def unregister():
    _unpatch_shift_smooth()

    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
