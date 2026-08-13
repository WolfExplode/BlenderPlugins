"""Packages each add-on into a zip named after its docs slug (e.g. dist/bweight.zip).

The docs site links to `.../releases/latest/download/<slug>.zip`, so these
filenames must stay in sync with the slugs used under docs/addons/.

Usage:
    python scripts/package_addons.py [--out dist]
"""
import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# slug -> ("dir" | "file", path relative to repo root)
ADDONS = {
    "bweight": ("dir", "Bweight"),
    "cyclic-animation-baker": ("dir", "cyclic animation"),
    "gizmo-plus": ("dir", "gizmo_plus"),
    "guard-edit-mode": ("dir", "Guard Edit Mode for MACHIN3tools"),
    "hdri-maker": ("dir", "hdri_maker"),
    "open-console-startup": ("file", "Open_console_on_startup.py"),
    "screenshot-nodes": ("dir", "ScreenshotNodes"),
    "symmetrize-plus": ("dir", "Symmetrize_Plus"),
    "target-please": ("dir", "Tracking Camera Rig"),
    "world-space-brush": ("dir", "world-space brush"),
}

EXCLUDE_DIRS = {"__pycache__", "reference"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def zip_dir(zf, src: Path):
    for path in sorted(src.rglob("*")):
        if path.is_dir():
            continue
        if EXCLUDE_DIRS & set(p.name for p in path.relative_to(ROOT).parents):
            continue
        if path.suffix in EXCLUDE_SUFFIXES:
            continue
        zf.write(path, arcname=path.relative_to(src.parent))


def package(slug, kind, rel_path, out_dir: Path):
    src = ROOT / rel_path
    if not src.exists():
        raise SystemExit(f"missing source for '{slug}': {src}")

    out_path = out_dir / f"{slug}.zip"
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if kind == "file":
            zf.write(src, arcname=src.name)
        else:
            zip_dir(zf, src)
    print(f"wrote {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="dist")
    args = parser.parse_args()

    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    for slug, (kind, rel_path) in ADDONS.items():
        package(slug, kind, rel_path, out_dir)


if __name__ == "__main__":
    main()
