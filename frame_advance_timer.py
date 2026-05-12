bl_info = {
    "name": "Frame Advance Timer",
    "author": "WXP",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Tool > Frame Advance",
    "description": "Advance the timeline by one frame every N seconds",
    "category": "Animation",
}

import time

import bpy
from bpy.props import BoolProperty, FloatProperty, PointerProperty
from bpy.types import Operator, Panel, PropertyGroup

_UI_REFRESH_INTERVAL = 0.1


class FrameAdvanceTimerProperties(PropertyGroup):
    interval: FloatProperty(
        name="Seconds",
        description="Wait this many seconds before advancing to the next frame",
        default=1.0,
        min=0.01,
        max=86400.0,
        soft_min=0.1,
        soft_max=120.0,
        unit="TIME",
    )
    running: BoolProperty(
        name="Running",
        description="Timer is advancing frames (internal state)",
        default=False,
    )
    next_advance_mono: FloatProperty(
        name="Next Advance",
        description="Monotonic clock value when the next frame advance is due",
        default=0.0,
        options={"HIDDEN"},
    )


def _tag_view3d_ui_redraw():
    wm = bpy.context.window_manager
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            for region in area.regions:
                if region.type == "UI":
                    region.tag_redraw()


def _ui_refresh_timer():
    if not any(s.frame_advance_timer.running for s in bpy.data.scenes):
        return None
    _tag_view3d_ui_redraw()
    return _UI_REFRESH_INTERVAL


def _stop_ui_refresh_timer_safe():
    try:
        bpy.app.timers.unregister(_ui_refresh_timer)
    except ValueError:
        pass


def _stop_running(scene):
    props = scene.frame_advance_timer
    props.running = False
    _stop_timer_safe()
    _stop_ui_refresh_timer_safe()
    _tag_view3d_ui_redraw()


def _frame_advance_timer():
    try:
        scene = bpy.context.scene
    except Exception:
        return None

    props = scene.frame_advance_timer
    if not props.running:
        return None

    if scene.frame_current >= scene.frame_end:
        _stop_running(scene)
        return None

    scene.frame_current += 1
    props.next_advance_mono = time.monotonic() + props.interval

    if scene.frame_current >= scene.frame_end:
        _stop_running(scene)
        return None

    return props.interval


def _stop_timer_safe():
    try:
        bpy.app.timers.unregister(_frame_advance_timer)
    except ValueError:
        pass


class FRAME_ADV_OT_start(Operator):
    bl_idname = "frame_advance_timer.start"
    bl_label = "Start"
    bl_description = "Begin advancing one frame per interval"

    def execute(self, context):
        props = context.scene.frame_advance_timer
        if props.running:
            self.report({"INFO"}, "Already running")
            return {"CANCELLED"}

        props.running = True
        props.next_advance_mono = time.monotonic() + props.interval
        bpy.app.timers.register(_frame_advance_timer, first_interval=props.interval)
        _stop_ui_refresh_timer_safe()
        bpy.app.timers.register(_ui_refresh_timer, first_interval=0.05)
        _tag_view3d_ui_redraw()
        return {"FINISHED"}


class FRAME_ADV_OT_stop(Operator):
    bl_idname = "frame_advance_timer.stop"
    bl_label = "Stop"
    bl_description = "Stop advancing frames"

    def execute(self, context):
        _stop_running(context.scene)
        return {"FINISHED"}


class VIEW3D_PT_frame_advance_timer(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Tool"
    bl_label = "Frame Advance"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.frame_advance_timer

        box = layout.box()
        box.label(text="Timer", icon="TIME")
        sub = box.column(align=True)
        sub.label(text=f"Frame {scene.frame_current}", icon="SEQUENCE")
        if props.running:
            remaining = max(0.0, props.next_advance_mono - time.monotonic())
            sub.label(text=f"Next in {remaining:5.2f} s")
        else:
            sub.label(text="Stopped")

        layout.separator()
        layout.prop(props, "interval")
        row = layout.row(align=True)
        row.enabled = not props.running
        row.operator(FRAME_ADV_OT_start.bl_idname, text="Start", icon="PLAY")
        row = layout.row(align=True)
        row.enabled = props.running
        row.operator(FRAME_ADV_OT_stop.bl_idname, text="Stop", icon="PAUSE")


classes = (
    FrameAdvanceTimerProperties,
    FRAME_ADV_OT_start,
    FRAME_ADV_OT_stop,
    VIEW3D_PT_frame_advance_timer,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.frame_advance_timer = PointerProperty(type=FrameAdvanceTimerProperties)


def unregister():
    # Ensure timer does not keep running after addon disable
    for scene in bpy.data.scenes:
        if scene.frame_advance_timer.running:
            scene.frame_advance_timer.running = False
    _stop_timer_safe()
    _stop_ui_refresh_timer_safe()

    del bpy.types.Scene.frame_advance_timer
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
