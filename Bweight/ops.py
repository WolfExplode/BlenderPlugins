import bpy
import numpy as np
from bpy.props import EnumProperty, FloatProperty, IntProperty


def _editable_mask(mesh):
    """Boolean per-vertex mask of editable vertices under the current paint mask."""
    n = len(mesh.vertices)
    if mesh.use_paint_mask_vertex:
        mask = np.zeros(n, dtype=bool)
        mesh.vertices.foreach_get("select", mask)
        return mask
    if mesh.use_paint_mask:
        poly_sel = np.zeros(len(mesh.polygons), dtype=bool)
        mesh.polygons.foreach_get("select", poly_sel)
        loop_total = np.zeros(len(mesh.polygons), dtype=np.int32)
        mesh.polygons.foreach_get("loop_total", loop_total)
        loop_verts = np.zeros(len(mesh.loops), dtype=np.int32)
        mesh.loops.foreach_get("vertex_index", loop_verts)
        mask = np.zeros(n, dtype=bool)
        mask[loop_verts[np.repeat(poly_sel, loop_total)]] = True
        return mask
    return np.ones(n, dtype=bool)


def _get_weights(mesh, group_index):
    n = len(mesh.vertices)
    weights = np.zeros(n, dtype=np.float64)
    in_group = np.zeros(n, dtype=bool)
    for v in mesh.vertices:
        for g in v.groups:
            if g.group == group_index:
                weights[v.index] = g.weight
                in_group[v.index] = True
                break
    return weights, in_group


def _normalize_others(mesh, active_index, indices, new_active_weights, locked_indices):
    """Redistribute the remainder across each vertex's other unlocked groups,
    matching Blender's weight-paint auto-normalize behavior. Returns the
    (possibly clamped) active weights actually applied."""
    applied = new_active_weights.copy()
    for k, i in enumerate(indices):
        vertex = mesh.vertices[i]
        locked_sum = 0.0
        others = []
        for g in vertex.groups:
            if g.group == active_index:
                continue
            if g.group in locked_indices:
                locked_sum += g.weight
            else:
                others.append(g)
        room = max(0.0, 1.0 - locked_sum)
        active_w = min(new_active_weights[k], room)
        applied[k] = active_w
        remaining = room - active_w
        others_sum = sum(g.weight for g in others)
        if others_sum > 1e-8:
            scale = remaining / others_sum
            for g in others:
                g.weight *= scale
    return applied


class PAINT_OT_bweight_filter(bpy.types.Operator):
    bl_idname = "paint.bweight_filter"
    bl_label = "Weight Filter"
    bl_description = "Filter the active vertex group's weights"
    bl_options = {'REGISTER', 'UNDO'}

    filter_type: EnumProperty(
        name="Type",
        items=(
            ('SMOOTH', "Smooth", "Blend each weight towards the average of its neighbors"),
            ('SHARPEN', "Sharpen", "Push each weight away from the average of its neighbors"),
            ('GROW', "Grow", "Expand weights outward by taking the neighborhood maximum"),
            ('SHRINK', "Shrink", "Contract weights inward by taking the neighborhood minimum"),
        ),
        default='SMOOTH',
    )
    strength: FloatProperty(
        name="Strength",
        description="Blend factor for smooth/sharpen",
        default=0.5, min=0.0, max=1.0,
    )
    iterations: IntProperty(
        name="Iterations",
        default=1, min=1, max=100,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (
            context.mode == 'PAINT_WEIGHT'
            and obj is not None
            and obj.type == 'MESH'
        )

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data
        vgroup = obj.vertex_groups.active
        if vgroup is None:
            self.report({'WARNING'}, "No active vertex group")
            return {'CANCELLED'}
        if vgroup.lock_weight:
            self.report({'WARNING'}, f"Vertex group '{vgroup.name}' is locked")
            return {'CANCELLED'}

        n = len(mesh.vertices)
        edges = np.zeros(len(mesh.edges) * 2, dtype=np.int32)
        mesh.edges.foreach_get("vertices", edges)
        edges = edges.reshape(-1, 2)
        ea, eb = edges[:, 0], edges[:, 1]
        degree = np.bincount(edges.ravel(), minlength=n)
        connected = degree > 0

        weights, in_group = _get_weights(mesh, vgroup.index)
        original = weights.copy()
        editable = _editable_mask(mesh)

        for _ in range(self.iterations):
            if self.filter_type in {'GROW', 'SHRINK'}:
                new = weights.copy()
                op = np.maximum if self.filter_type == 'GROW' else np.minimum
                op.at(new, ea, weights[eb])
                op.at(new, eb, weights[ea])
            else:
                total = (np.bincount(ea, weights[eb], minlength=n)
                         + np.bincount(eb, weights[ea], minlength=n))
                avg = total / np.maximum(degree, 1)
                if self.filter_type == 'SMOOTH':
                    new = weights + (avg - weights) * self.strength
                else:  # SHARPEN
                    new = weights + (weights - avg) * self.strength
                new[~connected] = weights[~connected]
            np.clip(new, 0.0, 1.0, out=new)
            weights = np.where(editable, new, weights)

        changed = (
            editable
            & (in_group | (weights > 0.0))
            & (np.abs(weights - original) > 1e-7)
        )
        indices = np.nonzero(changed)[0]
        final_weights = weights[indices]

        if context.tool_settings.use_auto_normalize and len(obj.vertex_groups) > 1:
            locked_indices = {vg2.index for vg2 in obj.vertex_groups if vg2.lock_weight}
            final_weights = _normalize_others(
                mesh, vgroup.index, indices, final_weights, locked_indices,
            )

        # vgroup.add takes one weight per call, so batch vertices sharing a value
        values, groups = np.unique(final_weights, return_inverse=True)
        add = vgroup.add
        for gi, value in enumerate(values):
            add(indices[groups == gi].tolist(), float(value), 'REPLACE')

        mesh.update()
        return {'FINISHED'}


classes = (PAINT_OT_bweight_filter,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
