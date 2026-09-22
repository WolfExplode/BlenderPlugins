"""LateLoader - defer add-on loading until after startup, or until asked.

This is a *startup script*, not an add-on. It must live in

    <Blender config>/scripts/startup/LateLoader.py

because Blender enables add-ons from preferences during startup, and only
scripts in `scripts/startup/` run before that happens. An add-on installed the
normal way registers far too late to defer anything.

One goal: keep add-ons out of the startup critical path. It never disables an
add-on, never edits preferences, and never patches files in the Blender
installation. It intercepts one function, in memory, for the duration of
startup.

While it holds that function it also times every add-on it lets through, so the
manager can show what each one costs rather than making you guess from module
names.

Policies, per add-on module name, stored in <Blender config>/LateLoader.json:

    startup     load normally during startup (the default for anything unlisted)
    background  skip during startup, load automatically once the window is up
    manual      skip during startup, load only when asked

`background` is the useful default for slow add-ons: the window appears without
waiting for them, and they finish loading a moment later, long before a human
reaches for a tool. `manual` is for add-ons you rarely touch in a session.

Author: WXP
"""

import json
import os
import time
import traceback

import bpy
import addon_utils

CONFIG_NAME = "LateLoader.json"

POLICY_STARTUP = 'startup'
POLICY_BACKGROUND = 'background'
POLICY_MANUAL = 'manual'
DEFERRED_POLICIES = (POLICY_BACKGROUND, POLICY_MANUAL)

POLICY_ITEMS = (
    (POLICY_STARTUP, "Startup", "Load during startup, as normal"),
    (POLICY_BACKGROUND, "Background", "Skip startup, load once the window is up"),
    (POLICY_MANUAL, "Manual", "Skip startup, load only when asked"),
)

# Module names that are never deferred, whatever the config says. Blender's own
# extension plumbing and the render engine are load-bearing during startup.
NEVER_DEFER = frozenset((
    "bl_pkg",
    "cycles",
))

# A measured register cost at or above this is worth deferring. The default for
# the bulk action, and the threshold that flags a row as slow.
SLOW_SECONDS = 0.05

# Deferred module names in the order Blender would have enabled them, so that
# add-ons which depend on each other still load in their original relative
# order. Populated during startup, drained afterwards.
_pending = []
_policies = {}
_timings = {}
_load_errors = {}
_orig_enable = None
_timings_dirty = False

# module name -> (label, category, warning), rebuilt by scan().
_info = {}


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

def config_path():
    return os.path.join(bpy.utils.user_resource('CONFIG'), CONFIG_NAME)


def read_config():
    """(policies, timings) from disk. Never raises - a bad config defers nothing."""
    try:
        with open(config_path(), encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}, {}
    except Exception:
        print("LateLoader: could not read %s, deferring nothing" % config_path())
        traceback.print_exc()
        return {}, {}

    policies = {}
    raw = data.get("policies")
    if isinstance(raw, dict):
        for module, policy in raw.items():
            if isinstance(module, str) and policy in DEFERRED_POLICIES:
                policies[module] = policy

    timings = {}
    raw = data.get("timings")
    if isinstance(raw, dict):
        for module, seconds in raw.items():
            if isinstance(module, str) and isinstance(seconds, (int, float)):
                timings[module] = float(seconds)

    return policies, timings


def write_config():
    """Persist policies and measured timings. Returns True on success."""
    global _timings_dirty
    keep = {m: p for m, p in _policies.items() if p in DEFERRED_POLICIES}
    data = {
        "policies": keep,
        "timings": {m: round(s, 4) for m, s in sorted(_timings.items())},
    }
    try:
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        _timings_dirty = False
        return True
    except Exception:
        traceback.print_exc()
        return False


def policy_for(module):
    return _policies.get(module, POLICY_STARTUP)


def set_policy(module, policy):
    if policy == POLICY_STARTUP:
        _policies.pop(module, None)
    else:
        _policies[module] = policy
    return write_config()


def _record_timing(module, seconds):
    global _timings_dirty
    _timings[module] = seconds
    _timings_dirty = True


# ---------------------------------------------------------------------------
# the startup intercept
# ---------------------------------------------------------------------------

def _patched_enable(module_name, **kwargs):
    """Stand-in for addon_utils.enable during startup only.

    Deferrable add-ons go on the queue; everything else is enabled for real and
    timed, so the manager has a real cost to show next to each name.
    """
    if policy_for(module_name) in DEFERRED_POLICIES and module_name not in NEVER_DEFER:
        if module_name not in _pending:
            _pending.append(module_name)
        return None

    start = time.perf_counter()
    mod = _orig_enable(module_name, **kwargs)
    if mod is not None:
        _record_timing(module_name, time.perf_counter() - start)
    return mod


def _restore_enable():
    """Put addon_utils.enable back, if we are still the one holding it."""
    global _orig_enable
    if _orig_enable is None:
        return
    if addon_utils.enable is _patched_enable:
        addon_utils.enable = _orig_enable
    _orig_enable = None


def pending():
    """Module names skipped at startup and not yet loaded."""
    return list(_pending)


def is_loaded(module):
    return module not in _pending


def load_now(module):
    """Load one deferred add-on. Returns (ok, message)."""
    if module not in _pending:
        return True, "%s is already loaded" % module

    errors = []

    def handle_error(ex):
        errors.append(ex)
        traceback.print_exc()

    # default_set=False: the preferences entry is already there. We skipped
    # registering the add-on, we never removed it, so there is nothing to add
    # back and no reason to touch preferences at all.
    start = time.perf_counter()
    mod = addon_utils.enable(module, default_set=False, handle_error=handle_error)
    elapsed = time.perf_counter() - start

    if mod is None:
        _pending.remove(module)
        reason = repr(errors[0]) if errors else "add-on did not load"
        _load_errors[module] = reason
        return False, "%s failed to load: %s" % (module, reason)

    # Registering costs the same whenever it happens, so this is also the
    # startup cost this add-on would have had.
    _record_timing(module, elapsed)
    _pending.remove(module)
    _load_errors.pop(module, None)
    return True, "Loaded %s in %s" % (module, format_seconds(elapsed))


def _drain_one():
    """Timer: load a single background add-on per event-loop tick.

    One per tick rather than all at once so the window stays responsive while
    the queue empties, and so a slow add-on costs one stutter instead of a
    freeze. Returns 0.0 to run again on the next tick, None to stop.
    """
    _restore_enable()

    for module in list(_pending):
        if policy_for(module) == POLICY_BACKGROUND:
            ok, message = load_now(module)
            if not ok:
                print("LateLoader: %s" % message)
            return 0.0

    # Queue empty. Persist what this run measured, once.
    if _timings_dirty:
        write_config()
    return None


# ---------------------------------------------------------------------------
# scanning the installed add-ons
# ---------------------------------------------------------------------------

def enabled_modules():
    """Module names Blender has in preferences, deferred ones included."""
    return sorted(a.module for a in bpy.context.preferences.addons)


def scan():
    """Refresh the label/category table for every add-on on disk.

    Reads bl_info (or the extension manifest) without importing anything, which
    is what lets a deferred, unloaded add-on still show a human name.
    """
    _info.clear()
    try:
        modules = addon_utils.modules(refresh=True)
    except TypeError:
        modules = addon_utils.modules()
    except Exception:
        traceback.print_exc()
        modules = []

    for mod in modules:
        try:
            bl_info = addon_utils.module_bl_info(mod) or {}
        except Exception:
            bl_info = {}
        name = mod.__name__
        _info[name] = (
            bl_info.get("name") or name,
            bl_info.get("category") or "",
            bl_info.get("warning") or "",
        )

    # Forget timings and policies for add-ons that are no longer installed.
    known = set(_info) | set(enabled_modules())
    stale = [m for m in _timings if m not in known]
    stale_policies = [m for m in _policies if m not in known]
    if stale or stale_policies:
        for m in stale:
            _timings.pop(m, None)
        for m in stale_policies:
            _policies.pop(m, None)
        write_config()

    return len(_info)


def label_for(module):
    info = _info.get(module)
    if info:
        return info[0]
    # Not scanned yet, or a manifest that could not be read.
    return module.rpartition(".")[2] or module


def category_for(module):
    info = _info.get(module)
    return info[1] if info else ""


def format_seconds(seconds):
    if seconds is None:
        return "--"
    if seconds >= 1.0:
        return "%.2f s" % seconds
    return "%d ms" % round(seconds * 1000)


def status_for(module):
    """(text, icon) describing where this add-on stands right now."""
    if module in _load_errors:
        return "failed", 'ERROR'
    if module in _pending:
        if policy_for(module) == POLICY_MANUAL:
            return "on demand", 'PAUSE'
        return "loading", 'TIME'
    if policy_for(module) in DEFERRED_POLICIES:
        return "loaded late", 'CHECKMARK'
    return "", 'DOT'


def totals():
    """(measured, deferred, on_critical_path, unmeasured)."""
    measured = 0.0
    deferred = 0.0
    unmeasured = 0
    for module in enabled_modules():
        seconds = _timings.get(module)
        if seconds is None:
            unmeasured += 1
            continue
        measured += seconds
        if policy_for(module) in DEFERRED_POLICIES and module not in NEVER_DEFER:
            deferred += seconds
    return measured, deferred, measured - deferred, unmeasured


# ---------------------------------------------------------------------------
# the add-on list shown in the manager
# ---------------------------------------------------------------------------

VIEW_ITEMS = (
    ('ALL', "All", "Every enabled add-on"),
    ('DEFERRED', "Deferred", "Add-ons with a background or manual policy"),
    ('SLOW', "Slow", "Add-ons measured at or above the slow threshold"),
    ('WAITING', "Waiting", "Deferred add-ons that have not loaded yet"),
)

SORT_ITEMS = (
    ('TIME', "Slowest First", "Order by measured register cost"),
    ('NAME', "Name", "Order by add-on name"),
    ('CATEGORY', "Category", "Group by the add-on's category"),
    ('MODULE', "Module", "Order by module name"),
)

# Set while the list is being rebuilt, so writing item.policy does not bounce
# straight back into the config writer.
_suspending = False


def _policy_updated(self, context):
    if _suspending:
        return
    if self.locked:
        return
    set_policy(self.module, self.policy)


class LATELOADER_PG_addon(bpy.types.PropertyGroup):
    """One row of the manager list."""

    module: bpy.props.StringProperty()
    label: bpy.props.StringProperty()
    category: bpy.props.StringProperty()
    # -1 means "never measured", which sorts and draws differently from 0.
    seconds: bpy.props.FloatProperty(default=-1.0)
    locked: bpy.props.BoolProperty()
    waiting: bpy.props.BoolProperty()
    failed: bpy.props.BoolProperty()
    policy: bpy.props.EnumProperty(
        name="Loads",
        description="When this add-on is loaded",
        items=POLICY_ITEMS,
        update=_policy_updated,
    )


def _sorted_modules(wm):
    modules = enabled_modules()
    cutoff = wm.lateloader_threshold_ms / 1000.0

    view = wm.lateloader_view
    if view == 'DEFERRED':
        modules = [m for m in modules if policy_for(m) in DEFERRED_POLICIES]
    elif view == 'SLOW':
        modules = [m for m in modules if (_timings.get(m) or 0.0) >= cutoff]
    elif view == 'WAITING':
        modules = [m for m in modules if m in _pending]

    needle = wm.lateloader_filter.lower().strip()
    if needle:
        modules = [
            m for m in modules
            if needle in m.lower()
            or needle in label_for(m).lower()
            or needle in category_for(m).lower()
        ]

    sort = wm.lateloader_sort
    if sort == 'TIME':
        # Unmeasured sorts last rather than pretending to be instant.
        modules.sort(key=lambda m: (_timings.get(m) is None,
                                    -(_timings.get(m) or 0.0),
                                    label_for(m).lower()))
    elif sort == 'NAME':
        modules.sort(key=lambda m: label_for(m).lower())
    elif sort == 'CATEGORY':
        modules.sort(key=lambda m: (category_for(m).lower(), label_for(m).lower()))
    else:
        modules.sort()
    return modules


def rebuild(context=None):
    """Refill the list from the current policies, timings and queue state."""
    global _suspending
    wm = (context or bpy.context).window_manager
    items = wm.lateloader_addons

    selected = ""
    if 0 <= wm.lateloader_index < len(items):
        selected = items[wm.lateloader_index].module

    _suspending = True
    try:
        items.clear()
        for module in _sorted_modules(wm):
            item = items.add()
            item.module = module
            item.label = label_for(module)
            item.name = item.label        # what the list's own search filters on
            item.category = category_for(module)
            seconds = _timings.get(module)
            item.seconds = -1.0 if seconds is None else seconds
            item.locked = module in NEVER_DEFER
            item.waiting = module in _pending
            item.failed = module in _load_errors
            item.policy = policy_for(module)
    finally:
        _suspending = False

    wm.lateloader_index = next(
        (i for i, it in enumerate(items) if it.module == selected), 0)


def _view_updated(self, context):
    rebuild(context)


class LATELOADER_UL_addons(bpy.types.UIList):
    """Scrolling add-on list: name, measured cost, and the three policies."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_prop):
        if self.layout_type == 'GRID':
            layout.label(text="", icon=_row_icon(item))
            return

        cutoff = context.window_manager.lateloader_threshold_ms / 1000.0

        split = layout.split(factor=0.50, align=True)

        name = split.row(align=True)
        name.label(text=item.label, icon=_row_icon(item))

        rest = split.row(align=True)

        cost = rest.row(align=True)
        cost.alignment = 'RIGHT'
        cost.ui_units_x = 3.5
        cost.active = item.seconds >= 0.0
        cost.alert = item.seconds >= cutoff
        cost.label(text=format_seconds(None if item.seconds < 0.0 else item.seconds))

        load = rest.row(align=True)
        load.enabled = item.waiting
        op = load.operator(LATELOADER_OT_load.bl_idname, text="", icon='IMPORT', emboss=True)
        op.module = item.module

        policy = rest.row(align=True)
        policy.enabled = not item.locked
        policy.ui_units_x = 11
        policy.prop(item, "policy", expand=True)

    def draw_filter(self, context, layout):
        # Searching and sorting live above the list, on properties that drive
        # what goes into it. The list's own filter would fight with them.
        row = layout.row()
        row.enabled = False
        row.label(text="Use the search and sort above the list")


def _row_icon(item):
    if item.failed:
        return 'ERROR'
    if item.waiting:
        return 'PAUSE' if item.policy == POLICY_MANUAL else 'TIME'
    if item.policy in DEFERRED_POLICIES:
        return 'CHECKMARK'
    return 'DOT'


# ---------------------------------------------------------------------------
# operators
# ---------------------------------------------------------------------------

class LATELOADER_OT_load(bpy.types.Operator):
    """Load this deferred add-on now"""
    bl_idname = "lateloader.load"
    bl_label = "Load Add-on"
    bl_options = {'REGISTER', 'INTERNAL'}

    module: bpy.props.StringProperty(name="Module")

    def execute(self, context):
        ok, message = load_now(self.module)
        rebuild(context)
        self.report({'INFO'} if ok else {'ERROR'}, message)
        return {'FINISHED'} if ok else {'CANCELLED'}


class LATELOADER_OT_load_all(bpy.types.Operator):
    """Load every add-on still waiting, including manual ones"""
    bl_idname = "lateloader.load_all"
    bl_label = "Load All Deferred Add-ons"
    bl_options = {'REGISTER'}

    def execute(self, context):
        failed = []
        count = 0
        for module in pending():
            ok, message = load_now(module)
            if ok:
                count += 1
            else:
                failed.append(message)

        rebuild(context)
        for message in failed:
            self.report({'ERROR'}, message)
        self.report({'INFO'}, "LateLoader: loaded %d add-on(s)" % count)
        return {'FINISHED'}


class LATELOADER_OT_set_policy(bpy.types.Operator):
    """Change when this add-on loads, from the next Blender start onward"""
    bl_idname = "lateloader.set_policy"
    bl_label = "Set Load Policy"
    bl_options = {'REGISTER', 'INTERNAL'}

    module: bpy.props.StringProperty(name="Module")
    policy: bpy.props.EnumProperty(name="Policy", items=POLICY_ITEMS)

    def execute(self, context):
        if self.module in NEVER_DEFER and self.policy != POLICY_STARTUP:
            self.report({'WARNING'}, "%s is never deferred" % self.module)
            return {'CANCELLED'}
        if not set_policy(self.module, self.policy):
            self.report({'ERROR'}, "Could not write %s" % config_path())
            return {'CANCELLED'}
        rebuild(context)
        return {'FINISHED'}


class LATELOADER_OT_scan(bpy.types.Operator):
    """Re-read the add-ons installed on disk"""
    bl_idname = "lateloader.scan"
    bl_label = "Rescan Add-ons"
    bl_options = {'REGISTER'}

    def execute(self, context):
        found = scan()
        rebuild(context)
        self.report({'INFO'}, "LateLoader: %d add-on(s) installed, %d enabled"
                    % (found, len(enabled_modules())))
        return {'FINISHED'}


class LATELOADER_OT_defer_slow(bpy.types.Operator):
    """Set every add-on measured at or above the threshold to Background"""
    bl_idname = "lateloader.defer_slow"
    bl_label = "Defer Slow Add-ons"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        threshold_ms = context.window_manager.lateloader_threshold_ms
        cutoff = threshold_ms / 1000.0
        changed = 0
        for module in enabled_modules():
            if module in NEVER_DEFER:
                continue
            seconds = _timings.get(module)
            if seconds is None or seconds < cutoff:
                continue
            if policy_for(module) != POLICY_STARTUP:
                continue
            _policies[module] = POLICY_BACKGROUND
            changed += 1

        if not changed:
            self.report({'INFO'}, "Nothing left to defer at or above %d ms" % threshold_ms)
            return {'CANCELLED'}
        if not write_config():
            self.report({'ERROR'}, "Could not write %s" % config_path())
            return {'CANCELLED'}
        rebuild(context)
        self.report({'INFO'}, "Deferred %d add-on(s)" % changed)
        return {'FINISHED'}


class LATELOADER_OT_clear_policies(bpy.types.Operator):
    """Put every add-on back on Startup"""
    bl_idname = "lateloader.clear_policies"
    bl_label = "Clear All Policies"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        if not _policies:
            self.report({'INFO'}, "Nothing is deferred")
            return {'CANCELLED'}
        count = len(_policies)
        _policies.clear()
        if not write_config():
            self.report({'ERROR'}, "Could not write %s" % config_path())
            return {'CANCELLED'}
        rebuild(context)
        self.report({'INFO'}, "Cleared %d policy/policies" % count)
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# the manager dialog
# ---------------------------------------------------------------------------

class LATELOADER_OT_manage(bpy.types.Operator):
    """Choose which add-ons are kept out of Blender's startup"""
    bl_idname = "lateloader.manage"
    bl_label = "LateLoader: Manage Add-on Loading"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        scan()
        rebuild(context)
        wm = context.window_manager
        try:
            return wm.invoke_props_dialog(
                self, width=640, title="LateLoader", confirm_text="Close")
        except TypeError:
            # Older Blender, without title/confirm_text.
            return wm.invoke_props_dialog(self, width=640)

    def execute(self, context):
        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager

        self._draw_summary(layout, context)

        row = layout.row(align=True)
        row.prop(wm, "lateloader_threshold_ms", text="Slow above (ms)")
        row.operator(LATELOADER_OT_defer_slow.bl_idname,
                     text="Defer Everything Slower", icon='SORTTIME')
        row.operator(LATELOADER_OT_scan.bl_idname, text="", icon='FILE_REFRESH')
        row.operator(LATELOADER_OT_clear_policies.bl_idname, text="", icon='X')

        row = layout.row(align=True)
        row.prop(wm, "lateloader_view", expand=True)

        row = layout.row(align=True)
        row.prop(wm, "lateloader_filter", text="", icon='VIEWZOOM')
        row.prop(wm, "lateloader_sort", text="")

        if not len(wm.lateloader_addons):
            box = layout.box()
            box.label(text="No add-on matches this view", icon='INFO')
            return

        layout.template_list(
            "LATELOADER_UL_addons", "",
            wm, "lateloader_addons",
            wm, "lateloader_index",
            rows=14,
        )

        self._draw_selected(layout, context)

    def _draw_summary(self, layout, context):
        measured, deferred, critical, unmeasured = totals()
        enabled = enabled_modules()
        deferred_count = len([m for m in enabled if policy_for(m) in DEFERRED_POLICIES])
        waiting = pending()

        box = layout.box()
        row = box.row()

        left = row.column()
        left.scale_y = 0.9
        left.label(text="%d add-ons enabled, %d deferred" % (len(enabled), deferred_count),
                   icon='PREFERENCES')
        if unmeasured:
            left.label(text="%d not measured yet - restart Blender once to time them"
                            % unmeasured, icon='QUESTION')
        else:
            left.label(text="Every enabled add-on has been measured", icon='CHECKMARK')

        right = row.column()
        right.scale_y = 0.9
        right.alignment = 'RIGHT'
        if measured:
            right.label(text="On startup: %s" % format_seconds(critical))
            right.label(text="Deferred: %s" % format_seconds(deferred))
        else:
            right.label(text="No timings yet")

        if waiting:
            row = box.row(align=True)
            row.label(text="%d add-on(s) still waiting" % len(waiting), icon='SORTTIME')
            row.operator(LATELOADER_OT_load_all.bl_idname, text="Load All Now", icon='IMPORT')

    def _draw_selected(self, layout, context):
        wm = context.window_manager
        if not (0 <= wm.lateloader_index < len(wm.lateloader_addons)):
            return
        item = wm.lateloader_addons[wm.lateloader_index]

        row = layout.row()
        row.scale_y = 0.8
        row.enabled = False

        detail = item.module
        if item.category:
            detail = "%s  -  %s" % (detail, item.category)
        if item.locked:
            detail += "  -  never deferred"
        elif item.failed:
            detail += "  -  failed to load, see the console"
        row.label(text=detail, icon='SCRIPT')

        note = layout.row()
        note.scale_y = 0.8
        note.enabled = False
        note.label(text="Policy changes apply from the next Blender start. "
                        "Times are measured register cost.", icon='INFO')


classes = (
    LATELOADER_PG_addon,
    LATELOADER_UL_addons,
    LATELOADER_OT_load,
    LATELOADER_OT_load_all,
    LATELOADER_OT_set_policy,
    LATELOADER_OT_scan,
    LATELOADER_OT_defer_slow,
    LATELOADER_OT_clear_policies,
    LATELOADER_OT_manage,
)


def menu_draw(self, context):
    self.layout.operator(LATELOADER_OT_manage.bl_idname, icon='TIME')


# ---------------------------------------------------------------------------
# startup
# ---------------------------------------------------------------------------

def _install_hook():
    """Patch addon_utils.enable before Blender's startup enable loop runs."""
    global _orig_enable

    # Headless Blender has no interactive user to load add-ons on demand, and a
    # render or batch script needs everything present. Never defer there.
    if bpy.app.background:
        return

    policies, timings = read_config()
    _policies.update(policies)
    _timings.update(timings)

    # Installed even with an empty config: the hook is also what measures each
    # add-on, and the first run is exactly when there is nothing to defer yet
    # and everything to measure.
    _orig_enable = addon_utils.enable
    addon_utils.enable = _patched_enable

    # Fires once the event loop is running, which is after the startup enable
    # loop has finished. Restores enable() and drains the background queue.
    bpy.app.timers.register(_drain_one, first_interval=0.0)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    wm = bpy.types.WindowManager
    wm.lateloader_addons = bpy.props.CollectionProperty(type=LATELOADER_PG_addon)
    wm.lateloader_index = bpy.props.IntProperty(name="Add-on")
    wm.lateloader_view = bpy.props.EnumProperty(
        name="Show", items=VIEW_ITEMS, default='ALL', update=_view_updated)
    wm.lateloader_sort = bpy.props.EnumProperty(
        name="Sort", items=SORT_ITEMS, default='TIME', update=_view_updated)
    wm.lateloader_filter = bpy.props.StringProperty(
        name="Search",
        description="Show only add-ons whose name, module or category matches",
        options={'TEXTEDIT_UPDATE'},
        update=_view_updated,
    )
    wm.lateloader_threshold_ms = bpy.props.IntProperty(
        name="Slow Above",
        description="Register cost at which an add-on counts as slow",
        default=int(SLOW_SECONDS * 1000), min=1, max=10000,
        update=_view_updated,
    )

    bpy.types.TOPBAR_MT_blender.append(menu_draw)


def unregister():
    bpy.types.TOPBAR_MT_blender.remove(menu_draw)

    wm = bpy.types.WindowManager
    for prop in ("lateloader_addons", "lateloader_index", "lateloader_view",
                 "lateloader_sort", "lateloader_filter", "lateloader_threshold_ms"):
        if hasattr(wm, prop):
            delattr(wm, prop)

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    _restore_enable()
    if bpy.app.timers.is_registered(_drain_one):
        bpy.app.timers.unregister(_drain_one)


# Runs at import time, which for a startup script is before add-ons are
# enabled. register() is called by Blender later and is too late for the hook.
# Wrapped because nothing here is worth failing a Blender launch over.
try:
    _install_hook()
except Exception:
    print("LateLoader: failed to install startup hook, loading add-ons normally")
    traceback.print_exc()
