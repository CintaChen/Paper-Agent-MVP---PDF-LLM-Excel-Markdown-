"""内容标签提取器 — 混合策略：PDF 自带关键词 + LLM 补充"""

import re
import json
from typing import Optional
from config.logging import setup_logging
from core.document import Document, ContentTag
from core.llm import LLMClient
from rag.tag_prompts import CONTENT_TAG_SYSTEM_PROMPT, CONTENT_TAG_USER_PROMPT

logger = setup_logging(__name__)

# 停用词表：过滤掉过于泛化的关键词
STOP_WORDS = {"研究", "分析", "方法", "技术", "系统", "应用", "基于", "面向", "设计", "实现", "探讨", "发展", "理论", "模型"}


def safe_parse_json(text: str) -> dict:
    """鲁棒解析 LLM 输出的 JSON

    处理以下脏数据：
    - 前后有 ```json ... ``` 代码块标记
    - 前后有非 JSON 文本
    - 单引号代替双引号
    - 末尾多余逗号
    """
    if not text:
        return {}

    # 去除首尾空白
    text = text.strip()

    # 去除 ```json ... ``` 代码块
    if text.startswith("```"):
        # 匹配 ```json ... ``` 或 ``` ... ```
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()

    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试修复单引号
    try:
        fixed = text.replace("'", '"')
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # 尝试提取第一个 { ... } 块
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    logger.warning(f"无法解析 LLM 输出为 JSON: {text[:200]}...")
    return {}


def _clean_pdf_text(text: str) -> str:
    """清理 PDF 文本中的不可见字符

    PyMuPDF 提取文本时会插入 BiDi 方向控制字符和其他不可见字符：
    - \\u202d (Left-to-Right Override)
    - \\u202c (Pop Directional Formatting)
    - \\u202e (Right-to-Left Override)
    - \\x02, \\u0002 (Start of Text)
    - \\u200b (Zero Width Space)
    - \\ufeff (Zero Width No-Break Space / BOM)
    """
    # 移除 BiDi 控制字符
    text = re.sub(r"[\u202a-\u202e\u2066-\u2069]", "", text)
    # 移除其他不可见控制字符（保留 \\n \\r \\t）
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u0002\u200b\ufeff]", "", text)
    return text


def extract_keywords_from_text(text: str) -> tuple[list[str], str | None]:
    """从论文文本中提取自带关键词

    返回 (keywords_list, raw_keywords_text_or_None)
    - keywords_list: 清洗后的关键词列表
    - raw_keywords_text: 匹配到的原始 Keywords 文本（用于 LLM 兜底）

    支持两种输入：
    1. 包含 Keywords 前缀的文本（如 "Keywords: AI, ML"）
    2. 纯关键词文本（如 "AI, ML, DL"）

    注意：PDF 文本中可能包含不可见字符（BiDi 标记等），需先清理。
    """
    if not text:
        return [], None

    # 清理不可见字符
    cleaned = _clean_pdf_text(text)

    # 尝试匹配带前缀的 Keywords 段落
    patterns = [
        r"关键词[：:\s]\s*(.+?)(?:\n|$)",
        r"Key\s*words[：:\s]\s*(.+?)(?:\n|$)",
        r"Keywords[：:\s]\s*(.+?)(?:\n|$)",
        r"KEY\s*WORDS[：:\s]\s*(.+?)(?:\n|$)",
        r"Index\s*Terms[：:\s]\s*(.+?)(?:\n|$)",
        r"(?i)keywords\s+([A-Z][^,.]{3,}(?:\s*[▪·×|]\s*[^,.]{3,})+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            raw = match.group(1).strip()
            keywords = _parse_keywords_from_raw(raw)
            if keywords:
                return keywords[:10], raw

    # 如果没有匹配到前缀，尝试直接解析（仅当文本包含分隔符时）
    if re.search(r'[,;，；、▪·×|•\x02]', cleaned):
        keywords = _parse_keywords_from_raw(cleaned)
        if keywords:
            return keywords[:10], cleaned

    return [], None


def _parse_keywords_from_raw(raw: str) -> list[str]:
    """从原始关键词文本中解析关键词列表"""
    if not raw:
        return []

    # 将 •、▪、·、×、| 等特殊符号替换为逗号
    raw_normalized = re.sub(r'[▪·×|]', ',', raw)
    # 处理 • (bullet)
    raw_normalized = re.sub(r'\s*•\s*', ',', raw_normalized)
    # 支持多种分隔符
    keywords = re.split(r"[；;，,、\x02\u0002]\s*", raw_normalized)
    # 清洗
    keywords = [
        kw.strip()
        for kw in keywords
        if kw.strip()
        and kw.strip() not in STOP_WORDS
        and len(kw.strip()) >= 2
        and re.search(r"\w", kw.strip())
    ]
    return keywords


def fix_keyword_spacing(kw: str) -> str:
    """修复 PDF 提取导致的空格丢失"""
    # 在括号前补空格: Generation(RAG) → Generation (RAG)
    kw = re.sub(r'([a-zA-Z])\(', r'\1 (', kw)
    # 在小写接大写处补空格: EnterpriseAI → Enterprise AI
    kw = re.sub(r'([a-z])([A-Z])', r'\1 \2', kw)
    # 修复 "word(" 后面缺少空格的情况
    kw = re.sub(r'\)([A-Z])', r') \1', kw)
    return kw.strip()


class ContentTagExtractor:
    """内容标签提取器 — 混合策略"""

    def __init__(self, llm_client: LLMClient = None):
        self.llm_client = llm_client or LLMClient()

    def extract(self, doc: Document) -> list[ContentTag]:
        """提取内容标签（含 LLM 兜底）"""
        tags = []

        # === 1. 提取自带关键词 ===
        introduction_for_keywords = self._get_introduction_text(doc, max_chars=5000)
        keywords, raw_keywords_text = extract_keywords_from_text(introduction_for_keywords)

        # 🆕 修复关键词空格
        from rag.tag_extractor import fix_keyword_spacing
        keywords = [fix_keyword_spacing(kw) for kw in keywords]

        for kw in keywords:
            tags.append(ContentTag(
                tag_type="topic",
                value=kw,
                confidence=1.0,
                evidence="论文自带关键词",
                source="pdf_keywords",
                needs_review=False,
            ))

        # 🆕 LLM 兜底：Keywords 质量差时，用 LLM 重新提取
        need_llm_keywords = (
            len(keywords) < 2 or
            any(len(kw) > 50 for kw in keywords)
        )
        llm_fallback_topics = []
        if need_llm_keywords:
            if raw_keywords_text and len(raw_keywords_text) > 10:
                # 有 Keywords 原文 → 让 LLM 解析
                llm_fallback_topics = self._llm_parse_keywords(raw_keywords_text)
            else:
                # 无 Keywords 段落 → 让 LLM 从 Abstract 概括
                abstract = doc.metadata.get("abstract", "") or self._extract_abstract(doc)
                if abstract:
                    llm_fallback_topics = self._llm_fallback_topics(abstract)

            for ft in llm_fallback_topics:
                tags.append(ContentTag(
                    tag_type="topic",
                    value=ft,
                    confidence=0.5,
                    evidence="LLM 兜底提取",
                    source="llm_fallback",
                    needs_review=True,
                ))

        # === 2. LLM 补充提取 ===
        title = doc.title
        abstract = doc.metadata.get("abstract", "") or self._extract_abstract(doc)
        introduction = self._get_introduction_text(doc)

        # 准备 Keywords 信息
        if len(keywords) >= 2:
            keywords_info = f"Keywords（来自 PDF）：{', '.join(keywords)}"
        else:
            keywords_info = "Keywords：无（需要从摘要中提取）"

        # 如果摘要和引言都为空，跳过 LLM 提取
        if not abstract and not introduction:
            logger.warning(f"论文无摘要/引言，跳过 LLM 标签提取: {doc.title}")
            return tags

        prompt = CONTENT_TAG_USER_PROMPT.format(
            title=title,
            abstract=abstract or "（无摘要）",
            introduction=introduction or "（无引言）",
            content=introduction or abstract or "（无内容）",
            keywords_info=keywords_info,
        )

        llm_topics = []
        try:
            result = self.llm_client.chat(
                system_prompt=CONTENT_TAG_SYSTEM_PROMPT,
                user_prompt=prompt,
            )
            parsed = safe_parse_json(result)

            if parsed:
                # domain
                domain = parsed.get("domain", "")
                if domain:
                    domain_evidence = ""
                    evidence_dict = parsed.get("evidence", {})
                    if isinstance(evidence_dict, dict):
                        domain_evidence = evidence_dict.get("domain", "")
                    tags.append(ContentTag(
                        tag_type="domain",
                        value=domain,
                        confidence=parsed.get("confidence", 0.5),
                        evidence=domain_evidence[:200],
                        source="llm_extracted",
                        needs_review=parsed.get("needs_review", False),
                    ))

                # topics
                llm_topics = parsed.get("topics", [])
                topic_evidence_list = []
                if isinstance(parsed.get("evidence"), dict):
                    ev = parsed["evidence"].get("topics", [])
                    topic_evidence_list = ev if isinstance(ev, list) else []

                for i, topic in enumerate(llm_topics):
                    topic_ev = topic_evidence_list[i] if i < len(topic_evidence_list) else ""
                    tags.append(ContentTag(
                        tag_type="topic",
                        value=topic,
                        confidence=parsed.get("confidence", 0.5),
                        evidence=topic_ev[:200],
                        source="llm_extracted",
                        needs_review=parsed.get("needs_review", False),
                    ))

                # methodologies
                methodologies = parsed.get("methodologies", [])
                evidence_list = []
                if isinstance(parsed.get("evidence"), dict):
                    evidence_list = parsed["evidence"].get("methodologies", [])

                for i, method in enumerate(methodologies):
                    method_evidence = evidence_list[i] if i < len(evidence_list) else ""
                    tags.append(ContentTag(
                        tag_type="methodology",
                        value=method,
                        confidence=parsed.get("confidence", 0.5),
                        evidence=method_evidence[:200],
                        source="llm_extracted",
                        needs_review=parsed.get("needs_review", False),
                    ))

        except Exception as e:
            logger.error(f"LLM 标签提取失败: {e}")

        # === 3. 去重（保留高置信度）===
        tags = self._deduplicate(tags)

        logger.info(f"标签提取完成: {doc.title} — {len(tags)} 个标签（{len(keywords)} 个来自自带关键词）")
        return tags

    def _llm_parse_keywords(self, raw_keywords_text: str) -> list[str]:
        """LLM 兜底：解析 Keywords 原文"""
        if not raw_keywords_text or len(raw_keywords_text) < 10:
            return []

        try:
            prompt = f"""请从以下 Keywords 文本中提取关键词。

要求：
- 忠于原文，禁止编造
- 只输出 JSON 数组格式，如：["关键词1", "关键词2"]
- 修复空格丢失（如 "EnterpriseAI" → "Enterprise AI"）
- 过滤垃圾数据（如 "1."、"2." 等章节编号）

Keywords 文本：
{raw_keywords_text[:1000]}

输出："""

            result = self.llm_client.chat(
                system_prompt="你是学术文献分析专家。",
                user_prompt=prompt,
                max_tokens=200
            )

            match = re.search(r'\[.*\]', result, re.DOTALL)
            if match:
                topics = json.loads(match.group(0))
                if isinstance(topics, list) and len(topics) >= 2:
                    return [fix_keyword_spacing(t) for t in topics[:10]]
        except Exception:
            pass

        return []

    def _llm_fallback_topics(self, text: str) -> list[str]:
        """LLM 兜底：从文本中提取 2-5 个核心主题"""
        if not text or len(text) < 50:
            return []

        try:
            prompt = f"""请从以下学术文本中提取 2-5 个核心主题关键词。

要求：
- 必须是文本中明确讨论的研究主题
- 使用中文（如原文是英文则翻译为中文）
- 输出 JSON 数组格式，如：["主题1", "主题2"]

文本：
{text[:2000]}

输出："""

            result = self.llm_client.chat(
                system_prompt="你是学术文献分析专家。",
                user_prompt=prompt,
                max_tokens=200
            )

            # 解析 JSON 数组
            match = re.search(r'\[.*\]', result, re.DOTALL)
            if match:
                topics = json.loads(match.group(0))
                if isinstance(topics, list) and len(topics) >= 2:
                    return topics[:5]
        except Exception:
            pass

        return []

    def _extract_abstract(self, doc: Document) -> str:
        """从 PDF 前 2 页提取摘要"""
        if not doc.chunks:
            return ""

        # 取前 2 页的 chunks
        abstract_chunks = [c for c in doc.chunks if c.page and c.page <= 2]
        if not abstract_chunks:
            abstract_chunks = doc.chunks[:3]  # fallback: 前 3 个 chunk

        text = "\n".join(c.text for c in abstract_chunks)

        # 尝试匹配 "摘要" / "Abstract" 后面的内容
        patterns = [
            r"摘要[：:]?\s*(.+?)(?:\n\n|\n关键词|$)",
            r"Abstract[：:]?\s*(.+?)(?:\n\n|\nKey|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()[:1000]

        # fallback: 返回前 500 字
        return text[:500]

    def _get_introduction_text(self, doc: Document, max_chars: int = 2000) -> str:
        """获取引言部分（前 N 个 chunk 的文本拼接）"""
        if not doc.chunks:
            return ""

        text = ""
        for chunk in doc.chunks:
            if len(text) + len(chunk.text) > max_chars:
                remaining = max_chars - len(text)
                if remaining > 0:
                    text += chunk.text[:remaining]
                break
            text += chunk.text + "\n"

        return text[:max_chars]

    def _deduplicate(self, tags: list[ContentTag]) -> list[ContentTag]:
        """去重：相同 tag_type + value 保留置信度高的"""
        seen = {}
        for tag in tags:
            key = (tag.tag_type, tag.value)
            if key not in seen or tag.confidence > seen[key].confidence:
                seen[key] = tag
        return list(seen.values())
