"""Package approved working-tree source/docs, including intended untracked phases.

Never includes Git history, environment secrets, dependencies, builds or local DBs.
"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = {"backend", "frontend", "phases", "scripts", "docs", ".github"}
ROOT_FILES = {"README.md", "AGENTS.md", "ARCHITECTURE.md", "MASTER_ORCHESTRATOR.md",
              "PLAN.md", "DEPLOYMENT.md", "DEMO_SCRIPT.md", "VIVA_QA.md",
              "PROJECT_REPORT_OUTLINE.md", "TEST_SUMMARY.md", "FINAL_STATUS.md",
              "SUBMISSION_CHECKLIST.md", ".env.example", ".gitignore", "docker-compose.yml"}
FORBIDDEN = {"node_modules", "venv", ".venv", "__pycache__", ".pytest_cache", ".git",
             "dist", "dist-ssr", "coverage", "htmlcov", ".idea", ".vscode"}
SUFFIXES = {".pyc", ".log", ".db", ".sqlite", ".sqlite3", ".dump", ".sql", ".bak", ".zip"}
SECRET_PATTERN = re.compile(r"(?:shpat_|shpca_|shppa_)[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT).decode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    output = parser.parse_args().output.resolve()
    if output.suffix != ".zip":
        raise ValueError("Output must be a .zip archive.")
    names = sorted(set(filter(None, git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0"))))
    files: list[tuple[str, bytes]] = []
    for name in names:
        path = Path(name)
        if path.parts[0] not in DIRECTORIES and name not in ROOT_FILES:
            continue
        if any(part in FORBIDDEN for part in path.parts) or path.suffix in SUFFIXES:
            continue
        if path.name != ".env.example" and (path.name.startswith(".env") or path.name.endswith(".env")):
            continue
        source = ROOT / path
        if not source.is_file() or source.is_symlink() or source.resolve() == output:
            continue
        data = source.read_bytes()
        try:
            if SECRET_PATTERN.search(data.decode("utf-8")):
                raise RuntimeError(f"Potential credential detected in {name}; values suppressed. Review before packaging.")
        except UnicodeDecodeError:
            pass
        files.append((name, data))
    required = ROOT_FILES - {".gitignore", "docker-compose.yml"}
    if missing := required - {name for name, _ in files}:
        raise RuntimeError("Missing submission files: " + ", ".join(sorted(missing)))
    manifest = {"branch": git("branch", "--show-current").strip(), "head": git("rev-parse", "HEAD").strip(),
                "working_tree_snapshot": True, "dirty_working_tree": bool(git("status", "--porcelain").strip()),
                "files": [{"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in files]}
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in files:
            archive.writestr(ZipInfo.from_file(ROOT / name, "cartpilot/" + name), data, compress_type=ZIP_DEFLATED)
        archive.writestr("cartpilot/SUBMISSION_MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Archive integrity check failed")
    print(json.dumps({"output": str(output), "source_files": len(files), "screenshots": sum(name.endswith('.png') and name.startswith('docs/screenshots/') for name, _ in files), "bytes": output.stat().st_size, "integrity": "passed"}, indent=2))


if __name__ == "__main__":
    main()
