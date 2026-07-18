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

    # Ctrl-inverted gradient, in two cooperating parts:
    # 1. Holding Ctrl with the Gradient tool inverts the paint weight (1 - w)
    #    until released (paint.weight_gradient's own 'flip' property is
    #    ignored in interactive use, so inverting the weight is the only way).
    for key in ('LEFT_CTRL', 'RIGHT_CTRL'):
        kmi = km.keymap_items.new(
            "paint.bweight_gradient_invert_hold", key, 'PRESS',
            any=True, repeat=False,
        )
        addon_keymaps.append((km, kmi))
    # 2. A Ctrl+drag binding so the gradient still fires while Ctrl is held
    #    (the stock binding requires no modifiers). No flip needed — the
    #    inverted weight from part 1 does the actual inverting. Goes through
    #    the wrapper so the tool's Linear/Radial header setting is honored.
    km_tool = kc.keymaps.new(
        name="3D View Tool: Paint Weight, Gradient", space_type='VIEW_3D',
    )
    kmi = km_tool.keymap_items.new(
        "paint.bweight_gradient_ctrl", 'LEFTMOUSE', 'CLICK_DRAG', ctrl=True,
    )
    addon_keymaps.append((km_tool, kmi))


def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
