import subprocess
import sys
import pytest

from src.tools.git_tool import git_status, git_init, git_add_commit


class TestGitStatus:
    def test_git_status_in_repo(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, check=False, capture_output=True)
        (tmp_path / "file.txt").write_text("content")

        result = git_status(str(tmp_path))
        assert result.success is True
        assert "file.txt" in result.output

    def test_git_status_not_a_repo(self, tmp_path):
        (tmp_path / "file.txt").write_text("content")
        result = git_status(str(tmp_path))
        assert result.success is False
        assert "not a git repository" in result.error.lower()


class TestGitInit:
    def test_git_init_creates_repo(self, tmp_path):
        result = git_init(str(tmp_path))
        assert result.success is True
        git_dir = tmp_path / ".git"
        assert git_dir.exists()

    def test_git_init_already_initialized(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, check=False, capture_output=True)
        result = git_init(str(tmp_path))
        assert result.success is True


class TestGitAddCommit:
    def test_git_add_commit(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, check=False, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=False, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=False, capture_output=True)
        (tmp_path / "new.py").write_text("print('hello')")

        result = git_add_commit(str(tmp_path), "initial commit")
        assert result.success is True
        assert "initial commit" in result.output or "commit" in result.output
