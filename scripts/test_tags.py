"""快速测试标签提取 — 不依赖 Milvus"""
import os
import sys

# 清理 hermes 路径
if "PYTHONPATH" in os.environ:
    del os.environ["PYTHONPATH"]
sys.path = [p for p in sys.path if "hermes" not in p]
sys.path.insert(0, ".")

from pathlib import Path
from readers.pdf_reader import PDFReader
from rag.tag_extractor import ContentTagExtractor

pdf_dir = Path("input/papers")
pdf_files = sorted(pdf_dir.glob("*.pdf"))

print(f"找到 {len(pdf_files)} 篇论文\n")
print("=" * 80)

reader = PDFReader()
extractor = ContentTagExtractor()

for i, pdf_path in enumerate(pdf_files, 1):
    print(f"\n📄 [{i}/{len(pdf_files)}] {pdf_path.name}")
    print("-" * 60)

    try:
        doc = reader.read(str(pdf_path))
        print(f"   标题: {doc.title}")
        print(f"   页数: {doc.total_pages}, chunks: {len(doc.chunks)}")

        tags = extractor.extract(doc)

        if not tags:
            print("   ⚠️ 无标签")
        else:
            # 分组显示
            domains = [t for t in tags if t.tag_type == "domain"]
            topics = [t for t in tags if t.tag_type == "topic"]
            methods = [t for t in tags if t.tag_type == "methodology"]

            if domains:
                print(f"   🏷️ 领域: ", end="")
                print(", ".join([f"{d.value}({d.confidence:.1f},{d.source})" for d in domains]))

            if topics:
                print(f"   📌 主题: ", end="")
                print(", ".join([f"{t.value}({t.source})" for t in topics[:5]]))
                if len(topics) > 5:
                    print(f"          ...共 {len(topics)} 个")

            if methods:
                print(f"   🔬 方法: ", end="")
                print(", ".join([f"{m.value}({m.confidence:.1f})" for m in methods]))

            review = [t for t in tags if t.needs_review]
            if review:
                print(f"   ⚠️ 需人工确认: {len(review)} 个")

    except Exception as e:
        print(f"   ❌ 错误: {e}")

print(f"\n{'=' * 80}\n完成")
