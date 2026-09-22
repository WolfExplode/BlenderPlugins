# LateLoader

Keep add-ons out of Blender's startup critical path. That is the whole job.

Blender enables every add-on in your preferences before it draws anything, so a
pile of add-ons is time spent staring at nothing. LateLoader skips the slow ones
during startup and loads them a moment later, once the window is already up.

Measured on this machine, Blender 5.1, 68 add-ons enabled. Time from launching
`blender.exe` to the first viewport draw — the moment you can actually see your
scene:

| | First viewport draw |
| --- | --- |
| Without LateLoader | 4.88s |
| 11 add-ons deferred | **2.97s** |
| 58 add-ons deferred | **2.42s** |
| *(for scale)* Blender 5.1 with no add-ons at all | 1.75s |

The deferred add-ons finish loading in the background about a second later —
before the undeferred configuration would have drawn its first frame. Carrying
all 68 add-ons costs 0.67s over a bare Blender, rather than 3.1s.

Measure this with a `SpaceView3D` draw handler, not by timing the process.
LateLoader *moves* work off the critical path rather than removing it, so the
process takes the same wall-clock time either way and a stopwatch on
`blender.exe` will tell you nothing has changed.

## Why this is not an add-on

It is a **startup script**. Blender enables add-ons from preferences during
startup, and only scripts in `scripts/startup/` run before that happens. An
add-on installed the normal way registers long after the work it is meant to
avoid.

Install by copying one file:

```
C:\Users\<you>\AppData\Roaming\Blender Foundation\Blender\5.1\scripts\startup\LateLoader.py
```

Create the `startup` folder if it is not there. Uninstall by deleting the file.
There is nothing else to undo.

## What it does not do

It **never patches Blender's installation.** CleanPanels implements the same
idea by overwriting `addon_utils.py` inside `Program Files`, which needs write
access there and is silently reverted by every Blender update — leaving you
slower with no indication why. LateLoader replaces one function in memory,
for the duration of startup, and puts it back.

It **never disables an add-on or edits your preferences.** A deferred add-on
stays in `prefs.addons` exactly as before; it is simply not registered yet.
Verified: all 68 preference entries survive a `save_userpref()` while deferred.

It does not manage panels, categories, keymaps or anything else. One goal.

## Policies

Set per add-on, stored in `<Blender config>/LateLoader.json`:

| Policy | Behaviour |
| --- | --- |
| `startup` | Load during startup, as normal. The default for anything unlisted. |
| `background` | Skip startup, load automatically once the window is up. |
| `manual` | Skip startup, load only when asked. |

`background` is the one you want for most slow add-ons. The window appears
without waiting for them and they finish loading a second or so later, long
before you reach for a tool. Nothing is lost.

`manual` is for add-ons you rarely touch in a given session — importers for
formats you use monthly, for example. These stay unloaded until you ask.

Changes apply from the next Blender start. The config is plain JSON and can be
edited by hand:

```json
{
  "policies": {
    "bl_ext.user_default.hardops": "background",
    "SimpleBake": "background",
    "bl_ext.blender_org.io_scene_psk_psa": "manual"
  },
  "timings": {
    "SimpleBake": 0.3114,
    "bl_ext.user_default.hardops": 1.4022
  }
}
```

Module names are what appears in `bpy.context.preferences.addons` — extensions
carry their full `bl_ext.<repo>.<name>` path. `timings` is measured, not
configured; delete it and it is measured again on the next start.

## Measuring

LateLoader holds `addon_utils.enable` for the length of startup anyway, so it
times every add-on it lets through and remembers what each one cost. That is the
number the manager sorts on — deciding what to defer from module names alone is
guesswork, and the expensive add-ons are rarely the ones you would pick.

The first run after installing measures everything and defers nothing, because
there is nothing configured yet. From the second run on, every add-on in the
list has a cost next to it. A deferred add-on is timed when it loads in the
background, which costs the same as loading it during startup would have.

## Using it

The Blender icon menu (top left) gains **LateLoader: Manage Add-on Loading**,
also reachable from F3 search. Opening it rescans the add-ons installed on disk,
so the list is always what you have, under the names the Preferences
window uses rather than module paths.

The dialog shows:

- **A summary.** How many add-ons are enabled, how many are deferred, how much
  time is still on the startup path and how much has been moved off it.
- **Slow above (ms) / Defer Everything Slower.** One click puts every add-on
  measured at or above the threshold on `background`. The fastest way to a
  configuration that is worth having; adjust individual add-ons afterwards.
- **A scrolling list** of every enabled add-on with its measured cost, anything
  at or above the threshold marked. Search by name, module or category; sort by
  cost, name, category or module; filter to **Deferred**, **Slow** or
  **Waiting**.
- **Three buttons per row** — Startup, Background, Manual — and an import button
  to load a waiting add-on right now.

The icon at the left of each row is its current state: `·` loads at startup,
a tick loaded late, a clock waiting in the background queue, a pause icon
waiting on you, a warning triangle failed to load.

Operators, for keymaps or scripting:

| Operator | Does |
| --- | --- |
| `lateloader.manage` | Open the dialog |
| `lateloader.scan` | Rescan installed add-ons |
| `lateloader.load_all` | Load everything still waiting, `manual` included |
| `lateloader.load(module=...)` | Load one add-on now |
| `lateloader.set_policy(module=..., policy=...)` | Change a policy |
| `lateloader.defer_slow` | Defer everything at or above the threshold |
| `lateloader.clear_policies` | Put every add-on back on `startup` |

## Behaviour worth knowing

**Headless Blender never defers.** A `--background` render or batch script needs
every add-on present and has no interactive user to load them on demand, so the
hook does not install at all when `bpy.app.background` is true.

**A deferred add-on's operators, panels and keymaps do not exist until it
loads.** This is unavoidable — an unregistered add-on has registered nothing,
so there is no way to trigger it and no hook to catch the attempt. It is also
why `background` rather than true load-on-first-use is the right default: the
gap is a second or two at the start of a session, not a missing feature.

**Load order is preserved.** Deferred add-ons are loaded in the order Blender
would have enabled them, so add-ons that depend on each other still see the
same relative order.

**Deferring a dependency of an eager add-on will not work.** Order is only
preserved *among* deferred add-ons — anything left on `startup` still registers
first, before the deferred queue exists. If add-on A inspects or hooks add-on B
at register time, deferring B while A loads eagerly means A finds nothing.
[Guard Edit Mode for MACHIN3tools](../Guard%20Edit%20Mode%20for%20MACHIN3tools)
is the example in this repository: it looks up `machin3.*` operators when it
registers, so deferring MACHIN3tools without deferring it too leaves it inert.
Give both the same policy, or leave the dependency on `startup`.

**`bl_pkg` and `cycles` are never deferred**, whatever the config says. Blender's
extension plumbing and the render engine are load-bearing during startup.

**An add-on needed at file load is a bad fit for `manual`.** If a `.blend`
depends on an add-on's custom nodes, modifiers or handlers, opening that file
before the add-on loads will not resolve them. Use `startup` or `background`
for anything in that category.

**A broken config defers nothing.** Unreadable or malformed JSON is reported to
the console and startup proceeds normally. The hook is wrapped so that nothing
here can stop Blender from launching.

**The hook installs even with an empty config.** It has to, or the first run
would have nothing to measure and the manager would open empty. With no
policies set it defers nothing and only times what passes through, which is a
`perf_counter` call per add-on.

## Notes

Background loading runs one add-on per event-loop tick rather than all at once,
so the queue empties without freezing the window and a slow add-on costs one
stutter instead of a stall.

Developed against Blender 5.1. The hook relies on `addon_utils.enable` being the
function Blender's startup calls for each preference entry, which has been true
across the 4.x and 5.x line; if a future release changes that, LateLoader stops
deferring rather than breaking anything.

Background on how the startup cost was measured in the first place — and why
wall-clock timing of the Blender process hides this entirely — is in
`../blender-mcp/docs/startup_profiling_notes.md`.
