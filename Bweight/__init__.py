from . import ops, keymap

bl_info = {
    "name": "Bweight",
    "author": "WXP",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "Weight Paint mode",
    "description": "Keyboard-driven weight editing: smooth/sharpen (Ctrl Shift +/-), grow/shrink (Ctrl +/-)",
    "category": "Paint",
}

modules = (ops, keymap)


def register():
    for mod in modules:
        mod.register()


def unregister():
    for mod in reversed(modules):
        mod.unregister()
