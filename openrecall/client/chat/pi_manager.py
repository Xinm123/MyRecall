import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional


class PiInstallError(Exception):
    """Raised when Pi installation fails."""
    pass


PI_PACKAGE = "@mariozechner/pi-coding-agent@0.60.0"
PI_INSTALL_DIR = Path.home() / ".myrecall" / "pi-agent"


def find_bun_executable() -> Optional[str]:
    """Locate bun executable on the system.

    Check in order:
    1. Bundled bun (next to executable — for future bundling)
    2. ~/.bun/bin/bun
    3. /opt/homebrew/bin/bun
    4. /usr/local/bin/bun
    5. shutil.which("bun")
    """
    home = str(Path.home())
    paths_to_check = [
        f"{home}/.bun/bin/bun",
        "/opt/homebrew/bin/bun",
        "/usr/local/bin/bun",
    ]
    for path in paths_to_check:
        if Path(path).exists():
            return path
    if which := shutil.which("bun"):
        return which
    return None


def find_pi_executable() -> Optional[str]:
    """Locate Pi CLI entrypoint (cli.js) after installation."""
    cli = (
        PI_INSTALL_DIR
        / "node_modules"
        / "@mariozechner"
        / "pi-coding-agent"
        / "dist"
        / "cli.js"
    )
    if cli.exists():
        return str(cli)
    return None


def is_version_current() -> bool:
    """Check if installed Pi matches expected version (0.60.0)."""
    pkg_file = PI_INSTALL_DIR / "package.json"
    if not pkg_file.exists():
        return False
    try:
        pkg = json.loads(pkg_file.read_text())
        for dep, ver in pkg.get("dependencies", {}).items():
            if dep == "@mariozechner/pi-coding-agent":
                # Strip npm version prefixes (^ ~ @) for comparison
                return ver.lstrip("^~@") == "0.60.0"
    except (json.JSONDecodeError, OSError):
        pass
    return False


def ensure_skill_installed():
    """Copy myrecall-search skill with dynamic URL substitution.

    Replaces hardcoded localhost:8083 with the configured edge_base_url,
    enabling distributed deployment where client and server run on different machines.
    """
    source = (
        Path(__file__).parent / "skills" / "myrecall-search" / "SKILL.md"
    )
    dest = (
        Path.home()
        / ".pi"
        / "agent"
        / "skills"
        / "myrecall-search"
        / "SKILL.md"
    )
    if not source.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Dynamic URL substitution for distributed deployment
    from openrecall.shared.config import settings
    content = source.read_text()
    edge_url = settings.edge_base_url or "http://localhost:8083"
    content = content.replace("http://localhost:8083", edge_url)

    dest.write_text(content)


def ensure_installed():
    """Install Pi if not present or version mismatch."""
    if not find_bun_executable():
        raise PiInstallError(
            "bun not found. Please install bun from https://bun.sh"
        )

    if not is_version_current():
        PI_INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        pkg_json = PI_INSTALL_DIR / "package.json"
        pkg_json.write_text(
            json.dumps(
                {
                    "name": "myrecall-pi-agent",
                    "dependencies": {
                        "@mariozechner/pi-coding-agent": "0.60.0",
                        "@anthropic-ai/sdk": "^0.26.0",
                    },
                    "overrides": {
                        "hosted-git-info": {"lru-cache": "^10.0.0"}
                    },
                },
                indent=2,
            )
        )
        result = subprocess.run(
            ["bun", "install"],
            cwd=PI_INSTALL_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            raise PiInstallError(f"bun install failed: {result.stderr}")

    ensure_skill_installed()
