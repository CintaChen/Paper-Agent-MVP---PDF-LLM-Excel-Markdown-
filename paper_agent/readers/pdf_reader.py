"""PDF paper reader."""
import os
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None

class PDFReader:
    def __init__(self, input_dir: str):
        self.input_dir = Path(input_dir)

    def list_papers(self) -> list[str]:
        if not self.input_dir.exists():
            return []
        return [str(p) for p in self.input_dir.glob("*.pdf")]

    def read(self, filepath: str) -> str:
        """读取全部文本并拼接为一个字符串（兼容旧接口）"""
        if fitz is None:
            raise RuntimeError(
                "PyMuPDF is required. Install with: python -m pip install pymupdf"
            )

        doc = fitz.open(filepath)
        text = "".join(page.get_text() for page in doc)
        doc.close()

        return text

    def read_paginated(self, filepath: str) -> list[dict]:
        """读取 PDF，保留分页信息。
        返回 [{"page": 1, "text": "..."}, ...]
        """
        if fitz is None:
            raise RuntimeError(
                "PyMuPDF is required. Install with: python -m pip install pymupdf"
            )

        doc = fitz.open(filepath)
        pages = []
        for page_num, page in enumerate(doc, 1):
            pages.append({"page": page_num, "text": page.get_text()})
        doc.close()

        return pages

    @staticmethod
    def format_for_prompt(pages: list[dict]) -> str:
        """将分页内容格式化为带 PAGE 标记的文本，发送给模型"""
        parts = []
        for p in pages:
            parts.append(f"===== PAGE {p['page']} =====\n{p['text']}")
        return "\n\n".join(parts)
