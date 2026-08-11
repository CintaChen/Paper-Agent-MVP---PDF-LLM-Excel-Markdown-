"""极简 RAG 工具：纯 Python + OpenAI SDK + ChromaDB + pymupdf4llm"""
import os
import sys
import uuid
import re
import argparse
from dotenv import load_dotenv
from openai import OpenAI
import chromadb
import pymupdf4llm


# ========== 配置 ==========

def load_config():
    """加载 .env 配置"""
    load_dotenv()
    return {
        "api_key": os.getenv("API_KEY"),
        "base_url": os.getenv("BASE_URL"),
        "model": os.getenv("MODEL", "Longcat-2.0"),
        "emb_api_key": os.getenv("EMB_API_KEY") or os.getenv("API_KEY"),
        "emb_base_url": os.getenv("EMB_BASE_URL") or os.getenv("BASE_URL"),
        "emb_model": os.getenv("EMB_MODEL", "text-embedding-3-small"),
        "chroma_dir": os.getenv("CHROMA_DB_DIR", "./chroma_db"),
        "collection_name": os.getenv("COLLECTION_NAME", "paper_rag"),
    }


def get_llm_client(cfg):
    """创建 LLM 客户端"""
    return OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])


def get_embedding_client(cfg):
    """创建 Embedding 客户端"""
    return OpenAI(api_key=cfg["emb_api_key"], base_url=cfg["emb_base_url"])


def get_collection(cfg):
    """获取或创建 ChromaDB collection"""
    client = chromadb.PersistentClient(path=cfg["chroma_dir"])
    return client.get_or_create_collection(name=cfg["collection_name"])


# ========== 文本清洗 ==========

def clean_text(text):
    """清洗 PDF 提取的 Markdown 文本"""
    # 删除 soft hyphen
    text = text.replace("\xad", "")
    text = text.replace("­", "")

    # 修复英文断词：例如 "evalu-\nate" → "evaluate"
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    text = re.sub(r"(\w)-\s+(\w)", r"\1\2", text)

    # 压缩多余空白
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 按行处理
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 删除只包含数字的行
        if re.match(r"^[0-9\s\.,;:]+$", line):
            continue
        # 删除只包含标点的行
        if re.match(r"^[\s\W]+$", line):
            continue
        # 删除长度小于 3 的行
        if len(line) < 3:
            continue
        # 删除 HTML 注释（图片文本标记）
        if "<!-- Start of picture text -->" in line:
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def clean_html_tags(text):
    """移除 HTML 标签，保留标签内的文本"""
    return re.sub(r"<[^>]+>", "", text)


def is_figure_caption(text):
    """判断 chunk 是否主要是图注/图表噪声"""
    # 开头是 Figure/FIGURE/Fig./Table/Source，且没有后续完整段落
    if re.match(r"^(Figure|FIGURE|Fig\.|Table|SOURCE|Source)\s", text):
        # 检查是否有后续完整段落（超过 80 个字符的句子）
        lines = text.split("\n")
        # 第一行是图注标题
        remaining = "\n".join(lines[1:]).strip()
        # 如果没有后续内容或后续内容太短
        if len(remaining) < 80:
            return True
        # 如果后续内容也只是短标签
        if all(len(line.strip()) < 20 for line in remaining.split("\n") if line.strip()):
            return True

    # 检查是否包含大量 <br> 标签
    br_count = text.count("<br>")
    if br_count > 5:
        return True

    # 检查是否包含图片文本标记
    if "<!-- Start of picture text -->" in text or "picture text" in text.lower():
        return True

    return False


def has_too_many_short_lines(text, threshold=0.5):
    """检查短行比例是否过高"""
    lines = [line for line in text.split("\n") if line.strip()]
    if not lines:
        return True
    short_lines = sum(1 for line in lines if len(line.strip()) < 15)
    return short_lines / len(lines) > threshold


def is_quality_chunk(text):
    """判断 chunk 是否满足质量标准"""
    # 字符数 >= 120
    if len(text) < 120:
        return False

    # 数字比例 <= 0.2
    digit_count = sum(1 for c in text if c.isdigit())
    if digit_count / len(text) > 0.2:
        return False

    # 字母/汉字比例 >= 0.5
    alpha_count = sum(1 for c in text if c.isalpha())
    chinese_count = sum(1 for c in text if "一" <= c <= "鿿")
    if (alpha_count + chinese_count) / len(text) < 0.5:
        return False

    # 英文单词数 >= 25，或中文汉字数 >= 50
    english_words = len(re.findall(r"[a-zA-Z]+", text))
    if english_words < 25 and chinese_count < 50:
        return False

    # 至少包含 2 个完整句子
    sentences = re.split(r"[.!?。！？]+", text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    if len(sentences) < 2:
        return False

    # 短行比例不能过高
    if has_too_many_short_lines(text):
        return False

    # 不能主要是图注
    if is_figure_caption(text):
        return False

    # 包含图片文本标记的 chunk，除非有足够正文
    if "<!-- Start of picture text -->" in text or "<!--" in text:
        # 需要至少 3 个完整英文句子或 80 个中文汉字
        english_sentences = re.split(r"[.!?]+", text)
        english_sentences = [s.strip() for s in english_sentences if len(s.strip()) > 15]
        if len(english_sentences) < 3 and chinese_count < 80:
            return False

    return True


# ========== Ingest ==========

def extract_chunks_from_pdf(pdf_path):
    """从 PDF 中提取文本块，使用 Markdown 格式保留论文结构。
    返回 [(text, page_num), ...]
    """
    chunks = []

    # 使用 pymupdf4llm 将 PDF 转换为 Markdown
    md_pages = pymupdf4llm.to_markdown(pdf_path, page_chunks=True)

    for page_idx, page_data in enumerate(md_pages):
        page_num = page_idx + 1
        page_text = page_data.get("text", "")

        # 清洗文本
        page_text = clean_text(page_text)

        # 按 Markdown 段落切块
        paragraphs = page_text.split("\n\n")

        for para in paragraphs:
            para = para.strip()
            # 过滤低质量 chunk
            if is_quality_chunk(para):
                chunks.append((para, page_num))

    return chunks


def ingest_pdf(pdf_path, collection, embedding_client, emb_model):
    """处理单个 PDF 文件，将 chunks 存入 ChromaDB"""
    # 提取文本块
    chunks = extract_chunks_from_pdf(pdf_path)

    if not chunks:
        print(f"  [警告] {pdf_path} 没有提取到有效段落")
        return 0

    # 准备数据
    texts = [chunk[0] for chunk in chunks]
    metadatas = [
        {"source": pdf_path, "page": chunk[1]}
        for chunk in chunks
    ]
    ids = [str(uuid.uuid4()) for _ in chunks]

    # 向量化
    try:
        response = embedding_client.embeddings.create(
            model=emb_model,
            input=texts
        )
        embeddings = [item.embedding for item in response.data]
    except Exception as e:
        print(f"  [错误] Embedding 调用失败: {e}")
        print("  可能原因：")
        print("  - 当前 API 服务商可能不支持 embeddings 接口")
        print("  - EMB_MODEL 配置错误")
        print("  建议先运行: python test_embedding.py")
        return 0

    # 存入 ChromaDB
    collection.add(
        documents=texts,
        embeddings=embeddings,
        metadatas=metadatas,
        ids=ids,
    )

    return len(chunks)


def ingest(path, cfg):
    """处理 ingest 命令"""
    collection = get_collection(cfg)
    embedding_client = get_embedding_client(cfg)
    emb_model = cfg["emb_model"]

    # 判断路径类型
    if os.path.isfile(path):
        if not path.lower().endswith(".pdf"):
            print(f"错误：{path} 不是 PDF 文件")
            return
        pdf_files = [path]
    elif os.path.isdir(path):
        pdf_files = [
            os.path.join(path, f)
            for f in os.listdir(path)
            if f.lower().endswith(".pdf")
        ]
        if not pdf_files:
            print(f"错误：{path} 目录下没有找到 PDF 文件")
            return
    else:
        print(f"错误：{path} 不是有效的文件或目录")
        return

    # 处理每个 PDF
    total_chunks = 0
    total_pdfs = 0

    for pdf_path in pdf_files:
        print(f"处理: {pdf_path}")
        num_chunks = ingest_pdf(pdf_path, collection, embedding_client, emb_model)
        if num_chunks > 0:
            total_chunks += num_chunks
            total_pdfs += 1
            print(f"  切了 {num_chunks} 个 chunk")

    print(f"\n完成！处理了 {total_pdfs} 个 PDF，共 {total_chunks} 个 chunk")


# ========== 检索与生成 ==========

def retrieve(query_embedding, collection, n_results=6):
    """从 ChromaDB 检索相似片段"""
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
    )
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]
    return documents, metadatas, distances


def format_context(documents, metadatas, distances):
    """将检索结果格式化为上下文文本"""
    context_parts = []
    for i, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances)):
        source = meta.get("source", "未知")
        page = meta.get("page", "?")
        filename = os.path.basename(source)
        # 清洗 HTML 标签
        cleaned_doc = clean_html_tags(doc)
        context_parts.append(
            f"[片段 {i+1}] 来源: {filename}, 页码: {page}, distance: {dist:.4f}\n"
            f"片段内容: {cleaned_doc}"
        )
    return "\n\n".join(context_parts)


def get_system_prompt(context):
    """生成 System Prompt"""
    return f"""你是一个学术论文分析助手。你只能根据下面编号的参考片段回答问题。

规则：
1. 你只能根据下面编号片段回答。
2. 每个片段格式为：[片段编号] 来源: 文件名, 页码: X
3. 回答中的每个具体结论都必须标注来源，例如：[片段2，第7页]
4. 如果某个结论不能在参考片段中找到明确依据，禁止写出。
5. 不要使用模型已有知识补充。
6. 不要根据论文标题、文件名、期刊名、作者信息推测。
7. 如果片段不足以回答研究方法或实验设计，必须明确写："现有片段不足以判断该论文的研究方法/实验设计。"
8. 输出分为两部分：
   第一部分：可确认结论
   第二部分：无法确认内容
9. 回答使用中文。

参考片段：
{context}"""


def rewrite_query(user_question, chat_history, llm_client, model):
    """根据对话历史重写用户问题，使其适合向量检索"""
    # 如果没有历史，直接返回原问题
    if not chat_history:
        return user_question

    # 构建历史文本
    history_text = ""
    for msg in chat_history:
        role = "用户" if msg["role"] == "user" else "助手"
        history_text += f"{role}: {msg['content']}\n"

    rewrite_prompt = f"""根据以下对话历史，将用户最新问题改写成适合向量数据库检索的完整问题。

要求：
- 根据对话历史补全代词，例如"它""这篇论文""第二篇"等。
- 只输出改写后的问题。
- 不要解释。
- 如果用户问题已经完整，可以原样返回。
- 改写后的问题必须适合用于向量数据库检索。

对话历史：
{history_text}

用户最新问题：{user_question}

改写后的问题："""

    try:
        response = llm_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": rewrite_prompt}],
            temperature=0.0,
            max_tokens=200,
        )
        rewritten = response.choices[0].message.content.strip()
        return rewritten
    except Exception:
        # 重写失败，回退到原问题
        return user_question


# ========== Ask ==========

def ask(question, cfg, debug=False):
    """处理 ask 命令"""
    collection = get_collection(cfg)

    # 检查 collection 是否为空
    if collection.count() == 0:
        print("向量库为空，请先运行 ingest 命令导入论文")
        print("例如: python mini_rag.py ingest input/papers")
        return

    embedding_client = get_embedding_client(cfg)
    emb_model = cfg["emb_model"]

    # 向量化问题
    try:
        response = embedding_client.embeddings.create(
            model=emb_model,
            input=[question]
        )
        query_embedding = response.data[0].embedding
    except Exception as e:
        print(f"[错误] Embedding 调用失败: {e}")
        print("建议先运行: python test_embedding.py")
        return

    # 检索
    documents, metadatas, distances = retrieve(query_embedding, collection, n_results=6)

    # 格式化上下文
    context = format_context(documents, metadatas, distances)

    # 调用 LLM 生成回答
    llm_client = get_llm_client(cfg)
    model = cfg["model"]
    system_prompt = get_system_prompt(context)

    # 调试模式：打印完整 Prompt
    if debug:
        print("\n" + "=" * 60)
        print("【调试模式】完整 Prompt：")
        print("=" * 60)
        print(system_prompt)
        print(f"\n问题：{question}")
        print("=" * 60)
        print()

    try:
        response = llm_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=0.0,
            max_tokens=4096,
        )
        answer = response.choices[0].message.content
    except Exception as e:
        print(f"[错误] LLM 调用失败: {e}")
        return

    # 输出结果
    print("\n" + "=" * 50)
    print("回答：")
    print("=" * 50)
    print(answer)
    print()
    print("=" * 50)
    print("检索到的片段：")
    print("=" * 50)
    for i, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances)):
        source = meta.get("source", "未知")
        page = meta.get("page", "?")
        print(f"\n[片段 {i+1}] 来源: {os.path.basename(source)}, 第 {page} 页, distance: {dist:.4f}")
        print(f"{doc[:300]}..." if len(doc) > 300 else doc)


# ========== Chat（多轮对话） ==========

def chat(cfg):
    """处理 chat 命令：进入多轮对话模式"""
    collection = get_collection(cfg)

    # 检查 collection 是否为空
    if collection.count() == 0:
        print("向量库为空，请先运行 ingest 命令导入论文")
        print("例如: python mini_rag.py ingest input/papers")
        return

    embedding_client = get_embedding_client(cfg)
    llm_client = get_llm_client(cfg)
    emb_model = cfg["emb_model"]
    model = cfg["model"]

    # 短期对话记忆，最多保留 6 条消息（3 轮对话）
    chat_history = []

    print("进入多轮对话模式。输入 exit、quit 或 q 退出。")
    print("-" * 50)

    while True:
        # 获取用户输入
        user_input = input("\nYou: ").strip()

        # 检查退出命令
        if user_input.lower() in ("exit", "quit", "q"):
            print("退出对话模式。")
            break

        # 跳过空输入
        if not user_input:
            continue

        # ========== 查询重写 ==========
        rewritten_query = rewrite_query(user_input, chat_history, llm_client, model)
        if rewritten_query != user_input:
            print(f"[系统] 检索词已重写为：{rewritten_query}")

        # ========== 检索 ==========
        try:
            response = embedding_client.embeddings.create(
                model=emb_model,
                input=[rewritten_query]
            )
            query_embedding = response.data[0].embedding
        except Exception as e:
            print(f"[错误] Embedding 调用失败: {e}")
            continue

        documents, metadatas, distances = retrieve(query_embedding, collection, n_results=6)
        context = format_context(documents, metadatas, distances)

        # ========== 生成回答 ==========
        system_prompt = get_system_prompt(context)

        # 构建 messages：system + 历史对话 + 当前问题
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(chat_history)
        messages.append({"role": "user", "content": user_input})

        try:
            response = llm_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.0,
                max_tokens=4096,
            )
            answer = response.choices[0].message.content
        except Exception as e:
            print(f"[错误] LLM 调用失败: {e}")
            continue

        # 输出回答
        print(f"\nAgent: {answer}")

        # ========== 更新对话历史 ==========
        chat_history.append({"role": "user", "content": user_input})
        chat_history.append({"role": "assistant", "content": answer})

        # 最多保留 6 条消息（3 轮对话）
        if len(chat_history) > 6:
            chat_history = chat_history[-6:]


# ========== Reset ==========

def reset(cfg):
    """处理 reset 命令"""
    chroma_dir = cfg["chroma_dir"]
    collection_name = cfg["collection_name"]

    client = chromadb.PersistentClient(path=chroma_dir)

    # 获取所有 collection 列表
    collections = client.list_collections()
    collection_names = [c.name for c in collections]

    if collection_name in collection_names:
        client.delete_collection(name=collection_name)
        print("已清空本地向量库")
    else:
        print("已清空本地向量库")


# ========== Main ==========

def main():
    parser = argparse.ArgumentParser(description="极简 RAG 工具")
    subparsers = parser.add_subparsers(dest="command")

    # ingest 子命令
    ingest_parser = subparsers.add_parser("ingest", help="导入 PDF 到向量库")
    ingest_parser.add_argument("path", help="PDF 文件路径或目录路径")

    # ask 子命令
    ask_parser = subparsers.add_parser("ask", help="提问")
    ask_parser.add_argument("question", help="问题")
    ask_parser.add_argument("--debug", action="store_true", help="调试模式：打印完整 Prompt")

    # chat 子命令（多轮对话）
    subparsers.add_parser("chat", help="进入多轮对话模式")

    # reset 子命令
    subparsers.add_parser("reset", help="清空向量库")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    cfg = load_config()

    if args.command == "ingest":
        ingest(args.path, cfg)
    elif args.command == "ask":
        ask(args.question, cfg, debug=args.debug)
    elif args.command == "chat":
        chat(cfg)
    elif args.command == "reset":
        reset(cfg)


if __name__ == "__main__":
    # 打印重新入库提醒
    print("提示：如果刚修改了切块或清洗逻辑，请先运行 python mini_rag.py reset，再重新 ingest。\n")
    main()
