# 1. Add this class after GitHubApiError
class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """
    Prevent urllib from automatically following GitHub redirect URLs.

    GitHub artifact and job log download endpoints return short-lived signed
    storage URLs in the Location header. Following the redirect manually prevents
    the GitHub Authorization header from being sent to the storage backend.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None

# 2. Add these methods inside class GitHubClient
    def _download_redirected_file(self, api_download_url: str, dest_path: Path, description: str) -> None:
        """
        Download a GitHub API resource that returns a 302 Location URL.

        GitHub returns short-lived signed storage URLs for artifact and log
        downloads. This method captures the redirect URL first and then downloads
        from the signed URL without the GitHub Authorization header.
        """

        api_headers = self._headers(accept="application/vnd.github+json")
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        no_redirect_opener = urllib.request.build_opener(NoRedirectHandler)

        last_error: Optional[BaseException] = None

        for attempt in range(1, self.cfg.retries + 1):
            try:
                api_req = urllib.request.Request(
                    api_download_url,
                    headers=api_headers,
                    method="GET",
                )

                signed_url: Optional[str] = None

                try:
                    # Some GHES versions may stream directly instead of returning a redirect.
                    with no_redirect_opener.open(api_req, timeout=120) as resp, dest_path.open("wb") as f:
                        shutil.copyfileobj(resp, f, length=1024 * 1024)
                    return

                except urllib.error.HTTPError as e:
                    if e.code not in {302, 303, 307, 308}:
                        body = e.read().decode("utf-8", errors="replace")

                        if e.code == 410:
                            raise GitHubApiError(
                                f"{description} is gone/expired and cannot be downloaded."
                            ) from e

                        if e.code in {403, 429, 500, 502, 503, 504} and attempt < self.cfg.retries:
                            wait = self._retry_wait(e, attempt)
                            print(
                                f"WARN: {description} download HTTP {e.code}; retrying in {wait:.1f}s",
                                file=sys.stderr,
                            )
                            time.sleep(wait)
                            continue

                        raise GitHubApiError(
                            f"{description} download URL request failed: HTTP {e.code} {e.reason}\n"
                            f"URL: {api_download_url}\n"
                            f"Body: {body}"
                        ) from e

                    signed_url = e.headers.get("Location")

                    if not signed_url:
                        raise GitHubApiError(
                            f"GitHub returned HTTP {e.code} for {description}, "
                            "but no Location header was present."
                        ) from e

                # Download from the signed URL WITHOUT GitHub Authorization.
                storage_req = urllib.request.Request(
                    signed_url,
                    headers={"User-Agent": "actions-artifact-downloader/1.0"},
                    method="GET",
                )

                with urllib.request.urlopen(storage_req, timeout=180) as storage_resp, dest_path.open("wb") as f:
                    shutil.copyfileobj(storage_resp, f, length=1024 * 1024)

                return

            except (urllib.error.URLError, TimeoutError) as e:
                last_error = e

                if attempt < self.cfg.retries:
                    wait = min(2 ** attempt, 30)
                    print(
                        f"WARN: {description} download error; retrying in {wait:.1f}s: {e}",
                        file=sys.stderr,
                    )
                    time.sleep(wait)
                    continue

                raise GitHubApiError(
                    f"{description} download failed after {self.cfg.retries} attempts: "
                    f"{api_download_url}: {e}"
                ) from e

        raise GitHubApiError(
            f"{description} download failed: {api_download_url}: {last_error}"
        )


    def download_artifact_zip(self, artifact_id: int, dest_zip: Path) -> None:
        """
        Download a workflow artifact ZIP.
        This replaces the older artifact download logic that used Accept: application/zip.
        """

        url = f"{self.api_url}{self.base_repo_path}/actions/artifacts/{artifact_id}/zip"
        self._download_redirected_file(
            api_download_url=url,
            dest_path=dest_zip,
            description=f"Artifact {artifact_id}",
        )


    def list_run_jobs(self, run_id: int, run_attempt: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        List jobs for a workflow run, including step metadata.

        If run_attempt is supplied, the attempt-specific jobs endpoint is used.
        That makes the step log extraction line up with the exact retry attempt.
        """

        if run_attempt:
            path = f"{self.base_repo_path}/actions/runs/{run_id}/attempts/{run_attempt}/jobs"
            params = None
        else:
            path = f"{self.base_repo_path}/actions/runs/{run_id}/jobs"
            params = {"filter": "latest"}

        return list(self.paged(path, "jobs", params=params))


    def download_job_log(self, job_id: int, dest_log: Path) -> None:
        """
        Download the plain-text log file for a workflow job.
        """

        url = f"{self.api_url}{self.base_repo_path}/actions/jobs/{job_id}/logs"
        self._download_redirected_file(
            api_download_url=url,
            dest_path=dest_log,
            description=f"Job log {job_id}",
        )

# 3. Add these helper functions outside the class
GITHUB_LOG_TS_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\s(?P<message>.*)$"
)


def parse_github_datetime(value: Optional[str]) -> Optional[dt.datetime]:
    """
    Parse GitHub timestamp strings into UTC-aware datetime objects.
    Handles timestamps with more than 6 fractional second digits.
    """

    if not value:
        return None

    normalized = value.strip()

    match = re.match(
        r"^(?P<prefix>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"
        r"(?:\.(?P<fraction>\d+))?"
        r"(?P<tz>Z|[+-]\d{2}:\d{2})$",
        normalized,
    )

    if match:
        fraction = match.group("fraction")

        if fraction:
            fraction = fraction[:6].ljust(6, "0")
            normalized = f"{match.group('prefix')}.{fraction}{match.group('tz')}"

    try:
        parsed = dt.datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)

    return parsed.astimezone(dt.timezone.utc)


def parse_log_line_timestamp(line: str) -> Tuple[Optional[dt.datetime], str]:
    """
    Extract the timestamp from a GitHub Actions log line.

    Returns:
        Tuple of timestamp or None, and the log message.
    """

    match = GITHUB_LOG_TS_RE.match(line)

    if not match:
        return None, line

    ts = parse_github_datetime(match.group("ts"))
    return ts, match.group("message")


def step_name_matches(actual: str, expected: str, exact: bool = False) -> bool:
    """
    Match a workflow step name.

    Default behavior is case-insensitive contains matching.
    Exact mode is case-sensitive.
    """

    if exact:
        return actual == expected

    return expected.lower() in actual.lower()


def safe_name(value: str, fallback: str = "item") -> str:
    """
    Convert a job, step, or artifact name into a filesystem-safe name.
    """

    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return cleaned or fallback


def extract_step_log_text(job_log_text: str, step: Dict[str, Any]) -> Tuple[str, str]:
    """
    Extract one step's log lines from a full job log.

    Preferred method:
        Use the step started_at/completed_at timestamps from the jobs API
        and the timestamps that prefix each job log line.

    Fallback method:
        Search for the step name in the job log text.
    """

    step_name = str(step.get("name", ""))
    started_at = parse_github_datetime(step.get("started_at"))
    completed_at = parse_github_datetime(step.get("completed_at"))

    lines = job_log_text.splitlines()

    if started_at and completed_at:
        selected: List[str] = []

        for line in lines:
            line_ts, _message = parse_log_line_timestamp(line)

            if line_ts and started_at <= line_ts <= completed_at:
                selected.append(line)

        if selected:
            return "\n".join(selected) + "\n", "timestamp_window"

    # Best-effort fallback.
    # GitHub logs do not always include the friendly step name in the text.
    for idx, line in enumerate(lines):
        if step_name and step_name.lower() in line.lower():
            selected = [line]

            for follow in lines[idx + 1:]:
                selected.append(follow)

                if "##[endgroup]" in follow or "##[group]" in follow:
                    break

            return "\n".join(selected) + "\n", "name_search_fallback"

    return "", "not_found_in_job_log"


def write_step_log_summary_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    """
    Write a CSV summary of downloaded/extracted step logs.
    """

    path.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "run_id",
        "run_number",
        "run_attempt",
        "workflow_name",
        "head_branch",
        "head_sha",
        "run_created_at",
        "job_id",
        "job_name",
        "job_conclusion",
        "step_number",
        "step_name",
        "step_conclusion",
        "step_started_at",
        "step_completed_at",
        "match_method",
        "log_path",
        "bytes_written",
        "line_count",
        "job_log_path",
    ]

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()

        for row in rows:
            writer.writerow(row)


def download_step_logs_for_run(
    gh: GitHubClient,
    run: Dict[str, Any],
    workflow_name: str,
    step_name: str,
    logs_root: Path,
    exact_step_name: bool = False,
    job_name: Optional[str] = None,
    skip_download: bool = False,
) -> List[Dict[str, Any]]:
    """
    Download and extract logs for a named step from each matching job in one workflow run.

    Args:
        gh: GitHubClient instance.
        run: Workflow run JSON object from the workflow runs API.
        workflow_name: Resolved workflow name.
        step_name: Step name to search for.
        logs_root: Root directory where logs should be written.
        exact_step_name: If true, require exact case-sensitive step name match.
        job_name: Optional job name filter.
        skip_download: If true, reuse existing job log files.

    Returns:
        List of metadata records for extracted step logs.
    """

    run_id = int(run["id"])
    run_number = run.get("run_number")
    run_attempt = run.get("run_attempt")
    run_created_at = run.get("created_at")

    run_dir_name = f"run-{run_id}-number-{run_number}-attempt-{run_attempt}"
    run_log_dir = logs_root / run_dir_name

    jobs = gh.list_run_jobs(
        run_id=run_id,
        run_attempt=int(run_attempt) if run_attempt else None,
    )

    records: List[Dict[str, Any]] = []

    for job in jobs:
        current_job_name = str(job.get("name", ""))

        if job_name and not step_name_matches(current_job_name, job_name, exact=False):
            continue

        matching_steps = [
            step
            for step in job.get("steps", []) or []
            if step_name_matches(
                actual=str(step.get("name", "")),
                expected=step_name,
                exact=exact_step_name,
            )
        ]

        if not matching_steps:
            continue

        job_id = int(job["id"])
        job_safe = safe_name(current_job_name, fallback=f"job-{job_id}")

        job_log_path = run_log_dir / f"job-{job_id}-{job_safe}.log"

        if skip_download and job_log_path.exists():
            print(f"  Reusing existing job log: {job_log_path}")
        else:
            print(f"  Downloading job log: {current_job_name} ({job_id})")
            gh.download_job_log(job_id, job_log_path)

        job_log_text = job_log_path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        for step in matching_steps:
            step_number = step.get("number")
            current_step_name = str(step.get("name", ""))
            step_safe = safe_name(
                current_step_name,
                fallback=f"step-{step_number}",
            )

            step_log_text, match_method = extract_step_log_text(
                job_log_text=job_log_text,
                step=step,
            )

            step_log_path = run_log_dir / f"job-{job_id}-step-{step_number}-{step_safe}.log"
            step_log_path.parent.mkdir(parents=True, exist_ok=True)
            step_log_path.write_text(step_log_text, encoding="utf-8")

            records.append(
                {
                    "run_id": run_id,
                    "run_number": run_number,
                    "run_attempt": run_attempt,
                    "workflow_name": workflow_name,
                    "head_branch": run.get("head_branch"),
                    "head_sha": run.get("head_sha"),
                    "run_created_at": run_created_at,
                    "job_id": job_id,
                    "job_name": current_job_name,
                    "job_conclusion": job.get("conclusion"),
                    "step_number": step_number,
                    "step_name": current_step_name,
                    "step_conclusion": step.get("conclusion"),
                    "step_started_at": step.get("started_at"),
                    "step_completed_at": step.get("completed_at"),
                    "match_method": match_method,
                    "log_path": str(step_log_path),
                    "bytes_written": len(step_log_text.encode("utf-8")),
                    "line_count": step_log_text.count("\n")
                    + (1 if step_log_text and not step_log_text.endswith("\n") else 0),
                    "job_log_path": str(job_log_path),
                }
            )

    return records

# 4. Add these arguments inside parse_args()
    parser.add_argument(
        "--step-name",
        help=(
            "Optional workflow step name. If set, downloads each matching job log "
            "and extracts this step's log lines per workflow run."
        ),
    )

    parser.add_argument(
        "--exact-step-name",
        action="store_true",
        help=(
            "Require exact, case-sensitive step-name matching. "
            "Default is case-insensitive contains matching."
        ),
    )

    parser.add_argument(
        "--job-name",
        help=(
            "Optional job name filter when downloading step logs. "
            "Useful when the same step name exists in multiple jobs."
        ),
    )

# 5. Add these variables inside main()
# Find this section:
    output_dir = Path(args.output_dir).resolve()
    zip_dir = output_dir / "zips"
    extract_root = output_dir / "extracted"
    report_dir = output_dir / "reports"
# Change it to this:
    output_dir = Path(args.output_dir).resolve()
    zip_dir = output_dir / "zips"
    extract_root = output_dir / "extracted"
    report_dir = output_dir / "reports"
    logs_root = output_dir / "step-logs"

# Then find this:
    all_records: List[Dict[str, Any]] = []
    run_manifest: List[Dict[str, Any]] = []
# Change it to this:
    all_records: List[Dict[str, Any]] = []
    step_log_records: List[Dict[str, Any]] = []
    run_manifest: List[Dict[str, Any]] = []

# 6. Add this inside the for run in runs: loop
# Put this after run_manifest.append({...}) and before the for artifact in artifacts: loop.
        if args.step_name:
            print(f"  Looking for step logs named: {args.step_name}")

            step_records = download_step_logs_for_run(
                gh=gh,
                run=run,
                workflow_name=workflow_name,
                step_name=args.step_name,
                logs_root=logs_root,
                exact_step_name=args.exact_step_name,
                job_name=args.job_name,
                skip_download=args.skip_download,
            )

            print(f"  Extracted {len(step_records)} matching step log file(s).")

            step_log_records.extend(step_records)

# 7. Add the step-log report files near the existing report output
# Find this:
    manifest_path = report_dir / "workflow_runs.jsonl"
    parsed_jsonl_path = report_dir / "parsed_files.jsonl"
    parsed_csv_path = report_dir / "parsed_files_summary.csv"

    write_jsonl(manifest_path, run_manifest)
    write_jsonl(parsed_jsonl_path, all_records)
    write_csv_summary(parsed_csv_path, all_records)
# Change it to this:
    manifest_path = report_dir / "workflow_runs.jsonl"
    parsed_jsonl_path = report_dir / "parsed_files.jsonl"
    parsed_csv_path = report_dir / "parsed_files_summary.csv"
    step_logs_jsonl_path = report_dir / "step_logs.jsonl"
    step_logs_csv_path = report_dir / "step_logs_summary.csv"

    write_jsonl(manifest_path, run_manifest)
    write_jsonl(parsed_jsonl_path, all_records)
    write_csv_summary(parsed_csv_path, all_records)

    if args.step_name:
        write_jsonl(step_logs_jsonl_path, step_log_records)
        write_step_log_summary_csv(step_logs_csv_path, step_log_records)
# Then add these print lines near your final output:
    if args.step_name:
        print(f"Step log JSONL:        {step_logs_jsonl_path}")
        print(f"Step log CSV:          {step_logs_csv_path}")
        print(f"Extracted step logs:   {logs_root}")
        print(f"Step log files:        {len(step_log_records)}")

# 8. Example command
python download_actions_artifacts.py \
  --owner my-org \
  --repo my-repo \
  --workflow-name "CI" \
  --start "2026-06-01" \
  --end "2026-06-17" \
  --step-name "Run security scan" \
  --output-dir ./artifact-downloads
# With a job filter:
python download_actions_artifacts.py \
  --owner my-org \
  --repo my-repo \
  --workflow-name "CI" \
  --start "2026-06-01" \
  --end "2026-06-17" \
  --step-name "Run security scan" \
  --job-name "security" \
  --output-dir ./artifact-downloads