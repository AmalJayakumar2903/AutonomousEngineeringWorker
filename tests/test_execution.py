from backend.tools.execution import (
    git_status,
    run_command,
    run_tests,
)


def test_git_status():
    result = git_status(".")
    assert "success" in result


def test_python_command():
    result = run_command(
        ".",
        ["python", "--version"],
    )

    assert result["success"]


def test_unsafe_command_is_blocked():
    try:
        run_command(
            ".",
            ["powershell", "-Command", "Get-Process"],
        )
        assert False, "Unsafe command should be blocked."
    except ValueError:
        pass


def test_pytest_runner():
    result = run_tests(".", "tests/test_filesystem.py")

    assert result["success"]


def test_failed_command_is_observed():
    result = run_command(
        ".",
        ["python", "-c", "raise SystemExit(1)"],
    )

    assert not result["success"]
    assert result["return_code"] == 1