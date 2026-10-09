import subprocess
from pathlib import Path


ALLOWED_COMMANDS = {"python", "pytest", "git"}


def run_command(
    repository: str,
    command: list[str],
    timeout: int = 60,
) -> dict:
    """
    Execute an approved command inside the repository.

    shell=False prevents the model from turning its output
    into an unrestricted shell command.
    """

    if not command:
        raise ValueError("Command cannot be empty.")

    executable = Path(command[0]).stem.lower()

    if executable not in ALLOWED_COMMANDS:
        raise ValueError(
            f"Command '{command[0]}' is not permitted."
        )

    result = subprocess.run(
        command,
        cwd=Path(repository).resolve(),
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )

    return {
        "success": result.returncode == 0,
        "return_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def git_status(repository: str) -> dict:
    return run_command(
        repository,
        ["git", "status", "--short"],
    )


def git_diff(repository: str) -> dict:
    return run_command(
        repository,
        ["git", "diff"],
    )


def git_log(repository: str, limit: int = 10) -> dict:
    return run_command(
        repository,
        ["git", "log", "--oneline", f"-{limit}"],
    )


def run_tests(
    repository: str,
    test_path: str = "tests",
) -> dict:
    return run_command(
        repository,
        ["pytest", test_path, "-q"],
        timeout=120,
    )