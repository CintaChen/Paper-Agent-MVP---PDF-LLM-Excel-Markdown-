"""Paper Agent - Main entry point."""
from config import Config
from processors.paper_analyzer import PaperAnalyzer
from processors.output_writer import OutputWriter

results = []
review_items = []  # 待人工确认的论文


def main():
    global results, review_items
    config = Config()
    analyzer = PaperAnalyzer(config)
    writer = OutputWriter(config)

    papers = analyzer.discover_papers()
    total = len(papers)
    for i, paper in enumerate(papers, 1):
        print(f"[{i}/{total}] 正在处理: {paper['title']}")
        result, needs_review, review_reasons = analyzer.analyze(paper)
        if needs_review:
            review_items.append((result, review_reasons))
            print(f"  ⚠ 待确认: {', '.join(review_reasons)}")
        results.append(result)

    # 输出正常结果
    writer.write_all(results)

    # 输出人工确认清单
    writer.write_review_list(review_items)

    # 打印汇总
    print(f"\n处理完成：{len(results)} 篇论文")
    print(f"  - 正常输出：{len(results) - len(review_items)} 篇")
    print(f"  - 待人工确认：{len(review_items)} 篇")


if __name__ == "__main__":
    main()
