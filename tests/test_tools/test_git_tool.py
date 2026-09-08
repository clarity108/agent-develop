import subprocess
import sys
import pytest

from src.tools.git_tool import git_status, git_init, git_add_commit, git_log, git_branch, git_diff, git_blame


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

    def test_git_add_commit_nothing_to_commit(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, check=False, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=False, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=False, capture_output=True)

        result = git_add_commit(str(tmp_path), "empty")
        assert result.success is True
        assert "no changes" in result.output


class TestGitLog:
    def test_git_log_in_repo(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, check=False, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=False, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=False, capture_output=True)
        (tmp_path / "a.txt").write_text("a")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=False, capture_output=True)
        subprocess.run(["git", "commit", "-m", "first"], cwd=tmp_path, check=False, capture_output=True)
        (tmp_path / "b.txt").write_text("b")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=False, capture_output=True)
        subprocess.run(["git", "commit", "-m", "second"], cwd=tmp_path, check=False, capture_output=True)

        result = git_log(str(tmp_path))
        assert result.success is True
        assert "first" in result.output or "second" in result.output

    def test_git_log_count(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, check=False, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=False, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=False, capture_output=True)
        (tmp_path / "x.txt").write_text("x")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=False, capture_output=True)
        subprocess.run(["git", "commit", "-m", "only"], cwd=tmp_path, check=False, capture_output=True)

        result = git_log(str(tmp_path), count=1)
        assert result.success is True

    def test_git_log_not_a_repo(self, tmp_path):
        result = git_log(str(tmp_path))
        assert result.success is False
        assert "not a git repository" in result.error


class TestGitBranch:
    def test_git_branch_in_repo(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, check=False, capture_output=True)
        result = git_branch(str(tmp_path))
        assert result.success is True

    def test_git_branch_not_a_repo(self, tmp_path):
        result = git_branch(str(tmp_path))
        assert result.success is False


class TestGitDiff:
    def test_git_diff_working_tree(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, check=False, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=False, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=False, capture_output=True)
        (tmp_path / "a.txt").write_text("original")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=False, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=False, capture_output=True)
        (tmp_path / "a.txt").write_text("modified")

        result = git_diff(str(tmp_path))
        assert result.success is True
        assert "a.txt" in result.output

    def test_git_diff_not_a_repo(self, tmp_path):
        result = git_diff(str(tmp_path))
        assert result.success is False


class TestGitBlame:
    def test_git_blame_in_repo(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, check=False, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=False, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=False, capture_output=True)
        (tmp_path / "file.txt").write_text("line1\nline2\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=False, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=False, capture_output=True)

        result = git_blame(str(tmp_path), "file.txt")
        assert result.success is True
        assert "line1" in result.output or "line2" in result.output

    def test_git_blame_not_a_repo(self, tmp_path):
        result = git_blame(str(tmp_path), "file.txt")
        assert result.success is False
