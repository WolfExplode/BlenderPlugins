import bpy
import numpy as np
from bpy.app.handlers import persistent
from bpy.props import BoolProperty

from .ops import _get_weights, _normalize_others

# mesh name -> (active group index, weights array) from the last handler pass
_cache = {}
_updating = False
_pending = False
_prev_native = None


def scope_indices(obj, active_index):
    """Vertex-group indices of the selected bones, or None for stock behavior.

    Returns None (normalize across all unlocked groups, like Blender's native
    auto-normalize) unless 2+ bones are selected on the deforming armature and
    the active group is one of them.
    """
    arm = obj.find_armature()
    if arm is None or arm.pose is None:
        return None
    # Blender 5.x moved bone selection from Bone.select to PoseBone.select
    if bpy.app.version >= (5, 0, 0):
        names = [pb.name for pb in arm.pose.bones if pb.select]
    else:
        names = [pb.name for pb in arm.pose.bones if pb.bone.select]
    if len(names) < 2:
        return None
    indices = {
        obj.vertex_groups[name].index
        for name in names
        if name in obj.vertex_groups
    }
    if len(indices) < 2 or active_index not in indices:
        return None
    return indices


@persistent
def _on_depsgraph_update(scene, depsgraph):
    """Cheap per-dab callback: just schedule the heavy pass.

    Brush strokes fire one depsgraph update per dab; doing an O(vertices)
    read here would lag painting. Instead, coalesce dabs into a single
    throttled timer pass (the last dab of a stroke always schedules one).
    """
    global _pending
    if _updating or _pending or not getattr(scene, "bweight_scoped_normalize", False):
        return
    context = bpy.context
    if context.mode != 'PAINT_WEIGHT':
        return
    obj = context.active_object
    if obj is None or obj.type != 'MESH':
        return
    for update in depsgraph.updates:
        if update.id.original == obj and update.is_updated_geometry:
            _pending = True
            bpy.app.timers.register(_process, first_interval=0.05)
            return


def _process():
    global _pending, _updating
    _pending = False
    context = bpy.context
    scene = context.scene
    if (scene is None
            or not getattr(scene, "bweight_scoped_normalize", False)
            or context.mode != 'PAINT_WEIGHT'):
        return None
    obj = context.active_object
    if obj is None or obj.type != 'MESH':
        return None
    vgroup = obj.vertex_groups.active
    if vgroup is None or vgroup.lock_weight or len(obj.vertex_groups) < 2:
        return None

    mesh = obj.data
    weights, _ = _get_weights(mesh, vgroup.index)
    key = mesh.name
    cached = _cache.get(key)
    if (cached is None
            or cached[0] != vgroup.index
            or cached[1].shape[0] != weights.shape[0]):
        _cache[key] = (vgroup.index, weights)
        return None
    changed = np.nonzero(np.abs(weights - cached[1]) > 1e-7)[0]
    if changed.size == 0:
        return None

    locked = {vg.index for vg in obj.vertex_groups if vg.lock_weight}
    allowed = scope_indices(obj, vgroup.index)
    _updating = True
    try:
        applied = _normalize_others(
            obj, vgroup.index, changed, weights[changed], locked, allowed,
            old_active_weights=cached[1][changed],
        )
        clamped = np.abs(applied - weights[changed]) > 1e-7
        if clamped.any():
            clamped_indices = changed[clamped]
            values, groups = np.unique(applied[clamped], return_inverse=True)
            add = vgroup.add
            for gi, value in enumerate(values):
                add(clamped_indices[groups == gi].tolist(), float(value), 'REPLACE')
        weights[changed] = applied
        _cache[key] = (vgroup.index, weights)
        mesh.update()
    finally:
        _updating = False
    return None


def _toggle_update(self, context):
    global _prev_native
    tool_settings = context.tool_settings
    if self.bweight_scoped_normalize:
        _prev_native = tool_settings.use_auto_normalize
        tool_settings.use_auto_normalize = False
    else:
        if _prev_native is not None:
            tool_settings.use_auto_normalize = _prev_native
        _prev_native = None
        _cache.clear()


def _draw_options(self, context):
    layout = self.layout
    scene = context.scene
    col = layout.column()
    col.prop(scene, "bweight_scoped_normalize", text="Auto Normalize (Scoped)")
    if not scene.bweight_scoped_normalize:
        return
    obj = context.active_object
    if obj is None or obj.type != 'MESH' or obj.vertex_groups.active is None:
        return
    scope = scope_indices(obj, obj.vertex_groups.active.index)
    if scope is not None:
        col.label(text=f"Scope: {len(scope)} bones", icon='BONE_DATA')
    else:
        col.label(text="Scope: all groups (select 2+ bones)", icon='INFO')


def register():
    bpy.types.Scene.bweight_scoped_normalize = BoolProperty(
        name="Auto Normalize (Scoped)",
        description=(
            "Replace Auto Normalize: with 2+ bones selected (active bone "
            "included), weight painted off the active bone moves to the other "
            "selected bones (and vice versa), conserving their combined total; "
            "otherwise behave like normal Auto Normalize"
        ),
        default=False,
        update=_toggle_update,
    )
    bpy.types.VIEW3D_PT_tools_weightpaint_options.append(_draw_options)
    bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)


def unregister():
    global _pending
    if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)
    if bpy.app.timers.is_registered(_process):
        bpy.app.timers.unregister(_process)
    _pending = False
    bpy.types.VIEW3D_PT_tools_weightpaint_options.remove(_draw_options)
    del bpy.types.Scene.bweight_scoped_normalize
    _cache.clear()
