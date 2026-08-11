"""极简 RAG 测试脚本：测试 Embedding API 是否可用"""
import os
import sys
from dotenv import load_dotenv
from openai import OpenAI


def get_embedding_client():
    """创建 Embedding 客户端。
    如果 .env 中配置了 EMB_API_KEY 和 EMB_BASE_URL，则使用它们；
    否则复用 API_KEY 和 BASE_URL。
    """
    load_dotenv()

    emb_api_key = os.getenv("EMB_API_KEY") or os.getenv("API_KEY")
    emb_base_url = os.getenv("EMB_BASE_URL") or os.getenv("BASE_URL")

    if not emb_api_key:
        print("错误：未配置 API_KEY 或 EMB_API_KEY")
        sys.exit(1)

    return OpenAI(api_key=emb_api_key, base_url=emb_base_url)


def test_embedding():
    """测试 Embedding API"""
    client = get_embedding_client()
    emb_model = os.getenv("EMB_MODEL", "text-embedding-3-small")

    # 测试文本
    test_text = "这篇论文研究了人工智能对企业绿色转型的影响。"

    print(f"测试 Embedding 模型: {emb_model}")
    print(f"测试文本: {test_text}")
    print("-" * 50)

    try:
        response = client.embeddings.create(
            model=emb_model,
            input=[test_text]
        )
        embedding = response.data[0].embedding

        print(f"Embedding 成功！")
        print(f"向量长度: {len(embedding)}")
        print(f"前 10 个数值: {embedding[:10]}")

    except Exception as e:
        print(f"Embedding 调用失败: {e}")
        print()
        print("可能的原因：")
        print("1. 当前 API 服务商可能不支持 embeddings 接口")
        print("2. EMB_MODEL 配置错误，请确认模型名称正确")
        print("3. API Key 没有 embedding 权限")
        print()
        print("排查建议：")
        print("- 检查 .env 中的 EMB_MODEL 是否正确")
        print("- 尝试单独配置支持 embedding 的 API（如 OpenAI 官方）")
        print("- 查看 API 服务商文档确认是否支持 embeddings")


if __name__ == "__main__":
    test_embedding()
