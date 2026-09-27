"""测试 CLI：ingest 子命令的参数处理

回归点：path 曾为必填位置参数，导致 `ingest --reset` / `ingest --retry` 无法单独使用。
"""
import argparse

import pytest

from cli import main as cli_main


class FakePipeline:
    def __init__(self):
        self.resets = 0
        self.retries = 0
        self.ingested = []
        self.directories = []

    def reset(self):
        self.resets += 1

    def retry_failed(self):
        self.retries += 1
        return ["doc"]

    def ingest(self, file_path, force=False):
        self.ingested.append((file_path, force))

    def ingest_directory(self, dir_path, force=False):
        self.directories.append((dir_path, force))


@pytest.fixture
def pipeline(monkeypatch):
    import rag.ingest as ingest_module

    fake = FakePipeline()
    monkeypatch.setattr(ingest_module, "IngestPipeline", lambda: fake)
    return fake


def _args(path=None, reset=False, force=False, retry=False):
    return argparse.Namespace(path=path, reset=reset, force=force, retry=retry)


class TestCmdIngest:
    def test_retry_without_path(self, pipeline):
        cli_main.cmd_ingest(_args(retry=True))
        assert pipeline.retries == 1
        assert pipeline.ingested == []

    def test_reset_without_path(self, pipeline):
        cli_main.cmd_ingest(_args(reset=True))
        assert pipeline.resets == 1
        assert pipeline.ingested == []

    def test_no_path_without_flags_is_noop(self, pipeline):
        cli_main.cmd_ingest(_args())
        assert pipeline.ingested == []
        assert pipeline.directories == []
        assert pipeline.resets == 0

    def test_file_path_ingested_with_force(self, pipeline, tmp_path):
        pdf = tmp_path / "a.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        cli_main.cmd_ingest(_args(path=str(pdf), force=True))

        assert pipeline.ingested == [(str(pdf), True)]

    def test_directory_path_ingested(self, pipeline, tmp_path):
        cli_main.cmd_ingest(_args(path=str(tmp_path)))
        assert pipeline.directories == [(str(tmp_path), False)]

    def test_missing_path_reports_without_crash(self, pipeline):
        cli_main.cmd_ingest(_args(path="does/not/exist.pdf"))
        assert pipeline.ingested == []
