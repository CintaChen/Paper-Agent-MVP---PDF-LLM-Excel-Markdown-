"""检查 PDF 中的关键词格式"""
import os
import sys

if "PYTHONPATH" in os.environ:
    del os.environ["PYTHONPATH"]
sys.path = [p for p in sys.path if "hermes" not in p]
sys.path.insert(0, ".")

from pathlib import Path
from readers.pdf_reader import PDFReader

pdf_dir = Path("input/papers")
pdf_files = sorted(pdf_dir.glob("*.pdf"))

reader = PDFReader()

for i, pdf_path in enumerate(pdf_files, 1):
    print(f"\n{'='*80}")
    print(f"[{i}] {pdf_path.name}")
    print(f"{'='*80}")

    doc = reader.read(str(pdf_path))
    # 只看前 3 页的文本
    for chunk in doc.chunks[:5]:
        if chunk.page and chunk.page <= 2:
            text = chunk.text[:1500]
            print(f"\n--- 第 {chunk.page} 页 ---")
            print(text)
            print()
