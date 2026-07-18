"""Clean orphaned and duplicate keymap items from Blender's user keyconfig.

Must run INSIDE Blender (Scripting workspace -> open this file -> Run Script):
orphan detection works by querying Blender's live operator registry, which an
external script can't see. This replaces the old external dedupe approach,
which could only compare text and had no way to know whether an operator
still exists.

Finds, in every non-modal keymap of the user keyconfig:
  - orphans:    items whose operator is not registered (typically left behind
                by addons that were removed years ago; also call_menu /
                call_menu_pie / call_panel items whose menu or panel class
                no longer exists)
  - duplicates: identical items bound to the same key (KeyMapItem.compare)

Default is a DRY RUN that prints a report grouped by operator prefix.
Review it, then set REMOVE = True and run again to delete the flagged items.

NOTE: an operator also reads as missing while its addon is merely disabled
(not uninstalled). Enable everything you still use before running with
REMOVE = True, or shield specific addons via KEEP_PREFIXES.
"""

import bpy

REMOVE = False            # True: actually delete flagged items
REMOVE_ORPHANS = True
REMOVE_DUPLICATES = True
SAVE_PREFS = False        # True: save preferences after removal

# Operator prefixes to keep even if unregistered right now
# (addons you sometimes disable but still use), e.g. {"hops", "cp"}.
KEEP_PREFIXES: set[str] = set()

_UI_CALL_OPS = {"wm.call_menu", "wm.call_menu_pie", "wm.call_panel"}


def operator_exists(idname: str) -> bool:
    if "." not in idname:
        return False
    mod, _, func = idname.partition(".")
    try:
        getattr(getattr(bpy.ops, mod), func).get_rna_type()
        return True
    except Exception:
        return False


def missing_ui_target(kmi) -> str | None:
    """For call_menu/pie/panel items, the target class name if unregistered."""
    if kmi.idname not in _UI_CALL_OPS:
        return None
    name = getattr(kmi.properties, "name", "")
    if name and not hasattr(bpy.types, name):
        return name
    return None


def describe_key(kmi) -> str:
    mods = [
        label
        for flag, label in (
            (kmi.any, "Any"),
            (kmi.ctrl, "Ctrl"),
            (kmi.shift, "Shift"),
            (kmi.alt, "Alt"),
            (kmi.oskey, "OS"),
        )
        if flag
    ]
    if kmi.key_modifier != 'NONE':
        mods.append(kmi.key_modifier)
    return " ".join(mods + [kmi.type]) + f" ({kmi.value})"


def scan():
    """Return {keymap_name: [(kmi, reason), ...]} for all flagged items."""
    kc = bpy.context.window_manager.keyconfigs.user
    flagged = {}
    for km in kc.keymaps:
        if km.is_modal:
            continue
        kept = []
        for kmi in km.keymap_items:
            prefix = kmi.idname.partition(".")[0]
            if prefix in KEEP_PREFIXES:
                kept.append(kmi)
                continue

            if REMOVE_ORPHANS and not operator_exists(kmi.idname):
                flagged.setdefault(km.name, []).append((kmi, "missing operator"))
                continue
            target = missing_ui_target(kmi)
            if REMOVE_ORPHANS and target is not None:
                flagged.setdefault(km.name, []).append((kmi, f"missing menu/panel '{target}'"))
                continue

            if REMOVE_DUPLICATES and any(kmi.compare(other) for other in kept):
                flagged.setdefault(km.name, []).append((kmi, "duplicate"))
                continue
            kept.append(kmi)
    return flagged


def report(flagged):
    total = sum(len(v) for v in flagged.values())
    by_prefix = {}
    for km_name, items in sorted(flagged.items()):
        print(f"\n[{km_name}]")
        for kmi, reason in items:
            print(f"  {kmi.idname:<45} {describe_key(kmi):<30} -- {reason}")
            by_prefix.setdefault(kmi.idname.partition(".")[0], 0)
            by_prefix[kmi.idname.partition(".")[0]] += 1
    print(f"\n{'=' * 60}")
    print(f"Flagged {total} item(s) across {len(flagged)} keymap(s).")
    if by_prefix:
        print("By operator prefix (likely source addon):")
        for prefix, count in sorted(by_prefix.items(), key=lambda kv: -kv[1]):
            print(f"  {prefix:<20} {count}")
    return total


def remove(flagged):
    kc = bpy.context.window_manager.keyconfigs.user
    removed = 0
    for km_name, items in flagged.items():
        km = kc.keymaps.get(km_name)
        if km is None:
            continue
        for kmi, _reason in items:
            try:
                km.keymap_items.remove(kmi)
                removed += 1
            except Exception as ex:
                print(f"  could not remove {kmi.idname} from {km_name}: {ex}")
    print(f"Removed {removed} keymap item(s).")
    if SAVE_PREFS:
        bpy.ops.wm.save_userpref()
        print("Preferences saved.")
    else:
        print("Preferences NOT saved -- save manually to persist, or restart to revert.")
    return removed


def main():
    flagged = scan()
    total = report(flagged)
    if not total:
        print("Nothing to clean.")
        return
    if REMOVE:
        remove(flagged)
    else:
        print("\nDry run only. Set REMOVE = True and run again to delete these.")


if __name__ == "__main__":
    main()
