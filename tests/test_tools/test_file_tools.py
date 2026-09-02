import pytest
from pathlib import Path

from src.tools.file_tools import read_file, write_file, list_files, ToolResult


class TestReadFile:
    def test_read_file_returns_content(self, tmp_path: Path):
        file = tmp_path / "hello.txt"
        file.write_text("hello world\nsecond line")
        result = read_file(str(file))
        assert result == ToolResult(success=True, output="hello world\nsecond line", error=None)

    def test_read_file_missing_returns_error(self):
        result = read_file("/nonexistent/path/file.txt")
        assert result.success is False
        assert result.error is not None
        assert "not found" in result.error.lower()

    def test_read_file_empty_file(self, tmp_path: Path):
        file = tmp_path / "empty.txt"
        file.write_text("")
        result = read_file(str(file))
        assert result == ToolResult(success=True, output="", error=None)


class TestWriteFile:
    def test_write_file_creates_content(self, tmp_path: Path):
        file = tmp_path / "new.txt"
        result = write_file(str(file), "written content")
        assert result.success is True
        assert file.read_text() == "written content"

    def test_write_file_creates_parent_dirs(self, tmp_path: Path):
        file = tmp_path / "a" / "b" / "c" / "deep.txt"
        result = write_file(str(file), "deep content")
        assert result.success is True
        assert file.read_text() == "deep content"

    def test_write_file_overwrites_existing(self, tmp_path: Path):
        file = tmp_path / "existing.txt"
        file.write_text("old")
        result = write_file(str(file), "new")
        assert result.success is True
        assert file.read_text() == "new"


class TestListFiles:
    def test_list_files_returns_names(self, tmp_path: Path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.py").write_text("b")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "c.txt").write_text("c")

        result = list_files(str(tmp_path), recursive=True)
        assert result.success is True
        names = result.output.split("\n")
        assert "a.txt" in names
        assert "b.py" in names
        assert "sub/c.txt" in names or "sub\\c.txt" in names

    def test_list_files_non_recursive(self, tmp_path: Path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "b.txt").write_text("b")

        result = list_files(str(tmp_path), recursive=False)
        assert result.success is True
        names = result.output.split("\n")
        assert "a.txt" in names
        assert not any("b.txt" in n for n in names)
