"""测试论文分析 Agent（单次分析 / 长文 map-reduce / 结果规整）"""
import json
import threading
import time

import pytest

from agent.analysis_agent import (
    AnalysisAgent,
    build_paged_content,
    split_into_batches,
)
from core.document import Chunk, Document


class FakeLLMClient:
    """按顺序返回预设回复，并记录每次请求的提示词"""

    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []

    def chat(self, system_prompt, user_prompt, temperature=None, max_tokens=None):
        self.calls.append(
            {"system_prompt": system_prompt, "user_prompt": user_prompt}
        )
        return self._replies.pop(0) if self._replies else "{}"


def _doc(chunks=None, title="RAG for Education", authors=("Alice", "Bob"),
         year="2024", journal="Journal of AI"):
    return Document(
        id="d1",
        title=title,
        authors=list(authors),
        year=year,
        journal=journal,
        chunks=(
            chunks
            if chunks is not None
            else [Chunk(id="c1", text="正文内容", page=1)]
        ),
    )


FULL_REPLY = json.dumps(
    {
        "research_method": {
            "text": "采用对照实验",
            "evidence_pages": ["2", 2, 3],
        },
        "key_findings": [
            {"text": "RAG 提升准确率", "evidence_pages": [5]},
            {"text": "   ", "evidence_pages": []},
        ],
        "limitations": ["样本量小", "样本量小", "未做多语言验证"],
    },
    ensure_ascii=False,
)


class TestSinglePass:
    def test_full_analysis_shape(self):
        agent = AnalysisAgent(llm_client=FakeLLMClient([FULL_REPLY]))

        analysis = agent.analyze_document(_doc(), "full")

        # 文献信息来自文档本身，不需要 LLM
        assert analysis["title"] == "RAG for Education"
        assert analysis["authors"] == ["Alice", "Bob"]
        assert analysis["year"] == "2024"
        assert analysis["journal"] == "Journal of AI"

        # 页码去重 + 转 int；空白条目被丢弃；局限性去重
        assert analysis["research_method"]["text"] == "采用对照实验"
        assert analysis["research_method"]["evidence_pages"] == [2, 3]
        assert [f["text"] for f in analysis["key_findings"]] == ["RAG 提升准确率"]
        assert analysis["limitations"] == ["样本量小", "未做多语言验证"]

    def test_response_always_has_all_contract_keys(self):
        agent = AnalysisAgent(llm_client=FakeLLMClient([FULL_REPLY]))
        analysis = agent.analyze_document(_doc(), "full")

        assert set(analysis) == {
            "title",
            "authors",
            "year",
            "journal",
            "research_method",
            "key_findings",
            "limitations",
        }

    def test_page_markers_sent_to_llm(self):
        llm = FakeLLMClient([FULL_REPLY])
        agent = AnalysisAgent(llm_client=llm)
        doc = _doc(
            chunks=[
                Chunk(id="c1", text="第一页", page=1),
                Chunk(id="c2", text="第二页", page=2),
            ]
        )

        agent.analyze_document(doc, "full")

        prompt = llm.calls[0]["user_prompt"]
        assert "===== PAGE 1 =====" in prompt
        assert "===== PAGE 2 =====" in prompt
        assert "第一页" in prompt and "第二页" in prompt

    def test_method_only_leaves_other_fields_empty(self):
        reply = json.dumps(
            {"research_method": {"text": "问卷法", "evidence_pages": [1]}},
            ensure_ascii=False,
        )
        llm = FakeLLMClient([reply])
        agent = AnalysisAgent(llm_client=llm)

        analysis = agent.analyze_document(_doc(), "method")

        assert analysis["research_method"]["text"] == "问卷法"
        assert analysis["key_findings"] == []
        assert analysis["limitations"] == []
        assert "研究方法" in llm.calls[0]["user_prompt"]

    def test_invalid_json_keeps_bibliography(self):
        agent = AnalysisAgent(llm_client=FakeLLMClient(["这不是 JSON"]))

        analysis = agent.analyze_document(_doc(), "full")

        assert analysis["title"] == "RAG for Education"
        assert analysis["research_method"] == {"text": "", "evidence_pages": []}
        assert analysis["key_findings"] == []
        assert analysis["limitations"] == []

    def test_empty_document_skips_llm(self):
        llm = FakeLLMClient([])
        agent = AnalysisAgent(llm_client=llm)

        analysis = agent.analyze_document(_doc(chunks=[]), "full")

        assert llm.calls == []
        assert analysis["key_findings"] == []
        assert analysis["title"] == "RAG for Education"

    def test_invalid_analysis_type_raises(self):
        agent = AnalysisAgent(llm_client=FakeLLMClient([]))
        with pytest.raises(ValueError):
            agent.analyze_document(_doc(), "unknown")


class TestMapReduce:
    def _long_doc(self, n_pages=4, page_chars=60):
        return _doc(
            chunks=[
                Chunk(id=f"c{i}", text="x" * page_chars, page=i + 1)
                for i in range(n_pages)
            ]
        )

    def _partial(self, text, page):
        return json.dumps(
            {"key_findings": [{"text": text, "evidence_pages": [page]}]},
            ensure_ascii=False,
        )

    def test_long_document_splits_then_merges(self):
        merged = json.dumps(
            {
                "key_findings": [
                    {"text": "发现A", "evidence_pages": [1]},
                    {"text": "发现B", "evidence_pages": [3]},
                ]
            },
            ensure_ascii=False,
        )
        llm = FakeLLMClient([self._partial("发现A", 1),
                             self._partial("发现B", 3),
                             merged])
        agent = AnalysisAgent(
            llm_client=llm, max_single_pass_chars=300, max_batch_chars=300
        )

        analysis = agent.analyze_document(self._long_doc(), "results")

        # 2 个分片 + 1 次合并
        assert len(llm.calls) == 3
        assert "合并" in llm.calls[-1]["user_prompt"]
        assert [f["text"] for f in analysis["key_findings"]] == ["发现A", "发现B"]

    def test_fallback_merge_when_merge_reply_unparsable(self):
        llm = FakeLLMClient(
            [self._partial("发现A", 1), self._partial("发现B", 3), "无法解析"]
        )
        agent = AnalysisAgent(
            llm_client=llm, max_single_pass_chars=300, max_batch_chars=300
        )

        analysis = agent.analyze_document(self._long_doc(), "results")

        # 合并失败不会丢结果：走确定性合并
        assert [f["text"] for f in analysis["key_findings"]] == ["发现A", "发现B"]


class TestHelpers:
    def test_build_paged_content_groups_by_page(self):
        doc = _doc(
            chunks=[
                Chunk(id="c1", text="A1", page=1),
                Chunk(id="c2", text="A2", page=1),
                Chunk(id="c3", text="B1", page=2),
            ]
        )
        content = build_paged_content(doc)
        assert "===== PAGE 1 =====\nA1\nA2" in content
        assert "===== PAGE 2 =====\nB1" in content

    def test_split_into_batches_respects_limit(self):
        content = "\n\n".join(
            f"===== PAGE {i} =====\n" + "y" * 80 for i in range(1, 5)
        )
        batches = split_into_batches(content, limit=200)

        assert len(batches) >= 2
        assert all(len(b) <= 220 for b in batches)

    def test_split_into_batches_handles_unmarked_text(self):
        batches = split_into_batches("z" * 500, limit=200)
        assert len(batches) == 3
        assert all(len(b) <= 200 for b in batches)


class TestAnalyzeById:
    def test_analyze_by_doc_id(self):
        class FakeStore:
            def get_document(self, doc_id):
                return _doc() if doc_id == "d1" else None

        agent = AnalysisAgent(
            llm_client=FakeLLMClient([FULL_REPLY]), metadata_store=FakeStore()
        )

        analysis = agent.analyze("d1", "full")
        assert analysis["title"] == "RAG for Education"

    def test_missing_document_raises(self):
        class FakeStore:
            def get_document(self, doc_id):
                return None

        agent = AnalysisAgent(
            llm_client=FakeLLMClient([]), metadata_store=FakeStore()
        )
        with pytest.raises(ValueError):
            agent.analyze("nope", "full")


def _long_doc(n_pages=4, page_chars=60):
    """构造足以触发 map-reduce 的长文档"""
    return _doc(
        chunks=[
            Chunk(id=f"c{i}", text="x" * page_chars, page=i + 1)
            for i in range(n_pages)
        ]
    )


class _ConcurrencyProbe:
    """记录并发峰值的假 LLM"""

    def __init__(self, delay=0.05, fail_first=False, reply=None):
        self.delay = delay
        self.fail_first = fail_first
        self.calls = 0
        self._lock = threading.Lock()
        self.now = 0
        self.peak = 0
        self._reply = reply or json.dumps(
            {"key_findings": [{"text": "发现", "evidence_pages": [1]}]},
            ensure_ascii=False,
        )

    def chat(self, system_prompt, user_prompt, temperature=None, max_tokens=None):
        with self._lock:
            self.calls += 1
            call_no = self.calls
            self.now += 1
            self.peak = max(self.peak, self.now)
        try:
            time.sleep(self.delay)
            if self.fail_first and call_no == 1:
                raise RuntimeError("第一片失败")
            return self._reply
        finally:
            with self._lock:
                self.now -= 1


class TestConcurrentMap:
    def test_map_phase_runs_concurrently(self):
        llm = _ConcurrencyProbe()
        agent = AnalysisAgent(
            llm_client=llm,
            max_single_pass_chars=300,
            max_batch_chars=300,
            max_workers=4,
        )

        agent.analyze_document(_long_doc(), "results")

        assert llm.peak >= 2

    def test_max_workers_one_stays_sequential(self):
        llm = _ConcurrencyProbe(delay=0.01)
        agent = AnalysisAgent(
            llm_client=llm,
            max_single_pass_chars=300,
            max_batch_chars=300,
            max_workers=1,
        )

        agent.analyze_document(_long_doc(), "results")

        assert llm.peak == 1
        assert llm.calls >= 2

    def test_single_batch_failure_keeps_other_results(self):
        llm = _ConcurrencyProbe(delay=0, fail_first=True)
        agent = AnalysisAgent(
            llm_client=llm,
            max_single_pass_chars=300,
            max_batch_chars=300,
            max_workers=1,
        )

        analysis = agent.analyze_document(_long_doc(), "results")

        # 第一片失败被跳过，但整次分析不失败
        assert analysis["key_findings"]
