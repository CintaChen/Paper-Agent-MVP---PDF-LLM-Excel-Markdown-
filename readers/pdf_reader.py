"""PDF 文档读取器"""
import re
from pathlib import Path
from typing import Optional

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None

from config.logging import setup_logging
from core.document import Document, Chunk
from readers.base import BaseReader

logger = setup_logging(__name__)


class PDFReader(BaseReader):
    """PDF 读取器"""

    def __init__(self, input_dir: str = None):
        from config.settings import settings
        self.input_dir = Path(input_dir or settings.input_dir)

    def list_papers(self) -> list[str]:
        """列出所有 PDF 文件"""
        if not self.input_dir.exists():
            return []
        return [str(p) for p in self.input_dir.glob("*.pdf")]

    def read(self, file_path: str) -> Document:
        """读取 PDF 全部内容"""
        if fitz is None:
            raise RuntimeError("PyMuPDF 未安装")

        doc = fitz.open(file_path)
        pages_data = []
        for page_num, page in enumerate(doc, 1):
            raw_text = page.get_text()
            cleaned_text = self._clean_raw_text(raw_text)
            pages_data.append({
                "page": page_num,
                "text": cleaned_text,
            })
        doc.close()

        full_text = "\n\n".join(p["text"] for p in pages_data)

        # 智能提取摘要
        abstract = self._extract_abstract(full_text)

        # 提取 Keywords（使用清洗后文本）
        keywords = self._extract_keywords_from_text(full_text)

        title = self._extract_title(file_path, pages_data)
        doi = self._extract_doi(full_text)
        chunks = self._build_chunks(pages_data, file_path)

        return Document(
            id=self._make_doc_id(file_path),
            title=title,
            doi=doi,
            file_path=file_path,
            total_pages=len(pages_data),
            chunks=chunks,
            metadata={
                "keywords": keywords,
                "abstract": abstract,
            },
        )

    def read_paginated(self, file_path: str) -> list[dict]:
        """读取 PDF，保留分页"""
        if fitz is None:
            raise RuntimeError("PyMuPDF 未安装")

        doc = fitz.open(file_path)
        pages = []
        for page_num, page in enumerate(doc, 1):
            pages.append({
                "page": page_num,
                "text": page.get_text(),
            })
        doc.close()
        return pages

    @staticmethod
    def format_for_prompt(pages: list[dict]) -> str:
        """格式化为带 PAGE 标记的文本"""
        parts = []
        for p in pages:
            parts.append(f"===== PAGE {p['page']} =====\n{p['text']}")
        return "\n\n".join(parts)

    def _clean_raw_text(self, text: str) -> str:
        """清洗 PDF 原始文本（V2 增强版）"""
        import unicodedata

        # 1. 去除零宽字符和控制字符
        text = ''.join(
            char for char in text
            if unicodedata.category(char)[0] != 'C' or char in ('\n', '\t', '\r')
        )

        # 2. 去除零宽空格
        text = re.sub(r'[\u200B\u200C\u200D\uFEFF]', '', text)

        # 3. 过滤纯数字行（000, 001, 002...）
        text = re.sub(r'^\d{1,4}\s*$', '', text, flags=re.MULTILINE)

        # 4. 过滤连续空白行
        text = re.sub(r'\n{3,}', '\n\n', text)

        # 5. 过滤行首行尾空白
        lines = [line.strip() for line in text.split('\n')]

        # 6. 过滤空行
        lines = [line for line in lines if line]

        return '\n'.join(lines)

    def _extract_abstract(self, text: str) -> str:
        """
        智能提取摘要（V2 重构）
        - 双重匹配：先找 Abstract 标记，再验证内容合理性
        - 长度兜底：摘要超过 3000 字时强制截断
        - 置信度验证：检查提取内容是否像摘要
        """

        # === 第一阶段：定位 Abstract 起始位置 ===
        abstract_start = -1
        abstract_header_end = -1

        # 匹配模式（按优先级排序）
        start_patterns = [
            (r'(?i)\babstract\b[：:.]?\s*', 0),
            (r'(?i)\b摘要\b[：:.]?\s*', 0),
            (r'(?i)\babstract\b\s*\n\s*', 0),
            (r'(?i)\ba\s*b\s*s\s*t\s*r\s*a\s*c\s*t\b', 0),
        ]

        for pattern, offset in start_patterns:
            match = re.search(pattern, text)
            if match:
                abstract_start = match.start()
                abstract_header_end = match.end()
                break

        if abstract_start == -1:
            return ""

        # === 第二阶段：定位 Abstract 结束位置 ===
        remaining = text[abstract_header_end:]

        # 结束标志（按优先级）
        end_markers = [
            r'\n\s*1\s*[.．]\s*\s*introduction',
            r'\n\s*1\s*[.．]\s*\s*引言',
            r'\n\s*1\s*[.．]\s*\s*background',
            r'\n\s*keywords?\b',
            r'\n\s*关键词\b',
            r'\n\s*\d+\s*[.．]\s*\s*[A-Z]',
            r'\n\s*I\s*ntroduction',
            r'\n\s*abstract\b.*?\n\s*abstract',
            r'(?m)^\s*\d+\s*$',
        ]

        abstract_end = len(remaining)
        for pattern in end_markers:
            match = re.search(pattern, remaining, re.IGNORECASE)
            if match and 100 < match.start() < 5000:
                abstract_end = match.start()
                break

        abstract = remaining[:abstract_end].strip()

        # === 第三阶段：后处理 ===
        # 1. 清理开头的非字母数字字符
        abstract = re.sub(r'^[^\w\u4e00-\u9fff]+', '', abstract)

        # 2. 如果摘要超过 3000 字，尝试在句子边界截断
        if len(abstract) > 3000:
            last_sentence_end = max(
                abstract.rfind('。', 0, 3000),
                abstract.rfind('.', 0, 3000),
                abstract.rfind('？', 0, 3000),
                abstract.rfind('！', 0, 3000),
            )
            if last_sentence_end > 500:
                abstract = abstract[:last_sentence_end + 1]

        # 3. 验证：摘要中不应包含 "Figure X" 或 "Table X"
        if re.search(r'(?i)\b(figure|table)\s+\d+', abstract[-200:]):
            match = re.search(r'(?i)\b(figure|table)\s+\d+', abstract)
            if match and match.start() > 200:
                abstract = abstract[:match.start()].strip()

        return abstract

    def _extract_title(self, file_path: str, pages_data: list[dict]) -> str:
        """多策略标题提取（V2 增强版）"""
        if not pages_data:
            return Path(file_path).stem

        # 策略 1：基于字号
        title = self._extract_title_by_fontsize(file_path)
        if title and self._is_valid_title(title):
            return self._clean_title(title)

        # 策略 2：启发式规则（增强版）
        first_page_text = pages_data[0]["text"]
        title = self._heuristic_extract_title_v2(first_page_text)
        if title and self._is_valid_title(title):
            return self._clean_title(title)

        # 策略 3：LLM 兜底
        title = self._extract_title_by_llm(first_page_text)
        if title and self._is_valid_title(title):
            return self._clean_title(title)

        return Path(file_path).stem

    def _extract_title_by_fontsize(self, file_path: str) -> Optional[str]:
        """策略 1：通过字号识别标题"""
        try:
            doc = fitz.open(file_path)
            first_page = doc[0]

            blocks = first_page.get_text("dict")["blocks"]
            max_fontsize = 0
            title_candidates = []

            for block in blocks[:20]:
                if "lines" not in block:
                    continue
                for line in block["lines"]:
                    for span in line["spans"]:
                        fontsize = span["size"]
                        text = span["text"].strip()
                        if len(text) < 10:
                            continue
                        if fontsize > max_fontsize:
                            max_fontsize = fontsize
                            title_candidates = [text]
                        elif fontsize == max_fontsize:
                            title_candidates.append(text)

            doc.close()

            if title_candidates:
                return " ".join(title_candidates)[:200]
        except Exception:
            pass
        return None

    def _heuristic_extract_title_v2(self, first_page_text: str) -> Optional[str]:
        """启发式提取标题（V2 增强噪音过滤）"""
        noise_patterns = [
            r'(?i)available\s+online\s+at',
            r'(?i)academic\s+editor',
            r'(?i)original\s+article',
            r'(?i)review\s+article',
            r'(?i)research\s+article',
            r'(?i)received\s*:?\s*\d{4}',
            r'(?i)accepted\s*:?\s*\d{4}',
            r'(?i)published\s*:?\s*\d{4}',
            r'(?i)doi\s*:\s*\S+',
            r'(?i)journal\s+of',
            r'(?i)proceedings\s+of',
            r'(?i)copyright\s+©',
            r'(?i)all\s+rights\s+reserved',
            r'(?i)https?://\S+',
            r'(?i)vol(ume)?\.?\s*\d+',
            r'(?i)pp\.?\s*\d+',
            r'(?i)©\s*\d{4}',
            r'(?i)submitted',
            r'(?i)citation\s*:',
            r'(?i)department\s+of',
            r'(?i)university\s+of',
            r'(?i)college\s+of',
            r'(?i)school\s+of',
            r'(?i)institute\s+of',
            r'(?i)©\s*\d{4}\s*elsevier',
            r'(?i)elsevier\s+(inc|ltd|b\.v\.?)',
            r'(?i)springer\s+(nature|science)',
            r'(?i)ieee',
            r'(?i)acm\s+',
            r'(?i)arxiv:\d+\.\d+',
            r'(?i)preprint',
            r'(?i)under\s+review',
            r'(?i)corresponding\s+author',
            r'(?i)email\s*:',
            r'(?i)tel\s*:',
            r'(?i)fax\s*:',
            r'(?i)http\s*:',
            r'(?i)www\.',
        ]

        lines = first_page_text.split('\n')
        candidates = []

        for line in lines[:20]:
            line = line.strip()
            if len(line) < 15:
                continue

            is_noise = any(re.search(p, line) for p in noise_patterns)
            if is_noise:
                continue

            candidates.append(line)

        if not candidates:
            return None

        candidates.sort(key=len, reverse=True)

        for candidate in candidates:
            if len(candidate) <= 200:
                return candidate

        return candidates[0][:200]

    def _is_valid_title(self, title: str) -> bool:
        """验证标题是否有效"""
        if not title or len(title) < 10:
            return False

        noise_starts = [
            'available', 'academic', 'original', 'received', 'accepted',
            'published', 'copyright', 'journal', 'proceedings', 'department',
            'university', 'college', 'institute', 'corresponding', 'email',
        ]
        lower = title.lower().strip()
        for noise in noise_starts:
            if lower.startswith(noise):
                return False

        return True

    def _clean_title(self, title: str) -> str:
        """清洗标题"""
        import unicodedata

        # 1. 去除零宽字符和控制字符
        title = ''.join(
            char for char in title
            if unicodedata.category(char)[0] != 'C' or char in ('\n', '\t')
        )

        # 2. 去除零宽空格
        title = re.sub(r'[\u200B\u200C\u200D\uFEFF]', '', title)

        # 3. 去除前缀噪音
        prefix_patterns = [
            r'(?i)^(review\s*article|original\s*article|research\s*article|short\s*communication|letter\s*to\s*the\s*editor)\s*[|:/-]+\s*',
            r'(?i)^(case\s*report|clinical\s*trial|systematic\s*review|meta-analysis)\s*[|:/-]+\s*',
        ]
        for pattern in prefix_patterns:
            title = re.sub(pattern, '', title, count=1)

        # 4. 去除首尾空白和特殊字符
        title = title.strip(' \t\n\r\x0b\x0c·•▪|:/-')

        # 5. 合并连续空格
        title = re.sub(r'\s+', ' ', title)

        return title[:200]

    def _extract_title_by_llm(self, first_page_text: str) -> Optional[str]:
        """策略 3：LLM 兜底"""
        try:
            from rag.tag_prompts import TITLE_EXTRACTION_PROMPT
            from core.llm import LLMClient

            llm = LLMClient()
            prompt = TITLE_EXTRACTION_PROMPT.format(text=first_page_text[:2000])
            result = llm.chat(
                system_prompt="你是学术论文解析专家。",
                user_prompt=prompt,
                max_tokens=200
            )
            title = result.strip().strip('"').strip()
            return title if len(title) > 10 else None
        except Exception:
            return None

    def _extract_doi(self, text: str) -> Optional[str]:
        """提取 DOI"""
        pattern = re.compile(r"10\.\d{4,}/\S+", re.IGNORECASE)
        match = pattern.search(text)
        return match.group(0) if match else None

    def _extract_keywords_from_text(self, text: str) -> list[str]:
        """提取 Keywords（V2 增强版，增加边界检测）"""
        from rag.tag_extractor import extract_keywords_from_text

        patterns = [
            r'(?i)keywords?\s*[:：]\s*(.+?)(?=\n\s*\n|\n\s*\d+[.]|introduction|abstract|$)',
            r'(?i)key\s*words?\s*[:：]\s*(.+?)(?=\n\s*\n|\n\s*\d+[.]|introduction|abstract|$)',
            r'(?i)index\s*terms?\s*[:：]\s*(.+?)(?=\n\s*\n|\n\s*\d+[.]|introduction|abstract|$)',
            r'关键词\s*[:：]\s*(.+?)(?=\n\s*\n|\n\s*\d+[.]|摘要|引言|$)',
            r'(?i)索引词\s*[:：]\s*(.+?)(?=\n\s*\n|\n\s*\d+[.]|摘要|引言|$)',
            # Springer 格式：Keywords 后无冒号
            r'(?i)keywords\s+([A-Z][^,.]{3,}(?:\s*[▪·×|]\s*[^,.]{3,})+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                raw_keywords = match.group(1).strip()
                if len(raw_keywords) > 500:
                    raw_keywords = raw_keywords[:500]
                result, _ = extract_keywords_from_text(raw_keywords)
                if len(result) >= 2:
                    return result

        return []

    def _split_keywords(self, raw: str) -> list[str]:
        """兼容多种分隔符（V2 增强版）"""
        if not raw:
            return []

        normalized = raw

        # 1. 替换所有 Unicode bullet 符号
        bullet_chars = [
            '\u2022', '\u2023', '\u25CF', '\u25CB', '\u25A0', '\u25A1',
            '\u25B6', '\u25C6', '\u00B7', '\u2219', '\u25E6', '\u25AA',
            '\u25AB',
        ]
        for char in bullet_chars:
            normalized = normalized.replace(char, ',')

        # 2. 替换中间带空格的点号
        normalized = re.sub(r'\s*[\u00B7\u2219\u2022]\s*', ',', normalized)

        # 3. 替换标准分隔符
        normalized = re.sub(r'[,;，；\n\r\t]+', ',', normalized)

        # 4. 替换连续空格（3个以上视为分隔符）
        normalized = re.sub(r'\s{3,}', ',', normalized)

        # === 第二阶段：分割 ===
        keywords = [kw.strip() for kw in normalized.split(',') if kw.strip()]

        # === 第三阶段：过滤噪音 ===
        filtered = []
        for kw in keywords:
            if re.match(r'^\d+$', kw):
                continue
            if re.match(r'^\d+([.]\d+)*[.\s]*$', kw):
                continue
            if len(kw) < 2:
                continue
            if kw.lower() in ['keywords', 'key words', 'index terms', '']:
                continue
            filtered.append(kw)

        # === 第四阶段：去重保序 ===
        seen = set()
        unique = []
        for kw in filtered:
            if kw.lower() not in seen:
                seen.add(kw.lower())
                unique.append(kw)

        return unique

    def _build_chunks(
        self, pages_data: list[dict], file_path: str
    ) -> list[Chunk]:
        """构建 chunks（按段落分块）"""
        chunks = []
        doc_id = self._make_doc_id(file_path)

        for page_data in pages_data:
            page_num = page_data["page"]
            text = page_data["text"]
            paragraphs = text.split("\n\n")

            for para in paragraphs:
                para = para.strip()
                if len(para) >= 50:
                    chunks.append(
                        Chunk(
                            id=f"{doc_id}_{page_num}_{len(chunks)}",
                            text=para,
                            page=page_num,
                            metadata={"doc_id": doc_id, "source": file_path},
                        )
                    )

        return chunks

    def _make_doc_id(self, file_path: str) -> str:
        """生成文档 ID"""
        import hashlib
        return hashlib.md5(file_path.encode()).hexdigest()[:16]
