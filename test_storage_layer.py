"""验证存储层基础功能"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.document import Document, Chunk
from storage.keyword_store import BM25Store
from storage.metadata_store import SQLiteStore


def test_bm25_store():
    """测试 BM25 存储"""
    print("=" * 50)
    print("测试 BM25 关键词存储")
    print("=" * 50)

    # 创建测试 chunks
    chunks = [
        Chunk(
            id=f"chunk_{i}",
            text=text,
            page=i + 1,
            metadata={"doc_id": "doc_1", "source": "test.pdf"},
        )
        for i, text in enumerate([
            "人工智能在教育中的应用研究",
            "深度学习技术改变了教学方式",
            "机器学习算法可以预测学生表现",
            "自然语言处理在教育问答系统中应用",
            "计算机视觉技术辅助在线考试监考",
            "AI 智能辅导系统提供个性化学习路径",
            "教育数据挖掘分析学生学习行为",
            "强化学习优化教学资源配置",
        ])
    ]

    # 构建索引
    store = BM25Store()
    store.build_index(chunks)
    print(f"✓ 索引构建完成: {store.total_docs} 个文档")

    # 搜索测试
    query = "人工智能教育"
    results = store.search(query, top_k=3)
    print(f"✓ 搜索 '{query}': {len(results)} 个结果")
    for r in results:
        print(f"  - [{r.rank}] 分数: {r.score:.4f} | {r.chunk.text[:30]}...")

    # 保存/加载测试
    store.save_index("./storage_data/test_bm25.json")
    print("✓ 索引保存完成")

    store2 = BM25Store()
    store2.load_index("./storage_data/test_bm25.json")
    print(f"✓ 索引加载完成: {store2.total_docs} 个文档")

    # 中文搜索
    query2 = "学习"
    results2 = store2.search(query2, top_k=5)
    print(f"✓ 搜索 '{query2}': {len(results2)} 个结果")

    # 清理
    store.reset()
    print("✓ BM25 存储测试通过\n")


def test_sqlite_store():
    """测试 SQLite 存储"""
    print("=" * 50)
    print("测试 SQLite 元数据存储")
    print("=" * 50)

    # 创建测试文档
    chunks = [
        Chunk(
            id=f"doc_1_chunk_{i}",
            text=f"这是第 {i} 段内容。",
            page=i + 1,
            metadata={"doc_id": "doc_1"},
        )
        for i in range(3)
    ]

    doc = Document(
        id="doc_1",
        title="测试论文标题",
        authors=["张三", "李四"],
        year="2024",
        journal="计算机学报",
        doi="10.1234/test",
        file_path="./test.pdf",
        total_pages=10,
        chunks=chunks,
    )

    # 保存文档
    store = SQLiteStore(db_path="./storage_data/test_metadata.db")
    store.save_document(doc)
    print("✓ 文档保存完成")

    # 读取文档
    retrieved = store.get_document("doc_1")
    assert retrieved.title == "测试论文标题"
    assert len(retrieved.chunks) == 3
    print(f"✓ 文档读取完成: {retrieved.title} ({len(retrieved.chunks)} chunks)")

    # 列出所有文档
    docs = store.list_documents()
    print(f"✓ 列出文档: {len(docs)} 篇")

    # 按元数据搜索
    results = store.search_by_metadata(year="2024")
    print(f"✓ 按年份搜索: {len(results)} 篇")

    # 删除文档
    store.delete_document("doc_1")
    docs_after = store.list_documents()
    assert len(docs_after) == 0
    print("✓ 文档删除完成")

    store.close()
    print("✓ SQLite 存储测试通过\n")


def test_document_model():
    """测试数据模型"""
    print("=" * 50)
    print("测试数据模型")
    print("=" * 50)

    # 测试 Chunk
    chunk = Chunk(id="test_1", text="测试文本", page=1, metadata={"key": "value"})
    assert chunk.id == "test_1"
    print("✓ Chunk 模型正常")

    # 测试 Document
    doc = Document(
        id="doc_test",
        title="测试文档",
        authors=["作者1"],
        year="2024",
        chunks=[chunk],
    )
    assert doc.total_pages == 0
    print("✓ Document 模型正常")

    # 测试 SearchResult
    from core.document import SearchResult
    result = SearchResult(chunk=chunk, score=0.95, source="bm25", rank=1)
    assert result.score == 0.95
    print("✓ SearchResult 模型正常")

    print("✓ 数据模型测试通过\n")


if __name__ == "__main__":
    # 确保目录存在
    os.makedirs("./storage_data", exist_ok=True)

    try:
        test_document_model()
        test_bm25_store()
        test_sqlite_store()
        print("=" * 50)
        print("所有存储层测试通过！")
        print("=" * 50)
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
