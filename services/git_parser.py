"""
services/git_parser.py
======================
Handles all three input modes:
  Mode A - Fetch commit history from a repository URL
  Mode B - Parse an uploaded .txt git log file
  Mode C - Parse raw pasted commit text

For GitHub repositories, URL mode uses the GitHub REST API. For other allowed
hosts, the parser can fall back to a shallow clone when GitPython is available.
Returns: List[dict] with keys: hash, message, author, email, date, tags
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

import config

try:
    import git as gitpython

    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False


FULL_LOG_PATTERN = re.compile(
    r"^([a-f0-9]{7,40})\|(.+?)\|(.+?)\|(.+?)\|(.+?)\|(.*)$"
)
ONELINE_PATTERN = re.compile(r"^([a-f0-9]{6,40})\s+(.+)$")

NOISY_MESSAGE_PATTERN = re.compile(
    r"^(fix|wip|asdf|merge|update|chore|cleanup|lint|refactor|minor|small|test|checkpoint|typo|formatting|initial|docs?|hotfix)\b.*",
    re.IGNORECASE,
)


def parse_from_url(url: str) -> list[dict]:
    """Fetch structured commits from a supported repository URL."""
    parsed = _validate_url(url)
    host = parsed.netloc.lower().replace("www.", "")

    if host == "github.com":
        return _parse_from_github_url(parsed)

    if config.ENABLE_GIT_CLONE_FALLBACK and GIT_AVAILABLE:
        return _parse_from_clone(url)

    raise RuntimeError(
        "Only GitHub URL analysis is available without Git clone support. "
        "Use a GitHub repository URL, upload a git log file, or paste raw commits."
    )


def parse_from_file(file_content: str) -> list[dict]:
    """Parse content of an uploaded git log .txt file."""
    lines = file_content.strip().splitlines()
    return _parse_lines(lines)[: config.MAX_COMMITS_PER_ANALYSIS]


def parse_from_text(raw_text: str) -> list[dict]:
    """Parse raw pasted commit text."""
    lines = raw_text.strip().splitlines()
    return _parse_lines(lines)[: config.MAX_COMMITS_PER_ANALYSIS]


def _validate_url(url: str):
    parsed = urlparse(url)
    host = parsed.netloc.lower().replace("www.", "")
    if not parsed.scheme or not host:
        raise ValueError("Please enter a valid repository URL.")
    if host not in config.ALLOWED_REPO_HOSTS:
        raise ValueError(
            f"Host '{host}' is not allowed. Allowed: {', '.join(config.ALLOWED_REPO_HOSTS)}"
        )
    return parsed


def _parse_from_github_url(parsed_url) -> list[dict]:
    owner, repo = _extract_github_repo(parsed_url.path)
    commits = _fetch_github_commits(owner, repo)
    return commits[: config.MAX_COMMITS_PER_ANALYSIS]


def _extract_github_repo(path: str) -> tuple[str, str]:
    parts = [part for part in path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise ValueError("GitHub URLs must include an owner and repository name.")
    owner = parts[0]
    repo = parts[1].replace(".git", "")
    return owner, repo


def _fetch_github_commits(owner: str, repo: str) -> list[dict]:
    commits: list[dict] = []
    tag_map = _fetch_github_tags(owner, repo)
    per_page = min(100, config.MAX_COMMITS_PER_ANALYSIS)
    max_pages = max(1, (config.MAX_COMMITS_PER_ANALYSIS + per_page - 1) // per_page)

    for page in range(1, max_pages + 1):
        api_path = f"/repos/{quote(owner)}/{quote(repo)}/commits?per_page={per_page}&page={page}"
        payload = _github_api_get(api_path)
        if not isinstance(payload, list) or not payload:
            break

        for item in payload:
            sha = item.get("sha", "")
            commit_info = item.get("commit") or {}
            author_info = commit_info.get("author") or {}
            login = (item.get("author") or {}).get("login", "")
            author_name = author_info.get("name") or login or "Unknown"
            author_email = author_info.get("email") or ""
            message = (commit_info.get("message") or "").strip().splitlines()[0]
            date_raw = author_info.get("date") or ""

            commits.append(
                {
                    "hash": sha[:8],
                    "full_hash": sha,
                    "message": message or "No commit message",
                    "author": author_name,
                    "email": author_email,
                    "date": _parse_date(date_raw),
                    "date_raw": date_raw,
                    "tags": tag_map.get(sha, []),
                    "is_noisy": bool(NOISY_MESSAGE_PATTERN.match(message or "")),
                }
            )

            if len(commits) >= config.MAX_COMMITS_PER_ANALYSIS:
                return commits

        if len(payload) < per_page:
            break

    return commits


def _fetch_github_tags(owner: str, repo: str) -> dict[str, list[str]]:
    tag_map: dict[str, list[str]] = {}
    api_path = f"/repos/{quote(owner)}/{quote(repo)}/tags?per_page=100"

    try:
        payload = _github_api_get(api_path)
    except RuntimeError:
        return tag_map

    if not isinstance(payload, list):
        return tag_map

    for item in payload:
        commit_info = item.get("commit") or {}
        sha = commit_info.get("sha")
        name = item.get("name")
        if not sha or not name:
            continue
        tag_map.setdefault(sha, []).append(name)

    return tag_map


def _github_api_get(api_path: str):
    api_url = f"{config.GITHUB_API_BASE_URL.rstrip('/')}{api_path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": config.GITHUB_API_USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if config.GITHUB_API_TOKEN:
        headers["Authorization"] = f"Bearer {config.GITHUB_API_TOKEN}"

    request = Request(api_url, headers=headers)
    try:
        with urlopen(request, timeout=config.GITHUB_API_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        details = _read_http_error(exc)
        if exc.code == 403:
            raise RuntimeError(
                "GitHub API rate limit reached. Add GITHUB_API_TOKEN in config or environment "
                "to raise the limit."
            ) from exc
        if exc.code == 404:
            raise ValueError("Repository not found or not accessible through the GitHub API.") from exc
        raise RuntimeError(f"GitHub API request failed ({exc.code}): {details}") from exc
    except URLError as exc:
        raise RuntimeError(f"Unable to reach GitHub API: {exc.reason}") from exc


def _read_http_error(exc: HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except Exception:
        return exc.reason or "Unknown error"
    return payload.get("message") or exc.reason or "Unknown error"


def _parse_from_clone(url: str) -> list[dict]:
    """Clone repo shallowly and extract structured commit log."""
    clone_dir = tempfile.mkdtemp(dir=config.TEMP_CLONE_DIR)

    try:
        repo = gitpython.Repo.clone_from(
            url,
            clone_dir,
            depth=config.CLONE_DEPTH,
            no_single_branch=True,
        )
        commits = _extract_from_repo(repo)
        return commits[: config.MAX_COMMITS_PER_ANALYSIS]
    finally:
        shutil.rmtree(clone_dir, ignore_errors=True)


def _extract_from_repo(repo) -> list[dict]:
    """Run git log with custom format and parse into dicts."""
    fmt = "%H|%s|%an|%ae|%ad|%D"
    commits = []
    try:
        log_output = repo.git.log(
            "--all",
            f"--pretty=format:{fmt}",
            "--date=iso",
        )
    except Exception:
        log_output = repo.git.log(f"--pretty=format:{fmt}", "--date=iso")

    for line in log_output.splitlines():
        commit = _parse_full_line(line)
        if commit:
            commits.append(commit)
    return commits


def _parse_lines(lines: list[str]) -> list[dict]:
    """Try multiline format first, then fall back to single line formats."""
    content = "\n".join(lines)
    
    # 1. Try to parse standard git log blocks (multiline)
    multiline_commits = _parse_multiline_log(content)
    if multiline_commits:
        return multiline_commits

    # 2. Try to parse line by line (full pipe format or oneline)
    commits = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        commit = _parse_full_line(line) or _parse_oneline(line)
        if commit:
            commits.append(commit)
    return commits


def _parse_multiline_log(content: str) -> list[dict]:
    """Parse the default multiline 'git log' output."""
    # Pattern for 'commit HASH\nAuthor: NAME <EMAIL>\nDate: DATE\n\nMESSAGE'
    # Use finditer to find all blocks starting with 'commit '
    pattern = re.compile(r'^commit\s+([a-f0-9]{7,40}).*?\nAuthor:\s*(.*?)\nDate:\s*(.*?)\n\n(.*?)(?=\ncommit\s+|$)', re.MULTILINE | re.DOTALL)
    
    commits = []
    for match in pattern.finditer(content):
        sha, author_line, date_raw, message_block = match.groups()
        
        author = author_line.strip()
        email = ""
        auth_match = re.match(r"(.+?)\s*<(.+?)>", author)
        if auth_match:
            author, email = auth_match.groups()
            
        # Clean up message (strip indentation)
        message_lines = [line.strip() for line in message_block.splitlines() if line.strip()]
        message = " ".join(message_lines).strip()
        
        commits.append({
            "hash": sha[:8],
            "full_hash": sha,
            "message": message or "No commit message",
            "author": author,
            "email": email,
            "date": _parse_date(date_raw),
            "date_raw": date_raw.strip(),
            "tags": [],
            "is_noisy": bool(NOISY_MESSAGE_PATTERN.match(message or "")),
        })
            
    return commits


def _parse_full_line(line: str) -> dict | None:
    match = FULL_LOG_PATTERN.match(line)
    if not match:
        return None
    hash_, message, author, email, date_str, refs = match.groups()
    tags = _extract_tags(refs)
    return {
        "hash": hash_[:8],
        "full_hash": hash_,
        "message": message.strip(),
        "author": author.strip(),
        "email": email.strip(),
        "date": _parse_date(date_str),
        "date_raw": date_str.strip(),
        "tags": tags,
        "is_noisy": bool(NOISY_MESSAGE_PATTERN.match(message.strip())),
    }


def _parse_oneline(line: str) -> dict | None:
    match = ONELINE_PATTERN.match(line)
    if not match:
        return None
    hash_, message = match.groups()
    return {
        "hash": hash_[:8],
        "full_hash": hash_,
        "message": message.strip(),
        "author": "Unknown",
        "email": "",
        "date": None,
        "date_raw": "",
        "tags": [],
        "is_noisy": bool(NOISY_MESSAGE_PATTERN.match(message.strip())),
    }


def _extract_tags(refs: str) -> list[str]:
    """Extract version tags (v1.0, v2.3.1) from git refs string."""
    if not refs:
        return []
    tag_pattern = re.compile(r"tag:\s*(v?[\d]+[\d.]+[\w.-]*)", re.IGNORECASE)
    return tag_pattern.findall(refs)


def _parse_date(date_str: str) -> datetime | None:
    date_str = date_str.strip()
    if not date_str:
        return None

    iso_candidate = date_str.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso_candidate)
    except ValueError:
        pass

    formats = [
        "%Y-%m-%d %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str[:25], fmt)
        except ValueError:
            continue
    return None


def extract_repo_name(url_or_text: str) -> str:
    """Derive a clean repo name from a URL or fallback label."""
    if not url_or_text:
        return "Unnamed Repository"
    try:
        path = urlparse(url_or_text).path.rstrip("/")
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 2:
            return f"{parts[-2]}/{parts[-1].replace('.git', '')}"
        if parts:
            return parts[-1].replace(".git", "")
    except Exception:
        pass
    return "Uploaded Repository"
