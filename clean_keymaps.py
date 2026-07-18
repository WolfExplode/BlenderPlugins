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
  - duplicates: items with the same operator, same properties, and the same
                key event as another item already kept

Duplicate detection deliberately does NOT use KeyMapItem.compare() alone --
that method only compares the event trigger (key/modifiers/value), not the
operator or its properties. Two different operators legitimately share a
key (e.g. an addon's G-key operator that PASS_THROUGHs to the built-in
transform.translate also bound to G as a fallback); compare()-only dedupe
deletes the fallback and silently breaks the shortcut. Learned this the
hard way -- see git history.

Default is a DRY RUN that prints a report grouped by operator prefix.
Review it, then set REMOVE = True and run again to delete the flagged items.

Orphan candidates are double-checked against currently ENABLED addons before
being flagged, because "not registered right now" is not proof of removal:
addons register operators/menus conditionally (MACHIN3tools only registers
the pies you activate in its preferences -- deactivating the Modes Pie
unregisters MACHIN3_MT_modes_pie, and a naive hasattr check then deletes
every Tab binding for it; learned this the hard way too). The double-check:
  1. the addon keyconfig (wm.keyconfigs.addon) -- items an enabled addon is
     actively contributing (matched by operator + properties, not key, so
     user-remapped copies still count)
  2. the source files of every INSTALLED addon (enabled or not, via
     addon_utils.modules) -- a literal occurrence of the operator idname or
     menu/panel class name means the owner addon is still installed, just
     disabled or not registering that piece right now
Items rescued this way are reported separately and never deleted, so only
keymaps of truly UNINSTALLED addons get flagged as orphans.

Blind spots of the source scan: addons shipping only compiled code
(.pyc / native modules) or building idnames dynamically at runtime won't
match -- shield those via KEEP_PREFIXES.
"""

import os

import addon_utils
import bpy

REMOVE = False            # True: actually delete flagged items
REMOVE_ORPHANS = True
REMOVE_DUPLICATES = True
SAVE_PREFS = False        # True: save preferences after removal

# Operator prefixes to keep even if unregistered and unmatched by the
# installed-addon source scan (compiled-only or dynamic-idname addons),
# e.g. {"hops", "cp"}.
KEEP_PREFIXES: set[str] = set()

_UI_CALL_OPS = {"wm.call_menu", "wm.call_menu_pie", "wm.call_panel", "wm.call_asset_shelf_popover"}


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


_addon_source_cache: dict[str, tuple[str, bool]] | None = None
_token_cache: dict[str, tuple[str, bool] | None] = {}


def _addon_sources() -> dict[str, tuple[str, bool]]:
    """{module_name: (concatenated .py source, is_enabled)} for every
    INSTALLED addon, enabled or not."""
    global _addon_source_cache
    if _addon_source_cache is None:
        _addon_source_cache = {}
        enabled = {a.module for a in bpy.context.preferences.addons}
        for mod in addon_utils.modules(refresh=False):
            file = getattr(mod, "__file__", None)
            if not file:
                continue
            paths = []
            if os.path.basename(file) == "__init__.py":
                for dirpath, _dirs, files in os.walk(os.path.dirname(file)):
                    paths.extend(os.path.join(dirpath, fn) for fn in files if fn.endswith(".py"))
            else:
                paths.append(file)
            chunks = []
            for path in paths:
                try:
                    with open(path, encoding="utf-8", errors="ignore") as f:
                        chunks.append(f.read())
                except OSError:
                    pass
            _addon_source_cache[mod.__name__] = ("\n".join(chunks), mod.__name__ in enabled)
    return _addon_source_cache


def find_owner_addon(token: str) -> tuple[str, bool] | None:
    """(module_name, is_enabled) of the installed addon whose source mentions
    token, or None if no installed addon does.

    token is an operator idname ('machin3.smart_vert') or a menu/panel class
    name ('MACHIN3_MT_modes_pie'); both appear literally in the source of the
    addon that defines them, even while that piece is deactivated (or the
    whole addon disabled) and thus unregistered. Enabled addons are preferred
    when several mention the same token.
    """
    if token not in _token_cache:
        hits = [
            (name, is_enabled)
            for name, (src, is_enabled) in _addon_sources().items()
            if token in src
        ]
        _token_cache[token] = max(hits, key=lambda hit: hit[1]) if hits else None
    return _token_cache[token]


def addon_keyconfig_has(km_name: str, kmi) -> bool:
    """True if an enabled addon currently contributes this item (operator +
    properties; the key is ignored so user-remapped copies still match)."""
    km = bpy.context.window_manager.keyconfigs.addon.keymaps.get(km_name)
    return km is not None and any(
        other.idname == kmi.idname and properties_equal(kmi.properties, other.properties)
        for other in km.keymap_items
    )


def properties_equal(a, b) -> bool:
    if a is None or b is None:
        return a is b
    names = {p.identifier for p in a.bl_rna.properties if p.identifier != "rna_type"}
    if names != {p.identifier for p in b.bl_rna.properties if p.identifier != "rna_type"}:
        return False
    return all(getattr(a, name) == getattr(b, name) for name in names)


def items_equal(a, b) -> bool:
    """True duplicate: same operator, same properties, same key event."""
    return a.idname == b.idname and a.compare(b) and properties_equal(a.properties, b.properties)


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


def check_orphan(km_name: str, kmi) -> tuple[str | None, str | None]:
    """(flag_reason, spare_note) -- at most one is set.

    flag_reason: kmi is unregistered and no installed addon claims it -> remove.
    spare_note:  kmi is unregistered, but 'not registered right now' is not
                 proof of removal -- an installed addon still owns it, either
                 contributing it via the addon keyconfig or mentioning the
                 operator / menu class in its source (disabled addons, or
                 conditionally registered pieces like deactivated MACHIN3tools
                 pies) -> keep.
    Both None: kmi's operator is registered, nothing orphaned about it.
    """
    if not operator_exists(kmi.idname):
        reason, token = "missing operator", kmi.idname
    else:
        target = missing_ui_target(kmi)
        if target is None:
            return None, None
        reason, token = f"missing menu/panel '{target}'", target

    if addon_keyconfig_has(km_name, kmi):
        return None, f"{reason}, but contributed by an enabled addon's keyconfig"
    owner = find_owner_addon(token)
    if owner is not None:
        name, is_enabled = owner
        state = "enabled" if is_enabled else "installed but DISABLED"
        return None, f"{reason}, but owned by {state} addon '{name}'"
    return reason, None


def scan():
    """Return ({keymap_name: [(kmi, reason), ...]}, [(keymap_name, kmi, note), ...]):
    items flagged for removal, and orphan candidates spared by the enabled-addon
    double-check."""
    kc = bpy.context.window_manager.keyconfigs.user
    flagged = {}
    spared = []
    for km in kc.keymaps:
        if km.is_modal:
            continue
        kept = []
        for kmi in km.keymap_items:
            prefix = kmi.idname.partition(".")[0]
            if prefix in KEEP_PREFIXES:
                kept.append(kmi)
                continue

            note = None
            if REMOVE_ORPHANS:
                reason, note = check_orphan(km.name, kmi)
                if reason is not None:
                    flagged.setdefault(km.name, []).append((kmi, reason))
                    continue

            if REMOVE_DUPLICATES and any(items_equal(kmi, other) for other in kept):
                flagged.setdefault(km.name, []).append((kmi, "duplicate"))
                continue
            if note is not None:
                spared.append((km.name, kmi, note))
            kept.append(kmi)
    return flagged, spared


def report(flagged, spared):
    if spared:
        print(f"Spared {len(spared)} unregistered item(s) still claimed by an installed addon:")
        for km_name, kmi, note in spared:
            print(f"  [{km_name}] {kmi.idname:<40} {describe_key(kmi):<25} -- {note}")

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
    flagged, spared = scan()
    total = report(flagged, spared)
    if not total:
        print("Nothing to clean.")
        return
    if REMOVE:
        remove(flagged)
    else:
        print("\nDry run only. Set REMOVE = True and run again to delete these.")


if __name__ == "__main__":
    main()
