"""文档管理路由"""
from fastapi import APIRouter, HTTPException

router = APIRouter()

_metadata_store = None


def get_metadata_store():
    """惰性单例：导入本模块不打开 SQLite"""
    global _metadata_store
    if _metadata_store is None:
        from storage.metadata_store import SQLiteStore

        _metadata_store = SQLiteStore()
    return _metadata_store


@router.get("")
async def list_documents(page: int = 1, page_size: int = 20, search: str = None):
    """列出所有文档"""
    docs = get_metadata_store().list_documents()

    if search:
        docs = [d for d in docs if search.lower() in d.title.lower()]

    total = len(docs)
    start = (page - 1) * page_size
    end = start + page_size
    paged_docs = docs[start:end]

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "documents": [
                {
                    "id": d.id,
                    "title": d.title,
                    "authors": d.authors,
                    "year": d.year,
                    "journal": d.journal,
                    "doi": d.doi,
                    "total_pages": d.total_pages,
                    "chunk_count": len(d.chunks),
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                }
                for d in paged_docs
            ],
        },
    }


@router.get("/stats")
async def document_stats():
    """文档统计"""
    docs = get_metadata_store().list_documents()
    total_chunks = sum(len(d.chunks) for d in docs)
    total_pages = sum(d.total_pages for d in docs)

    return {
        "status": "success",
        "data": {
            "total_documents": len(docs),
            "total_chunks": total_chunks,
            "total_pages": total_pages,
        },
    }


@router.get("/{doc_id}")
async def get_document(doc_id: str):
    """获取单个文档"""
    doc = get_metadata_store().get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    return {
        "status": "success",
        "data": {
            "id": doc.id,
            "title": doc.title,
            "authors": doc.authors,
            "year": doc.year,
            "journal": doc.journal,
            "doi": doc.doi,
            "file_path": doc.file_path,
            "total_pages": doc.total_pages,
            "chunks": [
                {
                    "id": c.id,
                    "text": c.text,
                    "page": c.page,
                }
                for c in doc.chunks
            ],
        },
    }


@router.delete("/{doc_id}")
async def delete_document(doc_id: str):
    """删除文档"""
    doc = get_metadata_store().get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    get_metadata_store().delete_document(doc_id)
    return {"status": "success", "message": "文档已删除"}
