"""检查 PDF 中的关键词格式 — 扫描全文"""
import os
import sys

if "PYTHONPATH" in os.environ:
    del os.environ["PYTHONPATH"]
sys.path = [p for p in sys.path if "hermes" not in p]
sys.path.insert(0, ".")

from pathlib import Path
from readers.pdf_reader import PDFReader
import re

pdf_dir = Path("input/papers")
pdf_files = sorted(pdf_dir.glob("*.pdf"))

reader = PDFReader()

# 扩展的关键词匹配模式
patterns = [
    r"关键词[：:]\s*(.+?)(?:\n|$)",
    r"关键 词[：:]\s*(.+?)(?:\n|$)",
    r"Key\s*words[：:]\s*(.+?)(?:\n|$)",
    r"Keywords[：:]\s*(.+?)(?:\n|$)",
    r"KEY\s*WORDS[：:]\s*(.+?)(?:\n|$)",
    r"Index\s*Terms[：:]\s*(.+?)(?:\n|$)",
    r"索引词[：:]\s*(.+?)(?:\n|$)",
]

for i, pdf_path in enumerate(pdf_files, 1):
    print(f"\n{'='*80}")
    print(f"[{i}] {pdf_path.name}")
    print(f"{'='*80}")

    doc = reader.read(str(pdf_path))
    full_text = "\n".join(c.text for c in doc.chunks) if doc.chunks else ""

    found = False
    for pattern in patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            raw = match.group(1).strip()
            print(f"  ✅ 匹配: {pattern}")
            print(f"     原始: {raw[:200]}")
            found = True
            break

    if not found:
        # 尝试搜索 "关键" 或 "keyword" 附近的内容
        for m in re.finditer(r"(关键|keyword)", full_text, re.IGNORECASE):
            start = max(0, m.start() - 20)
            end = min(len(full_text), m.end() + 100)
            context = full_text[start:end]
            print(f"  🔍 找到关键词标记: ...{context}...")
            break
        else:
            print(f"  ❌ 未找到任何关键词标记")
