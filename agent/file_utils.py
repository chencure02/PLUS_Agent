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


def scan_uploads(
    lulc_dir: Path | str = LULC_DIR,
    drivers_dir: Path | str = DRIVERS_DIR,
    constraints_dir: Path | str = CONSTRAINTS_DIR,
) -> dict:
    """Scan uploads/ and return absolute paths. LLM must use these exact paths."""
    lulc_dir = Path(lulc_dir)
    drivers_dir = Path(drivers_dir)
    constraints_dir = Path(constraints_dir)
    for d in [lulc_dir, drivers_dir, constraints_dir]:
        os.makedirs(d, exist_ok=True)
    lulc = _scan_rasters(lulc_dir)
    drivers = _scan_rasters(drivers_dir)
    constraints = _scan_rasters(constraints_dir)
    return {
        "lulc_files": lulc,
        "driver_files": drivers,
        "constraint_files": constraints,
        "lulc_count": len(lulc),
        "driver_count": len(drivers),
        "lulc_dir": str(lulc_dir.resolve()),
        "drivers_dir": str(drivers_dir.resolve()),
        "constraints_dir": str(constraints_dir.resolve()),
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
    subdir.mkdir(parents=True, exist_ok=True)
    src = file_element.path
    if not src or not os.path.exists(src):
        return None
    dst = _unique_destination(subdir, file_element.name)
    shutil.copy2(src, str(dst))
    return str(dst)


def extract_zip_to(zip_path: str, target_dir: Path) -> list[str]:
    """Extract a zip file to target_dir. Returns list of extracted paths."""
    target_dir.mkdir(parents=True, exist_ok=True)
    extracted = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            # Skip directories and __MACOSX junk
            if member.endswith("/") or "__MACOSX" in member:
                continue
            basename = os.path.basename(member)
            if not basename:
                continue
            dst = _unique_destination(target_dir, basename)
            with zf.open(member) as src, open(dst, "wb") as out:
                out.write(src.read())
            extracted.append(str(dst))
    return extracted


def _unique_destination(directory: Path, filename: str) -> Path:
    """Return a non-overwriting destination path inside directory."""
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    for i in range(1, 1000):
        candidate = directory / f"{stem}__{ts}_{i:03d}{suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Could not allocate a unique filename for {filename}")


def _scan_rasters(directory: Path) -> list[str]:
    files = list(directory.glob("*.tif")) + list(directory.glob("*.tiff"))
    return sorted(str(f.resolve()) for f in files)
