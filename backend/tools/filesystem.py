from pathlib import Path


IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
}

ALLOWED_WRITE_EXTENSIONS = {
    ".py",
    ".sql",
    ".md",
    ".json",
    ".yaml",
    ".yml",
}


def _safe_path(repository: str, file_path: str) -> Path:
    """Resolve a path and prevent access outside the repository."""

    root = Path(repository).resolve()
    target = (root / file_path).resolve()

    if target != root and root not in target.parents:
        raise ValueError("Path escapes repository boundary.")

    return target


def list_files(repository: str) -> list[str]:
    """List files available to the worker."""

    root = Path(repository).resolve()
    files = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        if any(part in IGNORED_DIRECTORIES for part in path.parts):
            continue

        files.append(str(path.relative_to(root)))

    return sorted(files)


def read_file(repository: str, file_path: str) -> str:
    """Read a repository file."""

    target = _safe_path(repository, file_path)

    if not target.is_file():
        raise FileNotFoundError(file_path)

    return target.read_text(encoding="utf-8")


def write_file(
    repository: str,
    file_path: str,
    content: str,
) -> str:
    """Write only approved source/configuration file types."""

    target = _safe_path(repository, file_path)

    if target.suffix.lower() not in ALLOWED_WRITE_EXTENSIONS:
        raise ValueError(
            f"Writing '{target.suffix}' files is not permitted."
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    return f"Wrote {file_path}"