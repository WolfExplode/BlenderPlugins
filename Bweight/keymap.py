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


def register():
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:
        return
    km = kc.keymaps.new(name="Weight Paint", space_type='EMPTY')
    for filter_type, key, ctrl, shift in BINDINGS:
        kmi = km.keymap_items.new(
            "paint.bweight_filter", key, 'PRESS',
            ctrl=ctrl, shift=shift, repeat=True,
        )
        kmi.properties.filter_type = filter_type
        addon_keymaps.append((km, kmi))


def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
