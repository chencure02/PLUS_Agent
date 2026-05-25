"""File scanning utilities — auto-detect uploaded files for tool parameters."""
import os
import glob as glob_mod
import zipfile
import shutil
from datetime import datetime
from pathlib import Path
from agent.config import PROJECT_ROOT

UPLOADS_DIR = PROJECT_ROOT / "uploads"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
LULC_DIR = UPLOADS_DIR / "lulc"
DRIVERS_DIR = UPLOADS_DIR / "drivers"
CONSTRAINTS_DIR = UPLOADS_DIR / "constraints"


def ensure_dirs():
    """Create all required directories if they don't exist."""
    for d in [LULC_DIR, DRIVERS_DIR, CONSTRAINTS_DIR, OUTPUTS_DIR]:
        os.makedirs(d, exist_ok=True)


def make_output_dir() -> str:
    """Create a timestamped output subdirectory. Returns absolute path."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    d = OUTPUTS_DIR / ts
    os.makedirs(d, exist_ok=True)
    return str(d)


def scan_uploads() -> dict:
    """Scan uploads/ and return absolute paths. LLM must use these exact paths."""
    ensure_dirs()
    lulc = sorted([str(f.resolve()) for f in LULC_DIR.glob("*.tif")])
    drivers = sorted([str(f.resolve()) for f in DRIVERS_DIR.glob("*.tif")])
    constraints = sorted([str(f.resolve()) for f in CONSTRAINTS_DIR.glob("*.tif")])
    return {
        "lulc_files": lulc,
        "driver_files": drivers,
        "constraint_files": constraints,
        "lulc_count": len(lulc),
        "driver_count": len(drivers),
        "lulc_dir": str(LULC_DIR.resolve()),
        "drivers_dir": str(DRIVERS_DIR.resolve()),
        "constraints_dir": str(CONSTRAINTS_DIR.resolve()),
    }


def build_context_note(scan: dict) -> str | None:
    """Build a compact context note listing available files (absolute paths)."""
    parts = []
    if scan["lulc_files"]:
        paths = ", ".join(scan["lulc_files"])
        parts.append(f"LULC 数据 ({scan['lulc_count']} 张): {paths}")
    if scan["driver_files"]:
        parts.append(f"驱动因子文件夹: {scan['drivers_dir']}（{scan['driver_count']} 张）")
    if scan["constraint_files"]:
        parts.append(f"约束图: {', '.join(scan['constraint_files'])}")
    if parts:
        return " | ".join(parts)
    return None


def save_uploaded_file(file_element, subdir: Path) -> str | None:
    """Copy a Chainlit file element to the given subdirectory. Returns destination path."""
    ensure_dirs()
    src = file_element.path
    if not src or not os.path.exists(src):
        return None
    dst = subdir / file_element.name
    shutil.copy2(src, str(dst))
    return str(dst)


def extract_zip_to(zip_path: str, target_dir: Path) -> list[str]:
    """Extract a zip file to target_dir. Returns list of extracted paths."""
    ensure_dirs()
    extracted = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            # Skip directories and __MACOSX junk
            if member.endswith("/") or "__MACOSX" in member:
                continue
            basename = os.path.basename(member)
            if not basename:
                continue
            dst = target_dir / basename
            with zf.open(member) as src, open(dst, "wb") as out:
                out.write(src.read())
            extracted.append(str(dst))
    return extracted
