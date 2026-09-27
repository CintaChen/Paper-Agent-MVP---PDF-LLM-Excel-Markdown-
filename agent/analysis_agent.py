"""论文分析 Agent

对单篇论文做结构化抽取，输出字段与 docs/API_DESIGN.md §4.5.4 一致：
    research_method / key_findings / limitations（另附 title / authors / year / journal）

长文处理：
    正文超过单次上限时走 map-reduce——先按页分片做局部分析，再合并为最终结果，
    避免整篇论文塞爆上下文。

设计说明：
    分析基于 SQLite 中的全文（doc.chunks），不依赖向量检索，
    因此本 Agent 不会触碰 Milvus / BM25。
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from config.logging import setup_logging
from core.document import Document
from core.llm import LLMClient
from agent.base_agent import BaseAgent
from agent.prompts import (
    ANALYSIS_SYSTEM_PROMPT,
    ANALYSIS_USER_PROMPT,
    ANALYSIS_MERGE_PROMPT,
)

logger = setup_logging(__name__)

# 单次送入 LLM 的正文上限（字符）
MAX_SINGLE_PASS_CHARS = 12000
# map 阶段每片正文上限（字符）
MAX_BATCH_CHARS = 10000
# map 阶段并发度（分片之间彼此独立，并发可显著缩短长文分析耗时）
MAX_MAP_WORKERS = 4

_ANALYSIS_SCOPES = {
    "full": "研究方法、关键发现、局限性",
    "method": "研究方法",
    "results": "关键发现",
    "limitations": "局限性",
}

_PAGE_SPLIT = re.compile(r"(?=\n?===== PAGE \d+ =====)")


def _as_page_list(value: Any) -> list[int]:
    """把 LLM 返回的页码统一成去重、升序的正整数列表"""
    if isinstance(value, (int, float)):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []

    pages = set()
    for item in value:
        try:
            page = int(str(item).strip())
        except (TypeError, ValueError):
            continue
        if page > 0:
            pages.add(page)
    return sorted(pages)


def schema_for(analysis_type: str) -> str:
    """按分析类型生成期望的 JSON 结构（嵌入式地告诉 LLM 该输出什么）"""
    schema: dict[str, Any] = {}
    if analysis_type in ("full", "method"):
        schema["research_method"] = {"text": "", "evidence_pages": []}
    if analysis_type in ("full", "results"):
        schema["key_findings"] = [{"text": "", "evidence_pages": []}]
    if analysis_type in ("full", "limitations"):
        schema["limitations"] = [""]
    return json.dumps(schema, ensure_ascii=False, indent=2)


def build_paged_content(doc: Document) -> str:
    """把文档 chunks 按页聚合成带页码标记的正文"""
    by_page: dict[int, list[str]] = {}
    for chunk in doc.chunks:
        by_page.setdefault(chunk.page or 0, []).append(chunk.text)

    parts = []
    for page in sorted(by_page):
        parts.append(f"===== PAGE {page} =====\n" + "\n".join(by_page[page]))
    return "\n\n".join(parts)


def split_into_batches(content: str, limit: int = MAX_BATCH_CHARS) -> list[str]:
    """按 PAGE 块切分正文，再贪心合并为不超过 limit 的批次"""
    units: list[str] = []
    for block in _PAGE_SPLIT.split(content):
        block = block.strip()
        if not block:
            continue
        if len(block) <= limit:
            units.append(block)
        else:
            # 单个块本身就超限（例如无页码标记）时按长度硬切
            units.extend(
                block[i : i + limit] for i in range(0, len(block), limit)
            )

    batches: list[str] = []
    current = ""
    for unit in units:
        if current and len(current) + len(unit) + 2 > limit:
            batches.append(current)
            current = unit
        else:
            current = f"{current}\n\n{unit}".strip() if current else unit
    if current:
        batches.append(current)
    return batches or [content]


class AnalysisAgent(BaseAgent):
    """论文分析 Agent：结构化抽取研究方法 / 关键发现 / 局限性"""

    def __init__(
        self,
        llm_client: LLMClient = None,
        metadata_store: Any = None,
        max_single_pass_chars: int = MAX_SINGLE_PASS_CHARS,
        max_batch_chars: int = MAX_BATCH_CHARS,
        max_workers: int = MAX_MAP_WORKERS,
    ):
        super().__init__(
            llm_client=llm_client, system_prompt=ANALYSIS_SYSTEM_PROMPT
        )
        self._metadata_store = metadata_store
        self.max_single_pass_chars = max_single_pass_chars
        self.max_batch_chars = max_batch_chars
        self.max_workers = max(1, max_workers)

    @property
    def metadata_store(self):
        """惰性打开 SQLite（仅 analyze(doc_id) 路径需要）"""
        if self._metadata_store is None:
            from storage.metadata_store import SQLiteStore

            self._metadata_store = SQLiteStore()
        return self._metadata_store

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------
    def analyze(
        self,
        doc_id: str,
        analysis_type: str = "full",
        temperature: float = None,
        max_tokens: int = None,
    ) -> dict:
        """按 doc_id 分析（文档不存在时抛 ValueError）"""
        doc = self.metadata_store.get_document(doc_id)
        if doc is None:
            raise ValueError(f"文档不存在: {doc_id}")
        return self.analyze_document(doc, analysis_type, temperature, max_tokens)

    def analyze_document(
        self,
        doc: Document,
        analysis_type: str = "full",
        temperature: float = None,
        max_tokens: int = None,
    ) -> dict:
        """分析已加载的文档"""
        if analysis_type not in _ANALYSIS_SCOPES:
            raise ValueError(
                f"无效的 analysis_type: {analysis_type}，"
                f"可选 {list(_ANALYSIS_SCOPES)}"
            )

        content = build_paged_content(doc)
        if content:
            if len(content) <= self.max_single_pass_chars:
                data = self._analyze_single(
                    content, analysis_type, temperature, max_tokens
                )
            else:
                data = self._analyze_map_reduce(
                    content, analysis_type, temperature, max_tokens
                )
        else:
            logger.warning(f"文档无正文，仅返回文献信息: {doc.title}")
            data = {}

        analysis: dict[str, Any] = {
            "title": doc.title or "",
            "authors": list(doc.authors or []),
            "year": doc.year or "",
            "journal": doc.journal or "",
        }
        analysis.update(self._normalize(data, analysis_type))
        return analysis

    # ------------------------------------------------------------------
    # 内部分析流程
    # ------------------------------------------------------------------
    def _analyze_single(
        self,
        content: str,
        analysis_type: str,
        temperature: float,
        max_tokens: int,
    ) -> dict:
        prompt = ANALYSIS_USER_PROMPT.format(
            scope=_ANALYSIS_SCOPES[analysis_type],
            content=content,
            schema=schema_for(analysis_type),
        )
        return self._parse(
            self.chat(prompt, temperature=temperature, max_tokens=max_tokens)
        )

    def _analyze_map_reduce(
        self,
        content: str,
        analysis_type: str,
        temperature: float,
        max_tokens: int,
    ) -> dict:
        batches = split_into_batches(content, self.max_batch_chars)
        workers = max(1, min(self.max_workers, len(batches)))
        logger.info(
            f"正文 {len(content)} 字，分 {len(batches)} 片做局部分析"
            f"（并发 {workers}）"
        )

        def run_batch(batch: str) -> dict:
            try:
                return self._analyze_single(
                    batch, analysis_type, temperature, max_tokens
                )
            except Exception as e:  # noqa: BLE001 - 单片失败不应中断整次分析
                logger.warning(f"局部分析失败，跳过该片: {e}")
                return {}

        if workers == 1:
            results = [run_batch(batch) for batch in batches]
        else:
            # pool.map 保持输入顺序，便于合并阶段稳定复现
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(run_batch, batches))

        partials = [data for data in results if data]
        if not partials:
            return {}
        if len(partials) == 1:
            return partials[0]

        merged = self._merge_partials(
            partials, analysis_type, temperature, max_tokens
        )
        return merged or self._fallback_merge(partials, analysis_type)

    def _merge_partials(
        self,
        partials: list[dict],
        analysis_type: str,
        temperature: float,
        max_tokens: int,
    ) -> dict:
        prompt = ANALYSIS_MERGE_PROMPT.format(
            schema=schema_for(analysis_type),
            partials=json.dumps(partials, ensure_ascii=False, indent=2),
        )
        try:
            raw = self.chat(prompt, temperature=temperature, max_tokens=max_tokens)
        except Exception as e:  # noqa: BLE001 - 合并失败不应让整次分析失败
            logger.warning(f"局部结果合并请求失败，改用确定性合并: {e}")
            return {}

        merged = self._parse(raw)
        if not merged:
            logger.warning("局部结果合并未被解析为 JSON，改用确定性合并")
        return merged

    @staticmethod
    def _fallback_merge(partials: list[dict], analysis_type: str) -> dict:
        """不依赖 LLM 的兜底合并：拼接 + 去重"""
        method_texts: list[str] = []
        method_pages: list[int] = []
        findings: list[dict] = []
        limitations: list[str] = []

        for partial in partials:
            method = partial.get("research_method")
            if isinstance(method, dict):
                text = str(method.get("text", "") or "").strip()
                if text:
                    method_texts.append(text)
                method_pages.extend(_as_page_list(method.get("evidence_pages")))

            raw_findings = partial.get("key_findings")
            if isinstance(raw_findings, list):
                findings.extend(
                    item for item in raw_findings if isinstance(item, dict)
                )

            raw_limitations = partial.get("limitations")
            if isinstance(raw_limitations, list):
                limitations.extend(
                    str(item) for item in raw_limitations if str(item).strip()
                )

        merged: dict[str, Any] = {}
        if analysis_type in ("full", "method"):
            merged["research_method"] = {
                "text": " ".join(method_texts).strip(),
                "evidence_pages": method_pages,
            }
        if analysis_type in ("full", "results"):
            merged["key_findings"] = findings
        if analysis_type in ("full", "limitations"):
            merged["limitations"] = limitations
        return merged

    # ------------------------------------------------------------------
    # 解析与规整
    # ------------------------------------------------------------------
    @staticmethod
    def _parse(raw: str) -> dict:
        from rag.tag_extractor import safe_parse_json

        data = safe_parse_json(raw)
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _normalize(data: dict, analysis_type: str) -> dict:
        """把 LLM 输出规整为契约要求的形状（缺字段补空，始终返回全部键）"""
        data = data or {}

        method = data.get("research_method")
        if isinstance(method, dict):
            research_method = {
                "text": str(method.get("text", "") or "").strip(),
                "evidence_pages": _as_page_list(method.get("evidence_pages")),
            }
        else:
            research_method = {"text": "", "evidence_pages": []}

        findings: list[dict] = []
        raw_findings = data.get("key_findings")
        if isinstance(raw_findings, list):
            for item in raw_findings:
                if isinstance(item, dict):
                    text = str(item.get("text", "") or "").strip()
                    if text:
                        findings.append(
                            {
                                "text": text,
                                "evidence_pages": _as_page_list(
                                    item.get("evidence_pages")
                                ),
                            }
                        )
                elif isinstance(item, str) and item.strip():
                    findings.append(
                        {"text": item.strip(), "evidence_pages": []}
                    )

        limitations: list[str] = []
        seen: set[str] = set()
        raw_limitations = data.get("limitations")
        if isinstance(raw_limitations, list):
            for item in raw_limitations:
                text = str(item or "").strip()
                if text and text not in seen:
                    seen.add(text)
                    limitations.append(text)
        elif isinstance(raw_limitations, str) and raw_limitations.strip():
            limitations.append(raw_limitations.strip())

        return {
            "research_method": research_method,
            "key_findings": findings,
            "limitations": limitations,
        }
