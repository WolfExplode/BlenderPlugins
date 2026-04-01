"""
Deduplicate Blender exported keyconfig_data items (per section) and drop inactive shortcuts.

Run: python clean_keymaps.py [path-to-Blender Keymaps 5_0.py]
Default path is this repo's keymap file next to this script.
"""
from __future__ import annotations

import pprint
import sys
from pathlib import Path


def _freeze(x):
    if isinstance(x, dict):
        return tuple((k, _freeze(v)) for k, v in x.items())
    if isinstance(x, (list, tuple)):
        return tuple(_freeze(i) for i in x)
    return x


def _item_signature(it: tuple) -> tuple:
    if not isinstance(it, tuple) or not it:
        return ("__non_keymap__", _freeze(it))
    op = it[0]
    kd = it[1] if len(it) > 1 else {}
    pr = it[2] if len(it) > 2 else None
    if pr is None or pr == {}:
        pr_f: tuple = ()
    else:
        pr_f = _freeze(pr)
    return (op, _freeze(kd), pr_f)


def _is_inactive(it: tuple) -> bool:
    if len(it) < 3 or not isinstance(it[2], dict):
        return False
    return it[2].get("active") is False


def clean_keyconfig_data(keyconfig_data: list) -> tuple[list, dict]:
    stats = {
        "sections": 0,
        "items_before": 0,
        "items_after": 0,
        "removed_inactive": 0,
        "removed_duplicate": 0,
    }
    out: list = []
    for block in keyconfig_data:
        if not isinstance(block, tuple) or len(block) < 3:
            out.append(block)
            continue
        stats["sections"] += 1
        name, region, body = block[0], block[1], block[2]
        if not isinstance(body, dict) or "items" not in body:
            out.append(block)
            continue
        items = body["items"]
        stats["items_before"] += len(items)
        seen: set = set()
        new_items = []
        for it in items:
            if not isinstance(it, tuple):
                new_items.append(it)
                continue
            if _is_inactive(it):
                stats["removed_inactive"] += 1
                continue
            sig = _item_signature(it)
            if sig in seen:
                stats["removed_duplicate"] += 1
                continue
            seen.add(sig)
            new_items.append(it)
        stats["items_after"] += len(new_items)
        out.append((name, region, {"items": new_items}))
    return out, stats


def main() -> int:
    default = Path(__file__).resolve().parent / "Blender Keymaps 5_0.py"
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    text = path.read_text(encoding="utf-8")
    marker = '\nif __name__ == "__main__":'
    idx = text.find(marker)
    if idx == -1:
        print("Could not find if __name__ block; aborting.", file=sys.stderr)
        return 1
    header = text[:idx]
    footer = text[idx:]

    ns: dict = {"__name__": "_keyconfig_clean"}
    exec(compile(header + "\n", str(path), "exec"), ns)
    version = ns.get("keyconfig_version")
    data = ns.get("keyconfig_data")
    if data is None:
        print("keyconfig_data missing after exec.", file=sys.stderr)
        return 1

    cleaned, stats = clean_keyconfig_data(data)

    body = [
        f"keyconfig_version = {version!r}",
        "keyconfig_data = \\",
        pprint.pformat(cleaned, width=100, sort_dicts=False),
        "",
    ]
    new_text = "\n".join(body) + footer
    path.write_text(new_text, encoding="utf-8")

    print(f"Wrote: {path}")
    print(
        f"Sections processed: {stats['sections']}, "
        f"items {stats['items_before']} -> {stats['items_after']} "
        f"(inactive -{stats['removed_inactive']}, dupes -{stats['removed_duplicate']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
