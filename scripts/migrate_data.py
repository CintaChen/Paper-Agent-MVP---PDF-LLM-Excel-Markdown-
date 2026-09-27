"""数据迁移脚本：从旧项目导入数据"""
import argparse
import json
from pathlib import Path
from config.logging import setup_logging

logger = setup_logging(__name__)


def migrate_from_old_paper_agent(old_output_dir: str, new_storage_dir: str):
    """从旧 paper_agent 的输出目录迁移数据"""
    old_path = Path(old_output_dir)
    if not old_path.exists():
        logger.error(f"旧数据目录不存在: {old_path}")
        return

    # 读取旧的 JSON 输出
    json_files = list(old_path.glob("*.json"))
    logger.info(f"发现 {len(json_files)} 个 JSON 文件")

    # TODO: 实现数据迁移逻辑
    # 1. 读取旧 JSON
    # 2. 转换为新的 Document 格式
    # 3. 保存到新的存储

    logger.info("数据迁移完成")


def main():
    parser = argparse.ArgumentParser(description="数据迁移工具")
    parser.add_argument("--from", dest="old_dir", required=True, help="旧数据目录")
    parser.add_argument("--to", dest="new_dir", required=True, help="新存储目录")
    args = parser.parse_args()

    migrate_from_old_paper_agent(args.old_dir, args.new_dir)


if __name__ == "__main__":
    main()
