"""PDF 解析 + LLM 兜底效果验证脚本

展示内容：
1. 规则提取结果（正则匹配 Keywords）
2. LLM 兜底是否触发（条件判断）
3. LLM 兜底结果（解析 Keywords 原文 / 从 Abstract 概括）
4. 最终合并结果
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from readers.pdf_reader import PDFReader
from rag.tag_extractor import ContentTagExtractor, extract_keywords_from_text

reader = PDFReader()

pdf_dir = "./input/papers"
pdf_files = [f for f in os.listdir(pdf_dir) if f.lower().endswith('.pdf')]

print(f"发现 {len(pdf_files)} 个 PDF 文件")
print(f"=" * 100)

total_rule_keywords = 0
total_llm_fallback = 0
total_final_keywords = 0

for i, filename in enumerate(pdf_files, 1):
    filepath = os.path.join(pdf_dir, filename)
    print(f"\n{'='*100}")
    print(f"[{i}/{len(pdf_files)}] {filename}")
    print(f"{'='*100}")

    try:
        # === 第一步：读取 PDF ===
        doc = reader.read(filepath)
        print(f"\n📄 基本信息:")
        print(f"  Title: {doc.title}")
        print(f"  DOI: {doc.doi}")
        print(f"  Pages: {doc.total_pages}")
        print(f"  Chunks: {len(doc.chunks)}")

        # === 第二步：展示 Abstract ===
        abstract = doc.metadata.get("abstract", "")
        print(f"\n📝 Abstract ({len(abstract)} 字):")
        if abstract:
            print(f"  {abstract[:300]}...")
        else:
            print(f"  （无）")

        # === 第三步：展示规则提取的 Keywords ===
        rule_keywords = doc.metadata.get("keywords", [])
        print(f"\n🔑 规则提取 Keywords ({len(rule_keywords)} 个):")
        if rule_keywords:
            for kw in rule_keywords:
                print(f"  ✓ {kw}")
        else:
            print(f"  （无）")

        # === 第四步：LLM 兜底 ===
        print(f"\n🤖 LLM 兜底:")
        extractor = ContentTagExtractor()

        # 判断是否需要 LLM 兜底
        need_llm = len(rule_keywords) < 2 or any(len(kw) > 50 for kw in rule_keywords)
        print(f"  触发条件: rule_keywords={len(rule_keywords)} 个, 超长关键词={any(len(kw) > 50 for kw in rule_keywords)}")
        print(f"  是否触发: {'✅ 是' if need_llm else '❌ 否'}")

        start_time = time.time()
        tags = extractor.extract(doc)
        elapsed = time.time() - start_time

        # 分类结果
        pdf_kw_tags = [t for t in tags if t.source == "pdf_keywords"]
        llm_fallback_tags = [t for t in tags if t.source == "llm_fallback"]
        llm_extracted_tags = [t for t in tags if t.source == "llm_extracted"]

        if llm_fallback_tags:
            total_llm_fallback += 1
            print(f"  ⏱ 耗时: {elapsed:.2f}s")
            print(f"  📌 LLM 兜底结果 ({len(llm_fallback_tags)} 个):")
            for tag in llm_fallback_tags:
                print(f"    → {tag.value} (confidence={tag.confidence}, needs_review={tag.needs_review})")

        if llm_extracted_tags:
            print(f"  📌 LLM 补充提取 ({len(llm_extracted_tags)} 个):")
            for tag in llm_extracted_tags:
                if tag.tag_type == "domain":
                    print(f"    → [domain] {tag.value}")
                elif tag.tag_type == "methodology":
                    print(f"    → [methodology] {tag.value}")

        # === 第五步：最终结果 ===
        final_topics = [t for t in tags if t.tag_type == "topic"]
        print(f"\n✅ 最终 Topics ({len(final_topics)} 个):")
        for tag in final_topics:
            source_icon = "📄" if tag.source == "pdf_keywords" else "🤖"
            review_icon = "⚠️" if tag.needs_review else "✓"
            print(f"  {source_icon} {review_icon} {tag.value} (source={tag.source}, conf={tag.confidence})")

        # 统计
        total_rule_keywords += len(rule_keywords)
        total_final_keywords += len(final_topics)

    except Exception as e:
        print(f"  ❌ 解析失败: {e}")
        import traceback
        traceback.print_exc()

    print()

# === 汇总统计 ===
print(f"\n{'='*100}")
print(f"📊 汇总统计")
print(f"{'='*100}")
print(f"  论文总数: {len(pdf_files)}")
print(f"  规则提取 Keywords 总数: {total_rule_keywords}")
print(f"  LLM 兜底触发次数: {total_llm_fallback}")
print(f"  最终 Topics 总数: {total_final_keywords}")
print(f"  兜底贡献: {total_final_keywords - total_rule_keywords} 个 Topics")
print(f"{'='*100}")
