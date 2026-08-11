"""Paper analysis processor."""
import json
import re
from config import Config
from readers.pdf_reader import PDFReader
from llm.api_client import LLMClient
from prompts import SYSTEM_PROMPT, ANALYSIS_PROMPT
from processors.output_writer import LIST_FIELDS, normalize_string_list


# DOI 正则：匹配 10.xxxx/... 格式
DOI_PATTERN = re.compile(r'10\.\d{4,}/\S+', re.IGNORECASE)

# 需要证据定位的字段
EVIDENCE_FIELDS = {"research_method", "data_source", "key_findings"}

# 文本质量阈值：少于该字符数视为疑似扫描版
MIN_TEXT_LENGTH = 200


def clean_json_text(text: str) -> str:
    """清洗模型返回的文本，提取 JSON 主体"""
    text = text.strip()
    # 去掉可能的 Markdown 代码块
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # 如果模型前后多说了话，尽量截取 JSON 主体
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return text


def safe_parse_json(text: str) -> dict:
    """安全解析 JSON，先清洗文本再解析"""
    cleaned = clean_json_text(text)
    return json.loads(cleaned)


def extract_doi(text: str) -> tuple:
    """从论文文本中提取 DOI。
    返回 (doi, doi_status)：
      - 找到唯一明确的 DOI → (doi, "已找到")
      - 找到多个候选 → (第一个候选, "待确认")
      - 未找到 → (None, "未找到")
    """
    matches = DOI_PATTERN.findall(text)
    if not matches:
        return None, "未找到"
    # 清理末尾可能的标点
    matches = [m.rstrip('.,;)') for m in matches]
    if len(matches) == 1:
        return matches[0], "已找到"
    return matches[0], "待确认"


def normalize_evidence_field(value, field_name: dict | str) -> dict | list[dict]:
    """规范化证据字段。
    - research_method / data_source: 转为 {"text": "", "evidence_pages": [], "evidence_excerpt": ""}
    - key_findings: 转为 [{"text": "", "evidence_pages": [], "evidence_excerpt": ""}, ...]
    - 兼容旧字符串格式
    """
    default_single = {"text": "", "evidence_pages": [], "evidence_excerpt": ""}

    if field_name == "key_findings":
        # key_findings 应该是列表
        if value is None:
            return []
        if isinstance(value, list):
            result = []
            for item in value:
                if isinstance(item, dict):
                    result.append({
                        "text": str(item.get("text", "")),
                        "evidence_pages": _normalize_pages(item.get("evidence_pages")),
                        "evidence_excerpt": str(item.get("evidence_excerpt", ""))
                    })
                elif isinstance(item, str):
                    # 旧格式：纯字符串
                    result.append({"text": item, "evidence_pages": [], "evidence_excerpt": ""})
            return result
        if isinstance(value, str):
            # 旧格式：单个字符串
            return [{"text": value, "evidence_pages": [], "evidence_excerpt": ""}]
        return []

    # research_method / data_source
    if isinstance(value, dict):
        return {
            "text": str(value.get("text", "")),
            "evidence_pages": _normalize_pages(value.get("evidence_pages")),
            "evidence_excerpt": str(value.get("evidence_excerpt", ""))
        }
    if isinstance(value, str):
        # 旧格式：纯字符串
        return {"text": value, "evidence_pages": [], "evidence_excerpt": ""}
    return default_single


def _normalize_pages(pages) -> list[int]:
    """规范化页码为整数列表"""
    if pages is None:
        return []
    if isinstance(pages, int):
        return [pages]
    if isinstance(pages, list):
        result = []
        for p in pages:
            try:
                result.append(int(p))
            except (ValueError, TypeError):
                continue
        return result
    return []


class PaperAnalyzer:
    def __init__(self, config: Config):
        self.config = config
        self.reader = PDFReader(config.input_dir)
        self.llm = LLMClient(config)

    def discover_papers(self) -> list[dict]:
        paths = self.reader.list_papers()
        return [{"path": p, "title": p.split(chr(92))[-1]} for p in paths]

    def analyze(self, paper: dict) -> tuple[dict, bool, list[str]]:
        """分析论文。
        返回 (result, needs_review, review_reasons)：
          - result: 分析结果字典
          - needs_review: 是否需要人工确认
          - review_reasons: 需要确认的原因列表
        """
        review_reasons = []
        needs_review = False

        # 读取分页内容用于模型提示
        pages = self.reader.read_paginated(paper["path"])
        content_for_prompt = PDFReader.format_for_prompt(pages)

        # 读取完整文本用于 DOI 提取和质量检查
        full_content = self.reader.read(paper["path"])

        # === 文本质量检查 ===
        if len(full_content.strip()) < MIN_TEXT_LENGTH:
            # 疑似扫描版，跳过 LLM 调用
            review_reasons.append(f"疑似扫描版（提取文本仅 {len(full_content.strip())} 字符）")
            needs_review = True
            parsed = {
                "extracted_title": paper["title"],
                "authors": [],
                "year": None,
                "journal": None,
                "research_background": "",
                "research_question": "",
                "research_objective": "",
                "research_method": {"text": "", "evidence_pages": [], "evidence_excerpt": ""},
                "model_or_framework": "",
                "data_source": {"text": "", "evidence_pages": [], "evidence_excerpt": ""},
                "experimental_design": "",
                "analysis_process": "",
                "key_findings": [],
                "contributions": "",
                "limitations_reported": [],
                "limitations_inferred": [],
                "relevance_score": "",
                "summary": "",
                "raw_text": full_content[:500],
            }
            doi, doi_status = extract_doi(full_content)
            parsed["doi"] = doi
            parsed["doi_status"] = doi_status
            parsed["original_filename"] = paper["title"]
            parsed["path"] = paper["path"]
            return parsed, needs_review, review_reasons

        # === 正常 LLM 调用 ===
        prompt = ANALYSIS_PROMPT.format(
            title=paper["title"],
            content=content_for_prompt,
            evaluation_topic=self.config.evaluation_topic
        )
        result = self.llm.chat(SYSTEM_PROMPT, prompt)

        # 解析 JSON
        try:
            parsed = safe_parse_json(result)
        except json.JSONDecodeError:
            # JSON 解析失败，标记为待确认
            review_reasons.append("JSON 解析失败")
            needs_review = True
            parsed = {
                "extracted_title": paper["title"],
                "research_question": "",
                "methodology": "",
                "key_findings": "",
                "limitations": "",
                "relevance_score": "",
                "summary": result,
                "raw_llm_response": result[:1000],
            }

        # 统一列表字段为 list[str]
        for field in LIST_FIELDS:
            if field in parsed:
                parsed[field] = normalize_string_list(parsed[field])

        # 处理证据字段
        for field in EVIDENCE_FIELDS:
            if field in parsed:
                parsed[field] = normalize_evidence_field(parsed[field], field)

        # 处理研究局限：支持新字段，兼容旧字段
        parsed["limitations_reported"] = normalize_string_list(
            parsed.get("limitations_reported")
        )
        parsed["limitations_inferred"] = normalize_string_list(
            parsed.get("limitations_inferred")
        )
        # 兼容旧字段：如果只有旧 limitations，内容归入 limitations_reported
        if "limitations" in parsed and not parsed.get("limitations_reported"):
            parsed["limitations_reported"] = normalize_string_list(
                parsed.get("limitations")
            )
        # 删除旧字段，避免混淆
        parsed.pop("limitations", None)

        # 规范化元数据字段
        parsed["authors"] = normalize_string_list(parsed.get("authors"))

        # year: 保持字符串或 null
        year = parsed.get("year")
        if isinstance(year, str) and year.strip() in ("", "null", "None", "未识别", "未明确提及"):
            parsed["year"] = None
        elif year is None:
            parsed["year"] = None

        # journal: 保持字符串或 null
        journal = parsed.get("journal")
        if isinstance(journal, str) and journal.strip() in ("", "null", "None", "未识别", "未明确提及"):
            parsed["journal"] = None
        elif journal is None:
            parsed["journal"] = None

        # DOI 从论文文本中提取（不依赖模型）
        doi, doi_status = extract_doi(full_content)
        parsed["doi"] = doi
        parsed["doi_status"] = doi_status

        # === 检查是否需要人工确认 ===
        # 检查标题
        extracted_title = parsed.get("extracted_title", "")
        if not extracted_title or extracted_title in ("未识别", "未明确提及"):
            review_reasons.append("标题未识别")
            needs_review = True

        # 检查作者
        authors = parsed.get("authors", [])
        if not authors:
            review_reasons.append("作者未识别")
            needs_review = True

        # 检查年份
        if parsed.get("year") is None:
            review_reasons.append("年份未识别")
            needs_review = True

        # 检查 DOI
        if parsed.get("doi_status") == "未找到":
            review_reasons.append("DOI 未找到")
            needs_review = True

        parsed["original_filename"] = paper["title"]
        parsed["path"] = paper["path"]
        return parsed, needs_review, review_reasons
