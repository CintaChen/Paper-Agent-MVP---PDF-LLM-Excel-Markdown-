"""生成标签提取验收检查表"""
import os
import sys

if "PYTHONPATH" in os.environ:
    del os.environ["PYTHONPATH"]
sys.path = [p for p in sys.path if "hermes" not in p]
sys.path.insert(0, ".")

from pathlib import Path
from readers.pdf_reader import PDFReader
from rag.tag_extractor import ContentTagExtractor

pdf_dir = Path("input/papers")
pdf_files = sorted(pdf_dir.glob("*.pdf"))

reader = PDFReader()
extractor = ContentTagExtractor()

results = []

for i, pdf_path in enumerate(pdf_files, 1):
    doc = reader.read(str(pdf_path))
    tags = extractor.extract(doc)

    domains = [t for t in tags if t.tag_type == "domain"]
    topics = [t for t in tags if t.tag_type == "topic"]
    methods = [t for t in tags if t.tag_type == "methodology"]
    review = [t for t in tags if t.needs_review]

    results.append({
        "index": i,
        "name": pdf_path.name,
        "title": doc.title,
        "domains": domains,
        "topics": topics,
        "methods": methods,
        "review": review,
        "total": len(tags),
    })

# 生成验收报告
lines = []
lines.append("# 标签提取验收检查表\n")
lines.append(f"> 生成时间: 2026-09-07\n")
lines.append(f"> 论文总数: {len(results)}\n")
lines.append("\n---\n")

lines.append("## 验收标准\n")
lines.append("| 编号 | 检查项 | 标准 |")
lines.append("|------|--------|------|")
lines.append("| AC1 | domain | 领域判断是否准确？ |")
lines.append("| AC2 | topics | 主题是否覆盖核心内容？2-5 个是否合理？ |")
lines.append("| AC3 | methodologies | 方法是否真实存在于论文中？ |")
lines.append("| AC4 | evidence | 原文摘录是否真实存在？ |")
lines.append("| AC5 | confidence | 是否与你的主观判断一致？ |")
lines.append("| AC6 | needs_review | 证据不足的论文是否被正确标记？ |")

lines.append("\n---\n")

for r in results:
    lines.append(f"\n## [{r['index']}] {r['name']}\n")
    lines.append(f"**标题:** {r['title']}\n")
    lines.append(f"**标签总数:** {r['total']}\n")

    # domain
    lines.append(f"\n### AC1: domain（领域）\n")
    if r["domains"]:
        for d in r["domains"]:
            lines.append(f"- **{d.value}** (置信度: {d.confidence}, 来源: {d.source})")
            if d.evidence:
                lines.append(f"  - 证据: *{d.evidence}*")
    else:
        lines.append("- ⚠️ 无领域标签")
    lines.append(f"\n**验收:** □ 准确  □ 不准确  □ 需修正")

    # topics
    lines.append(f"\n### AC2: topics（主题）\n")
    if r["domains"]:
        for t in r["topics"]:
            lines.append(f"- **{t.value}** (来源: {t.source})")
            if t.evidence and t.evidence != "论文自带关键词":
                lines.append(f"  - 证据: *{t.evidence}*")
    else:
        lines.append("- ⚠️ 无主题标签")
    lines.append(f"\n数量: {len(r['topics'])} 个  **验收:** □ 覆盖合理  □ 偏多  □ 偏少  □ 需修正")

    # methodologies
    lines.append(f"\n### AC3: methodologies（方法论）\n")
    if r["methods"]:
        for m in r["methods"]:
            lines.append(f"- **{m.value}** (置信度: {m.confidence}, 来源: {m.source})")
            if m.evidence:
                lines.append(f"  - 证据: *{m.evidence}*")
    else:
        lines.append("- ⚠️ 无方法论标签")
    lines.append(f"\n**验收:** □ 真实存在  □ 存疑  □ 需修正")

    # evidence
    lines.append(f"\n### AC4: evidence（证据）\n")
    has_evidence = any(t.evidence for t in r["domains"] + r["methods"])
    no_evidence = [t for t in r["domains"] + r["methods"] if not t.evidence]
    if has_evidence:
        lines.append(f"- ✅ 部分标签有证据")
    if no_evidence:
        lines.append(f"- ⚠️ 以下标签缺证据: {', '.join([t.value for t in no_evidence])}")
    lines.append(f"\n**验收:** □ 真实存在  □ 部分存疑  □ 需补充")

    # confidence
    lines.append(f"\n### AC5: confidence（置信度）\n")
    for t in r["domains"] + r["methods"]:
        lines.append(f"- {t.value}: {t.confidence:.1f}")
    lines.append(f"\n**验收:** □ 一致  □ 偏高  □ 偏低  □ 需修正")

    # needs_review
    lines.append(f"\n### AC6: needs_review（需确认）\n")
    if r["review"]:
        for t in r["review"]:
            lines.append(f"- ⚠️ {t.value} ({t.tag_type})")
    else:
        lines.append("- ✅ 无需要确认的标签")
    lines.append(f"\n**验收:** □ 标记正确  □ 应标记未标记  □ 不应标记但标记了")

    lines.append(f"\n---\n")

# 汇总
lines.append("## 验收汇总\n")
lines.append("| 论文 | domain | topics | methodologies | evidence | confidence | needs_review |")
lines.append("|------|--------|--------|----------------|----------|------------|--------------|")
for r in results:
    lines.append(f"| {r['name'][:20]}... | □ | □ | □ | □ | □ | □ |")

lines.append(f"\n\n**验收人:** ________________  \n**验收日期:** ________________\n")

content = "\n".join(lines)
with open("docs/TAG_EVALUATION.md", "w", encoding="utf-8") as f:
    f.write(content)

print(f"已生成: docs/TAG_EVALUATION.md")
print(f"论文数: {len(results)}")
