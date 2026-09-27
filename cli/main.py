"""CLI 入口"""
import argparse
import sys
from pathlib import Path
from config.logging import setup_logging

logger = setup_logging(__name__)


def cmd_ingest(args):
    """导入命令"""
    from rag.ingest import IngestPipeline

    pipeline = IngestPipeline()

    if args.reset:
        pipeline.reset()
        logger.info("已清空数据（向量 / 关键词 / 元数据）")

    if args.retry:
        docs = pipeline.retry_failed()
        print(f"重试完成: {len(docs)} 篇成功")
        return

    # --reset / --retry 可单独使用，此时 path 可省略
    if not args.path:
        if not args.reset:
            logger.error(
                "请提供 PDF 文件或目录路径"
                "（若只想重试失败项，请加 --retry）"
            )
        return

    path = Path(args.path)
    if path.is_file():
        pipeline.ingest(str(path), force=args.force)
    elif path.is_dir():
        pipeline.ingest_directory(str(path), force=args.force)
    else:
        logger.error(f"路径不存在: {path}")


def cmd_ask(args):
    """提问命令"""
    from rag.retrieve import HybridRetriever

    retriever = HybridRetriever()
    results = retriever.retrieve(args.question, top_k=args.top_k)

    print(f"\n检索到 {len(results)} 个相关片段:\n")
    for i, result in enumerate(results, 1):
        doc_title = result.chunk.metadata.get("doc_title", "未知文献")
        page = result.chunk.page
        print(f"[{i}] 来源: {doc_title}, 第 {page} 页, 分数: {result.score:.4f}")
        print(f"    {result.chunk.text[:200]}...")
        print()


def cmd_analyze(args):
    """分析命令"""
    from agent.writing_agent import WritingAgent

    agent = WritingAgent()

    if args.mode == "outline":
        response = agent.generate_outline(
            topic=args.topic,
            context_query=args.query,
            top_k=args.top_k,
        )
    elif args.mode == "paragraph":
        response = agent.polish_paragraph(
            topic=args.topic,
            draft=args.draft or "",
            context_query=args.query,
            top_k=args.top_k,
        )
    else:
        logger.error(f"未知模式: {args.mode}")
        return

    print(response)


def cmd_style(args):
    """风格优化命令"""
    from agent.style_agent import StyleAgent

    agent = StyleAgent()

    if args.mode == "polish":
        response = agent.polish(args.text)
    elif args.mode == "simplify":
        response = agent.simplify(args.text)
    elif args.mode == "academic":
        response = agent.improve_academic_style(args.text)
    else:
        logger.error(f"未知模式: {args.mode}")
        return

    print(response)


def main():
    parser = argparse.ArgumentParser(description="论文辅助 Agent 系统")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # ingest 子命令
    ingest_parser = subparsers.add_parser("ingest", help="导入 PDF 论文")
    ingest_parser.add_argument(
        "path",
        nargs="?",
        help="PDF 文件路径或目录路径（--reset / --retry 时可省略）",
    )
    ingest_parser.add_argument(
        "--reset", action="store_true", help="清空现有数据（向量 / 关键词 / 元数据）"
    )
    ingest_parser.add_argument(
        "--force", action="store_true", help="强制重新导入（忽略断点续传）"
    )
    ingest_parser.add_argument(
        "--retry", action="store_true", help="重试导入失败的论文"
    )

    # ask 子命令
    ask_parser = subparsers.add_parser("ask", help="提问")
    ask_parser.add_argument("question", help="问题")
    ask_parser.add_argument(
        "--top-k", type=int, default=5, help="返回结果数量"
    )

    # analyze 子命令
    analyze_parser = subparsers.add_parser("analyze", help="论文分析")
    analyze_parser.add_argument(
        "mode", choices=["outline", "paragraph"], help="分析模式"
    )
    analyze_parser.add_argument("--topic", required=True, help="主题")
    analyze_parser.add_argument("--query", help="检索查询词")
    analyze_parser.add_argument("--draft", help="草稿内容")
    analyze_parser.add_argument(
        "--top-k", type=int, default=5, help="检索文献数量"
    )

    # style 子命令
    style_parser = subparsers.add_parser("style", help="行文风格优化")
    style_parser.add_argument(
        "mode",
        choices=["polish", "simplify", "academic"],
        help="优化模式",
    )
    style_parser.add_argument("text", help="待优化文本")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "ingest":
        cmd_ingest(args)
    elif args.command == "ask":
        cmd_ask(args)
    elif args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "style":
        cmd_style(args)


if __name__ == "__main__":
    main()
