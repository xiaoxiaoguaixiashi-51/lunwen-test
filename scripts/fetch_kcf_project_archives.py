"""Fetch pinned GitHub source archives when Git transport is unavailable."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from urllib.parse import quote, urlparse


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, output: Path) -> None:
    subprocess.run(
        ["curl", "--fail", "--location", "--silent", "--show-error",
         "--connect-timeout", "10", "--max-time", "300", "--retry", "0",
         "--output", str(output), url],
        check=True, capture_output=True, text=True, timeout=320,
    )


def extract_source(archive: Path, destination: Path) -> None:
    """Accept only ordinary files/directories beneath a single archive root."""
    with tarfile.open(archive, "r:gz") as handle:
        members = handle.getmembers()
        roots = set()
        for member in members:
            parts = member.name.split("/")
            if member.name.startswith("/") or ".." in parts or "\\" in member.name:
                raise ValueError(f"Unsafe archive path: {member.name}")
            if not (member.isfile() or member.isdir()):
                raise ValueError(f"Unsupported archive entry: {member.name}")
            roots.add(parts[0])
        if len(roots) != 1:
            raise ValueError("Expected a single source archive root")
        # Strip the archive's generated root directory without following links.
        for member in members:
            relative = "/".join(member.name.split("/")[1:]).rstrip("/")
            if not relative:
                continue
            target = destination / relative
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                source = handle.extractfile(member)
                if source is None:
                    raise ValueError(f"Unreadable archive entry: {member.name}")
                with source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
                target.chmod(member.mode & 0o777)


def fetch_project(project: dict, root: Path, evidence: Path, cache: Path | None = None) -> dict:
    project_id = project["project_id"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", project_id):
        raise ValueError("Invalid project ID")
    parsed = urlparse(project["repo_url"])
    if parsed.scheme != "https" or parsed.netloc != "github.com":
        raise ValueError("Expected a public GitHub HTTPS repository")
    repository = parsed.path.strip("/").removesuffix(".git")
    destination = root / project_id
    log_dir = evidence / project_id
    log_dir.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        marker = destination / ".kcf-source.json"
        archive = log_dir / "source.tar.gz"
        if marker.is_file() and archive.is_file():
            record = json.loads(marker.read_text(encoding="utf-8"))
            if (record.get("repository") == project["repo_url"]
                    and record.get("requested_ref") in project["refs"]
                    and record.get("archive_sha256") == fingerprint(archive)):
                return record
        raise FileExistsError(f"Refusing to overwrite existing sources: {destination}")
    attempts = []
    for ref in project["refs"]:
        response = log_dir / "commit.json"
        try:
            download(f"https://api.github.com/repos/{repository}/commits/{quote(ref, safe='')}", response)
            commit = json.loads(response.read_text(encoding="utf-8"))["sha"]
            if not re.fullmatch(r"[0-9a-f]{40}", commit):
                raise ValueError("GitHub did not return a full commit SHA")
            break
        except (subprocess.SubprocessError, ValueError, KeyError) as exc:
            attempts.append({"ref": ref, "error": str(exc)})
    else:
        return {"project_id": project_id, "status": "resolve_failed", "attempts": attempts}

    archive = log_dir / "source.tar.gz"
    url = f"https://codeload.github.com/{repository}/tar.gz/{commit}"
    cached = cache / f"{project_id}.tar.gz" if cache else None
    if cached and cached.is_file():
        with tarfile.open(cached, "r:gz") as handle:
            members = handle.getmembers()
            if not members or members[0].name.split("/")[0] != f"{repository.split('/')[-1]}-{commit}":
                raise ValueError("Cached archive root does not match resolved commit")
        shutil.copyfile(cached, archive)
    else:
        download(url, archive)
    with tempfile.TemporaryDirectory(prefix=f".{project_id}-", dir=root) as tmp:
        extracted = Path(tmp) / "source"
        extracted.mkdir()
        extract_source(archive, extracted)
        record = {
            "project_id": project_id, "status": "ok", "repository": project["repo_url"],
            "requested_ref": ref, "resolved_commit": commit, "archive_url": url,
            "archive_sha256": fingerprint(archive), "source_dir": str(destination),
            "checkout_kind": "official_github_archive", "attempts": attempts,
        }
        (extracted / ".kcf-source.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        extracted.rename(destination)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--projects-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--archive-cache", type=Path)
    args = parser.parse_args()
    args.projects_root.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    projects = json.loads(args.manifest.read_text(encoding="utf-8"))
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        pending = {pool.submit(fetch_project, p, args.projects_root, args.output_dir, args.archive_cache): p for p in projects}
        for future in concurrent.futures.as_completed(pending):
            try:
                row = future.result()
            except Exception as exc:
                row = {"project_id": pending[future]["project_id"], "status": "error", "error": str(exc)}
            rows.append(row)
            print(json.dumps(row), flush=True)
            report = {"manifest_sha256": fingerprint(args.manifest), "projects": sorted(rows, key=lambda r: r["project_id"])}
            (args.output_dir / "source_manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if all(row["status"] == "ok" for row in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
