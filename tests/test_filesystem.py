from backend.tools.filesystem import (
    list_files,
    read_file,
    write_file,
)


def test_list_files():
    files = list_files(".")
    assert isinstance(files, list)
    assert "README.md" in files or "pytest.ini" in files


def test_read_and_write_file(tmp_path):
    repository = str(tmp_path)

    write_file(repository, "example.py", "print('hello')")

    assert read_file(repository, "example.py") == "print('hello')"


def test_path_traversal_is_blocked(tmp_path):
    repository = str(tmp_path)

    try:
        read_file(repository, "../outside.txt")
        assert False, "Path traversal should be blocked."
    except ValueError:
        pass