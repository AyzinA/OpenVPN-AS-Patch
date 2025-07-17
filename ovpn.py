#!/usr/bin/env python3

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import zipfile
from datetime import datetime, timezone
import logging
from typing import Callable
from colorama import init, Fore

# Initialize colorama for colored logs
init(autoreset=True)

# ────────── Configuration ──────────
EGG_DIR = Path("/usr/local/openvpn_as/lib/python")
EGG_PATTERN = "pyovpn-*.egg"
BACKUP_DIR = Path("/tmp")
LOG_FORMAT = "%(asctime)s [%(levelname)-5s] %(message)s"
TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
DEBUG_MODE = False  # Enable to save intermediate files and verbose logging

# ────────── Logging Setup ──────────
logging.basicConfig(
    level=logging.DEBUG if DEBUG_MODE else logging.INFO,
    format=LOG_FORMAT,
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ────────── Helpers / Actions ──────────
def setup_temp_dir(prefix: str = "pyovpn_patch_") -> Path:
    """Create a temporary directory and return its Path object."""
    temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
    logger.debug(f"Created temporary directory: {temp_dir}")
    return temp_dir

def find_source_egg() -> Path | None:
    """Find the pyovpn egg file in the specified directory."""
    egg_files = list(EGG_DIR.glob(EGG_PATTERN))
    if not egg_files:
        logger.error(f"No egg file matching {EGG_PATTERN} found in {EGG_DIR}")
        return None
    if len(egg_files) > 1:
        logger.warning(f"Multiple egg files found: {egg_files}. Using the first one: {egg_files[0]}")
    return egg_files[0]

def patch() -> None:
    """Patch the OpenVPN-AS egg to modify concurrent connections limit."""
    logger.info(f"{Fore.CYAN}Starting patch workflow{Fore.RESET}")

    SOURCE_EGG = find_source_egg()
    if not SOURCE_EGG:
        logger.error("Aborting due to missing egg file.")
        return

    if not SOURCE_EGG.is_file():
        logger.error(f"Source egg not found: {SOURCE_EGG}")
        logger.error("Ensure script is run as root and path is correct.")
        return

    # Create temporary workspace
    temp_dir = setup_temp_dir() if DEBUG_MODE else Path(tempfile.mkdtemp(prefix="pyovpn_patch_"))
    try:
        dest_egg = temp_dir / SOURCE_EGG.name

        # Copy egg
        shutil.copy2(SOURCE_EGG, dest_egg)
        logger.debug(f"Copied egg to {dest_egg}")

        # Extract egg
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir()
        with zipfile.ZipFile(dest_egg, "r") as zf:
            zf.extractall(extract_dir)
        logger.debug(f"Extracted egg to {extract_dir}")

        # Rename existing .pyc
        lic_dir = extract_dir / "pyovpn" / "lic"
        old_pyc = lic_dir / "uprop.pyc"
        new_pyc = lic_dir / "uprop2.pyc"
        if not old_pyc.exists():
            logger.error(f"Expected {old_pyc} not found, aborting.")
            return
        old_pyc.rename(new_pyc)
        logger.debug(f"Renamed {old_pyc.name} to {new_pyc.name}")

        # Create new uprop.py
        new_py = lic_dir / "uprop.py"
        new_py.write_text(
            textwrap.dedent(
                """
                from pyovpn.lic import uprop2

                old_figure = None

                def new_figure(self, licdict):
                    ret = old_figure(self, licdict)
                    ret['concurrent_connections'] = 200
                    return ret
                for x in dir(uprop2):
                    if x[:2] == '__':
                        continue
                    if x == 'UsageProperties':
                        exec('old_figure = uprop2.UsageProperties.figure')
                        exec('uprop2.UsageProperties.figure = new_figure')
                    exec('%s = uprop2.%s' % (x, x))
                """
            ).lstrip(),
            encoding="utf-8",
        )
        logger.debug(f"Wrote new {new_py}")

        # Compile to .pyc
        result = subprocess.run(
            ["python3", "-m", "compileall", "-b", str(new_py)],
            capture_output=True,
            text=True,
            cwd=str(lic_dir),
        )
        if result.returncode != 0:
            logger.error("Compilation failed:")
            logger.error(f"stdout: {result.stdout or '(no stdout)'}")
            logger.error(f"stderr: {result.stderr or '(no stderr)'}")
            return
        logger.debug("Compiled uprop.py to uprop.pyc")

        # Verify uprop.pyc exists
        pyc_file = new_py.with_suffix(".pyc")
        if not pyc_file.exists():
            logger.error(f"Compiled file {pyc_file} not found, aborting.")
            return
        if not DEBUG_MODE:
            new_py.unlink(missing_ok=True)
        logger.debug(f"{'Left' if DEBUG_MODE else 'Removed'} {new_py}")

        # Re-zip the patched tree
        with zipfile.ZipFile(dest_egg, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in extract_dir.rglob("*"):
                zf.write(f, f.relative_to(extract_dir))
        logger.debug(f"Repacked egg to {dest_egg}")

        # Backup original egg
        timestamp = datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT)
        backup_path = BACKUP_DIR / f"{SOURCE_EGG.name}.bak-{timestamp}"
        try:
            shutil.copy2(SOURCE_EGG, backup_path)
            logger.debug(f"Backed up original egg to {backup_path}")
        except FileNotFoundError:
            logger.warning("No existing live egg found to back up (first install?)")

        # Deploy patched egg
        shutil.copy2(dest_egg, SOURCE_EGG)
        logger.debug(f"{Fore.GREEN}Deployed patched egg to {SOURCE_EGG}{Fore.RESET}")

    except PermissionError as e:
        logger.error(f"Permission error: {e}")
        logger.error("Run script as root or check file permissions.")
    except zipfile.BadZipFile as e:
        logger.error(f"Invalid zip file: {e}")
    except subprocess.SubprocessError as e:
        logger.error(f"Subprocess error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        if not DEBUG_MODE and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.debug(f"Cleaned up temporary directory: {temp_dir}")

# ────────── Menu Plumbing ──────────
ACTIONS: dict[str, Callable[[], None]] = {
    "1": patch,
}

MENU_BANNER = textwrap.dedent(
    """
    ╔═════════════════════════════════════╗
    ║     OpenVPN-AS Patch Utility        ║
    ║                        by AyzinA    ║
    ╠═════════════════════════════════════╩══════╗
    ║ 1. Patch to 200 VPN connections allowed    ║
    ║ q. Quit                                    ║
    ╚════════════════════════════════════════════╝
    """
).strip()

def main() -> None:
    """Main menu loop for the patch utility."""
    while True:
        print(f"{Fore.CYAN}{MENU_BANNER}{Fore.RESET}")
        choice = input(f"{Fore.YELLOW}Select an option (1 or q): {Fore.RESET}").strip().lower()
        if choice in {"q", "quit", "exit"}:
            logger.info("Exiting patch utility.")
            break
        if choice not in ACTIONS:
            logger.error(f"Invalid option: {choice!r}")
            continue
        action = ACTIONS[choice]
        action()
        logger.info("Action completed, exiting.")
        sys.exit(0)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Interrupted – exiting.")
        sys.exit(0)
