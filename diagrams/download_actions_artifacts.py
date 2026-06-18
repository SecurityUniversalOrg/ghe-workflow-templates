#!/usr/bin/env python3
"""
Download GitHub Actions workflow run artifacts for a specific workflow name and timeframe,
unzip them, and parse every extracted file into an index/summary.

Supports GitHub.com and GitHub Enterprise Server.

Examples:
  export GITHUB_TOKEN="ghp_xxx"

  python download_actions_artifacts.py \
    --owner my-org \
    --repo my-repo \
    --workflow-name "Copilot Security Analysis" \
    --start "2026-06-01T00:00:00Z" \
    --end "2026-06-17T23:59:59Z" \
    --output-dir ./artifact-downloads

  python download_actions_artifacts.py \
    --api-url "https://ghe.example.com/api/v3" \
    --owner my-org \
    --repo my-repo \
    --workflow-name "CI" \
    --start "2026-06-01" \
    --end "2026-06-17" \
    --artifact-name "security-results" \
    --search-regex "CRITICAL|HIGH|error|failed" \
    --expand-nested-zips
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

GITHUB_API_VERSION = "2022-11-28"
DEFAULT_API_URL = "https://api.github.com"
TEXT_EXTENSIONS = {
    ".txt", ".log", ".md", ".markdown", ".csv", ".json", ".jsonl", ".sarif",
    ".yml", ".yaml", ".xml", ".html", ".htm", ".properties", ".ini",
    ".cfg", ".conf", ".out", ".err", ".tsv", ".sql", ".py", ".sh",
    ".ps1", ".js", ".ts", ".java", ".cs", ".go", ".rb", ".php",
}
MAX_TEXT_PREVIEW_CHARS = 4000
MAX_TEXT_FILE_BYTES_DEFAULT = 20 * 1024 * 1024  # 20 MiB


@dataclass
class GitHubConfig:
    api_url: str
    owner: str
    repo: str
    token: str
    sleep_seconds: float = 0.0
    retries: int = 3


class GitHubApiError(RuntimeError):
    pass


class GitHubClient:
    def __init__(self, cfg: GitHubConfig) -> None:
        self.cfg = cfg
        self.api_url = cfg.api_url.rstrip("/")
        self.base_repo_path = f"/repos/{urllib.parse.quote(cfg.owner)}/{urllib.parse.quote(cfg.repo)}"

    def _headers(self, accept: str = "application/vnd.github+json") -> Dict[str, str]:
        return {
            "Accept": accept,
            "Authorization": f"Bearer {self.cfg.token}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": "actions-artifact-downloader/1.0",
        }

    def _request_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = self._url(path, params)
        data = self._request_bytes(url, headers=self._headers())
        return json.loads(data.decode("utf-8"))

    def _request_bytes(self, url: str, headers: Dict[str, str]) -> bytes:
        last_error: Optional[BaseException] = None
        for attempt in range(1, self.cfg.retries + 1):
            req = urllib.request.Request(url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    return resp.read()
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                # Retry normal transient server-side failures and secondary rate-limit-ish 403s.
                if e.code in {403, 429, 500, 502, 503, 504} and attempt < self.cfg.retries:
                    wait = self._retry_wait(e, attempt)
                    print(f"WARN: HTTP {e.code}; retrying in {wait:.1f}s: {url}", file=sys.stderr)
                    time.sleep(wait)
                    continue
                raise GitHubApiError(f"GitHub API request failed: HTTP {e.code} {e.reason}\nURL: {url}\nBody: {body}") from e
            except (urllib.error.URLError, TimeoutError) as e:
                last_error = e
                if attempt < self.cfg.retries:
                    wait = min(2 ** attempt, 30)
                    print(f"WARN: request error; retrying in {wait:.1f}s: {e}", file=sys.stderr)
                    time.sleep(wait)
                    continue
                raise GitHubApiError(f"GitHub API request failed after {self.cfg.retries} attempts: {url}: {e}") from e
            finally:
                if self.cfg.sleep_seconds > 0:
                    time.sleep(self.cfg.sleep_seconds)
        raise GitHubApiError(f"GitHub API request failed: {url}: {last_error}")

    def _retry_wait(self, error: urllib.error.HTTPError, attempt: int) -> float:
        retry_after = error.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            return float(retry_after)
        reset = error.headers.get("X-RateLimit-Reset")
        if reset and reset.isdigit():
            delta = int(reset) - int(time.time()) + 1
            if delta > 0:
                return float(min(delta, 120))
        return float(min(2 ** attempt, 30))

    def _url(self, path: str, params: Optional[Dict[str, Any]] = None) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            base = path
        else:
            base = f"{self.api_url}{path}"
        if not params:
            return base
        clean_params = {k: v for k, v in params.items() if v is not None and v != ""}
        return f"{base}?{urllib.parse.urlencode(clean_params)}"

    def paged(self, path: str, item_key: str, params: Optional[Dict[str, Any]] = None, limit: Optional[int] = None) -> Iterable[Dict[str, Any]]:
        page = 1
        emitted = 0
        while True:
            merged = dict(params or {})
            merged.update({"per_page": 100, "page": page})
            payload = self._request_json(path, merged)
            items = payload.get(item_key, [])
            if not items:
                break
            for item in items:
                yield item
                emitted += 1
                if limit is not None and emitted >= limit:
                    return
            if len(items) < 100:
                break
            page += 1

    def find_workflow_by_name(self, workflow_name: str) -> Dict[str, Any]:
        workflows = list(self.paged(f"{self.base_repo_path}/actions/workflows", "workflows"))
        exact = [w for w in workflows if w.get("name") == workflow_name]
        ci_exact = [w for w in workflows if str(w.get("name", "")).lower() == workflow_name.lower()]

        matches = exact or ci_exact
        if not matches:
            available = ", ".join(sorted(w.get("name", "<unnamed>") for w in workflows))
            raise GitHubApiError(f"Workflow named '{workflow_name}' was not found. Available workflows: {available}")
        if len(matches) > 1:
            names = ", ".join(f"{w.get('name')} ({w.get('path')}, id={w.get('id')})" for w in matches)
            raise GitHubApiError(f"Multiple workflows matched '{workflow_name}'. Use --workflow-id instead. Matches: {names}")
        return matches[0]

    def list_workflow_runs(
        self,
        workflow_id_or_file: str,
        created_range: str,
        status: Optional[str] = None,
        branch: Optional[str] = None,
        event: Optional[str] = None,
        max_runs: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        path = f"{self.base_repo_path}/actions/workflows/{urllib.parse.quote(str(workflow_id_or_file), safe='')}/runs"
        params = {
            "created": created_range,
            "status": status,
            "branch": branch,
            "event": event,
            "exclude_pull_requests": "false",
        }
        return list(self.paged(path, "workflow_runs", params=params, limit=max_runs))

    def list_run_artifacts(self, run_id: int, artifact_name: Optional[str] = None) -> List[Dict[str, Any]]:
        path = f"{self.base_repo_path}/actions/runs/{run_id}/artifacts"
        params = {"name": artifact_name} if artifact_name else None
        return list(self.paged(path, "artifacts", params=params))

    def download_artifact_zip(self, artifact_id: int, dest_zip: Path) -> None:
        url = f"{self.api_url}{self.base_repo_path}/actions/artifacts/{artifact_id}/zip"
        headers = self._headers(accept="application/zip")
        dest_zip.parent.mkdir(parents=True, exist_ok=True)

        last_error: Optional[BaseException] = None
        for attempt in range(1, self.cfg.retries + 1):
            req = urllib.request.Request(url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=180) as resp, dest_zip.open("wb") as f:
                    shutil.copyfileobj(resp, f, length=1024 * 1024)
                return
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                if e.code == 410:
                    raise GitHubApiError(f"Artifact {artifact_id} is gone/expired and cannot be downloaded.") from e
                if e.code in {403, 429, 500, 502, 503, 504} and attempt < self.cfg.retries:
                    wait = self._retry_wait(e, attempt)
                    print(f"WARN: artifact download HTTP {e.code}; retrying in {wait:.1f}s", file=sys.stderr)
                    time.sleep(wait)
                    continue
                raise GitHubApiError(f"Artifact download failed: HTTP {e.code} {e.reason}\nURL: {url}\nBody: {body}") from e
            except (urllib.error.URLError, TimeoutError) as e:
                last_error = e
                if attempt < self.cfg.retries:
                    wait = min(2 ** attempt, 30)
                    print(f"WARN: artifact download error; retrying in {wait:.1f}s: {e}", file=sys.stderr)
                    time.sleep(wait)
                    continue
                raise GitHubApiError(f"Artifact download failed after {self.cfg.retries} attempts: {url}: {e}") from e
        raise GitHubApiError(f"Artifact download failed: {url}: {last_error}")


def normalize_date_for_github(value: str, is_end: bool = False) -> str:
    """Accept YYYY-MM-DD or full ISO timestamp. Return a GitHub search-compatible UTC string."""
    value = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return f"{value}T{'23:59:59' if is_end else '00:00:00'}Z"
    if value.endswith("Z"):
        return value
    # Accept +00:00 style timestamps and normalize UTC-ish. GitHub search syntax accepts ISO 8601.
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            # Treat naive timestamps as UTC to avoid local-time surprises in CI.
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        parsed = parsed.astimezone(dt.timezone.utc)
        return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"Invalid date/time: {value}. Use YYYY-MM-DD or ISO 8601, e.g. 2026-06-01T00:00:00Z") from e


def safe_extract_zip(zip_path: Path, extract_dir: Path) -> None:
    extract_dir.mkdir(parents=True, exist_ok=True)
    root = extract_dir.resolve()
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            target = (extract_dir / member.filename).resolve()
            if not str(target).startswith(str(root) + os.sep) and target != root:
                raise RuntimeError(f"Unsafe zip path detected in {zip_path}: {member.filename}")
        zf.extractall(extract_dir)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_probably_binary(path: Path, sample_size: int = 4096) -> bool:
    try:
        with path.open("rb") as f:
            sample = f.read(sample_size)
        if b"\x00" in sample:
            return True
        if path.suffix.lower() in TEXT_EXTENSIONS:
            return False
        # Heuristic: if a high percentage is non-text control bytes, treat as binary.
        if not sample:
            return False
        text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)))
        non_text = sample.translate(None, text_chars)
        return len(non_text) / len(sample) > 0.30
    except OSError:
        return True


def read_text_limited(path: Path, max_bytes: int) -> Tuple[str, bool]:
    size = path.stat().st_size
    truncated = size > max_bytes
    with path.open("rb") as f:
        data = f.read(max_bytes)
    return data.decode("utf-8", errors="replace"), truncated


def summarize_json(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict):
        keys = list(obj.keys())[:25]
        summary: Dict[str, Any] = {"json_type": "object", "top_level_keys": keys}
        # SARIF convenience summary.
        if obj.get("version") and "runs" in obj:
            rules = 0
            results = 0
            for run in obj.get("runs", []) if isinstance(obj.get("runs"), list) else []:
                tool = run.get("tool", {}) if isinstance(run, dict) else {}
                driver = tool.get("driver", {}) if isinstance(tool, dict) else {}
                rules += len(driver.get("rules", []) or []) if isinstance(driver, dict) else 0
                results += len(run.get("results", []) or []) if isinstance(run, dict) else 0
            summary.update({"sarif_rules": rules, "sarif_results": results})
        return summary
    if isinstance(obj, list):
        return {"json_type": "array", "array_length": len(obj)}
    return {"json_type": type(obj).__name__}


def summarize_csv(path: Path, delimiter: str = ",") -> Dict[str, Any]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        sample = f.read(8192)
        f.seek(0)
        dialect = csv.Sniffer().sniff(sample) if sample else csv.get_dialect("excel")
        reader = csv.reader(f, dialect)
        rows = 0
        header: List[str] = []
        for row in reader:
            if rows == 0:
                header = row[:50]
            rows += 1
        return {"csv_rows": rows, "csv_header": header}


def parse_file(path: Path, root_dir: Path, max_text_bytes: int, search_regex: Optional[re.Pattern[str]]) -> Dict[str, Any]:
    rel = str(path.relative_to(root_dir))
    stat = path.stat()
    record: Dict[str, Any] = {
        "relative_path": rel,
        "absolute_path": str(path),
        "extension": path.suffix.lower(),
        "size_bytes": stat.st_size,
        "sha256": sha256_file(path),
        "is_binary": False,
        "truncated": False,
        "parse_status": "ok",
    }

    try:
        if is_probably_binary(path):
            record["is_binary"] = True
            record["parse_status"] = "binary_skipped"
            return record

        text, truncated = read_text_limited(path, max_text_bytes)
        record["truncated"] = truncated
        record["line_count"] = text.count("\n") + (1 if text else 0)
        record["preview"] = text[:MAX_TEXT_PREVIEW_CHARS]

        if search_regex:
            matches = []
            for line_no, line in enumerate(text.splitlines(), start=1):
                if search_regex.search(line):
                    matches.append({"line": line_no, "text": line[:1000]})
                    if len(matches) >= 100:
                        break
            record["match_count"] = len(matches)
            record["matches"] = matches

        suffix = path.suffix.lower()
        if suffix in {".json", ".sarif"}:
            obj = json.loads(text)
            record.update(summarize_json(obj))
        elif suffix == ".jsonl":
            jsonl_count = 0
            invalid_lines = 0
            for line in text.splitlines():
                if not line.strip():
                    continue
                try:
                    json.loads(line)
                    jsonl_count += 1
                except json.JSONDecodeError:
                    invalid_lines += 1
            record.update({"jsonl_records": jsonl_count, "jsonl_invalid_lines": invalid_lines})
        elif suffix in {".csv", ".tsv"}:
            record.update(summarize_csv(path, delimiter="\t" if suffix == ".tsv" else ","))
        else:
            record["text_preview_only"] = True
    except Exception as e:  # Keep walking even if one file fails.
        record["parse_status"] = "error"
        record["error"] = f"{type(e).__name__}: {e}"
    return record


def expand_nested_zips(root_dir: Path) -> List[Path]:
    extracted_dirs: List[Path] = []
    for zip_path in list(root_dir.rglob("*.zip")):
        # Avoid expanding original downloaded artifact zips if the caller puts them under root_dir.
        if not zip_path.is_file():
            continue
        dest = zip_path.with_suffix(zip_path.suffix + ".extracted")
        if dest.exists():
            continue
        try:
            safe_extract_zip(zip_path, dest)
            extracted_dirs.append(dest)
        except zipfile.BadZipFile:
            continue
    return extracted_dirs


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv_summary(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "run_id", "run_number", "run_attempt", "workflow_name", "head_branch", "head_sha", "run_created_at",
        "artifact_id", "artifact_name", "artifact_expired", "relative_path", "extension", "size_bytes",
        "sha256", "is_binary", "parse_status", "line_count", "match_count", "json_type", "csv_rows",
        "sarif_rules", "sarif_results", "absolute_path", "error",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download, unzip, and parse GitHub Actions workflow run artifacts by workflow name/timeframe.")
    parser.add_argument("--api-url", default=os.environ.get("GITHUB_API_URL", DEFAULT_API_URL), help="GitHub API URL. GitHub.com default: https://api.github.com. GHES example: https://ghe.example.com/api/v3")
    parser.add_argument("--owner", required=True, help="Repository owner/org")
    parser.add_argument("--repo", required=True, help="Repository name")
    parser.add_argument("--workflow-name", help="Workflow display name, e.g. 'CI' or 'Copilot Security Analysis'")
    parser.add_argument("--workflow-id", help="Workflow ID or workflow file name, e.g. 123456 or ci.yml. Overrides --workflow-name lookup.")
    parser.add_argument("--start", required=True, help="Start date/time, e.g. 2026-06-01 or 2026-06-01T00:00:00Z")
    parser.add_argument("--end", required=True, help="End date/time, e.g. 2026-06-17 or 2026-06-17T23:59:59Z")
    parser.add_argument("--artifact-name", help="Optional exact artifact name filter")
    parser.add_argument("--output-dir", default="./artifact-downloads", help="Output directory")
    parser.add_argument("--status", default="completed", help="Workflow run status/conclusion filter. Default: completed. Use empty string to disable.")
    parser.add_argument("--branch", help="Optional branch filter")
    parser.add_argument("--event", help="Optional event filter, e.g. push, pull_request, workflow_dispatch")
    parser.add_argument("--max-runs", type=int, help="Optional safety limit for workflow runs")
    parser.add_argument("--max-text-bytes", type=int, default=MAX_TEXT_FILE_BYTES_DEFAULT, help="Max bytes to read from each text file")
    parser.add_argument("--search-regex", help="Optional regex to evaluate against text files; matching lines are captured in parsed_files.jsonl")
    parser.add_argument("--expand-nested-zips", action="store_true", help="Also expand any .zip files found inside artifacts")
    parser.add_argument("--skip-download", action="store_true", help="Skip downloading if the zip already exists")
    parser.add_argument("--keep-zips", action="store_true", help="Keep downloaded artifact zip files. Default keeps them under zips/ anyway; this option is retained for clarity.")
    parser.add_argument("--sleep-seconds", type=float, default=0.0, help="Sleep between API calls to reduce rate-limit pressure")
    parser.add_argument("--retries", type=int, default=3, help="HTTP retries")
    args = parser.parse_args()

    if not args.workflow_name and not args.workflow_id:
        parser.error("Provide either --workflow-name or --workflow-id")
    if not os.environ.get("GITHUB_TOKEN"):
        parser.error("Set GITHUB_TOKEN in the environment")
    return args


def main() -> int:
    args = parse_args()
    token = os.environ["GITHUB_TOKEN"]
    output_dir = Path(args.output_dir).resolve()
    zip_dir = output_dir / "zips"
    extract_root = output_dir / "extracted"
    report_dir = output_dir / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)

    start = normalize_date_for_github(args.start, is_end=False)
    end = normalize_date_for_github(args.end, is_end=True)
    created_range = f"{start}..{end}"

    cfg = GitHubConfig(
        api_url=args.api_url,
        owner=args.owner,
        repo=args.repo,
        token=token,
        sleep_seconds=args.sleep_seconds,
        retries=args.retries,
    )
    gh = GitHubClient(cfg)

    workflow_ref = args.workflow_id
    workflow_name = args.workflow_name or args.workflow_id
    workflow_meta: Dict[str, Any] = {}
    if not workflow_ref:
        workflow_meta = gh.find_workflow_by_name(args.workflow_name)
        workflow_ref = str(workflow_meta["id"])
        workflow_name = workflow_meta.get("name", args.workflow_name)
        print(f"Resolved workflow '{args.workflow_name}' to id={workflow_ref}, path={workflow_meta.get('path')}")

    print(f"Listing runs for {args.owner}/{args.repo}, workflow={workflow_ref}, created={created_range}")
    runs = gh.list_workflow_runs(
        workflow_ref,
        created_range=created_range,
        status=args.status or None,
        branch=args.branch,
        event=args.event,
        max_runs=args.max_runs,
    )
    print(f"Found {len(runs)} workflow run(s).")

    all_records: List[Dict[str, Any]] = []
    run_manifest: List[Dict[str, Any]] = []
    search_re = re.compile(args.search_regex) if args.search_regex else None

    for run in runs:
        run_id = int(run["id"])
        run_number = run.get("run_number")
        run_attempt = run.get("run_attempt")
        run_created_at = run.get("created_at")
        run_dir_name = f"run-{run_id}-number-{run_number}-attempt-{run_attempt}"
        print(f"\nRun {run_id} / #{run_number} attempt {run_attempt} created {run_created_at}")

        artifacts = gh.list_run_artifacts(run_id, artifact_name=args.artifact_name)
        print(f"  Found {len(artifacts)} artifact(s).")

        run_manifest.append({
            "run_id": run_id,
            "run_number": run_number,
            "run_attempt": run_attempt,
            "workflow_name": workflow_name,
            "workflow_ref": workflow_ref,
            "created_at": run_created_at,
            "updated_at": run.get("updated_at"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "head_branch": run.get("head_branch"),
            "head_sha": run.get("head_sha"),
            "html_url": run.get("html_url"),
            "artifact_count": len(artifacts),
        })

        for artifact in artifacts:
            artifact_id = int(artifact["id"])
            artifact_name = artifact.get("name", f"artifact-{artifact_id}")
            expired = artifact.get("expired", False)
            safe_artifact_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", artifact_name).strip("._") or f"artifact-{artifact_id}"
            artifact_zip = zip_dir / run_dir_name / f"{artifact_id}-{safe_artifact_name}.zip"
            artifact_extract_dir = extract_root / run_dir_name / f"{artifact_id}-{safe_artifact_name}"

            if expired:
                print(f"  SKIP expired artifact: {artifact_name} ({artifact_id})")
                continue

            if args.skip_download and artifact_zip.exists():
                print(f"  Reusing existing zip: {artifact_zip}")
            else:
                print(f"  Downloading artifact: {artifact_name} ({artifact_id})")
                gh.download_artifact_zip(artifact_id, artifact_zip)

            if artifact_extract_dir.exists():
                shutil.rmtree(artifact_extract_dir)
            print(f"  Extracting to: {artifact_extract_dir}")
            safe_extract_zip(artifact_zip, artifact_extract_dir)

            if args.expand_nested_zips:
                nested = expand_nested_zips(artifact_extract_dir)
                if nested:
                    print(f"  Expanded {len(nested)} nested zip(s).")

            for file_path in sorted(p for p in artifact_extract_dir.rglob("*") if p.is_file()):
                record = parse_file(file_path, artifact_extract_dir, args.max_text_bytes, search_re)
                record.update({
                    "run_id": run_id,
                    "run_number": run_number,
                    "run_attempt": run_attempt,
                    "workflow_name": workflow_name,
                    "head_branch": run.get("head_branch"),
                    "head_sha": run.get("head_sha"),
                    "run_created_at": run_created_at,
                    "artifact_id": artifact_id,
                    "artifact_name": artifact_name,
                    "artifact_expired": expired,
                    "artifact_created_at": artifact.get("created_at"),
                    "artifact_expires_at": artifact.get("expires_at"),
                    "artifact_size_bytes": artifact.get("size_in_bytes"),
                    "artifact_digest": artifact.get("digest"),
                })
                all_records.append(record)

    manifest_path = report_dir / "workflow_runs.jsonl"
    parsed_jsonl_path = report_dir / "parsed_files.jsonl"
    parsed_csv_path = report_dir / "parsed_files_summary.csv"

    write_jsonl(manifest_path, run_manifest)
    write_jsonl(parsed_jsonl_path, all_records)
    write_csv_summary(parsed_csv_path, all_records)

    print("\nDone.")
    print(f"Workflow run manifest: {manifest_path}")
    print(f"Parsed file JSONL:     {parsed_jsonl_path}")
    print(f"Parsed file CSV:       {parsed_csv_path}")
    print(f"Extracted artifacts:   {extract_root}")
    print(f"Downloaded zips:       {zip_dir}")
    print(f"Parsed files:          {len(all_records)}")
    if search_re:
        total_matches = sum(int(r.get("match_count") or 0) for r in all_records)
        print(f"Regex matches:         {total_matches}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
    except GitHubApiError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)
