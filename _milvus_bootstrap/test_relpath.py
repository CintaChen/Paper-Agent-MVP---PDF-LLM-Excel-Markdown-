# -*- coding: utf-8 -*-
"""
演示：相对路径到底相对谁解析。

用法（在 E:/kunxuesuo/agent 下，再从别的目录各跑一次）：
    .venv\\Scripts\\python.exe _milvus_bootstrap\\test_relpath.py

本脚本自建一个模拟 Settings（不 mkdir、不碰你的真实配置），
用来对比三种写法在不同工作目录下的解析结果。
"""
import os
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 模拟「项目根目录」：config/ 的上一级
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class NaiveSettings(BaseSettings):
    """写法 A：直接写相对路径（你现在的做法）"""
    model_config = SettingsConfigDict(extra="ignore")
    milvus_uri: str = "storage_data/milvus.db"
    storage_dir: Path = Path("./storage_data")


class SmartSettings(BaseSettings):
    """写法 B：相对路径统一按项目根目录解析（推荐）"""
    model_config = SettingsConfigDict(extra="ignore")
    milvus_uri: str = "storage_data/milvus.db"
    storage_dir: Path = Path("./storage_data")

    @field_validator("milvus_uri")
    @classmethod
    def _to_abs(cls, v):
        p = Path(v)
        return str(p if p.is_absolute() else (PROJECT_ROOT / p).resolve())

    @field_validator("storage_dir")
    @classmethod
    def _to_abs_dir(cls, v):
        p = Path(v)
        return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()


def show():
    cwd = Path(os.getcwd()).resolve()
    print(f"  当前工作目录 (CWD) : {cwd}")
    print(f"  项目根目录         : {PROJECT_ROOT}")
    print()
    print(f"  {'':<16}{'写法A（你现在的）':<46}{'写法B（推荐）'}")
    print("  " + "-" * 92)

    n, s = NaiveSettings(), SmartSettings()

    for label, key in [("milvus_uri", "milvus_uri"), ("storage_dir", "storage_dir")]:
        a, b = getattr(n, key), getattr(s, key)
        a_ok = "正确" if str(Path(a).resolve()).startswith(str(PROJECT_ROOT)) else "跑偏"
        b_ok = "正确" if str(Path(b).resolve()).startswith(str(PROJECT_ROOT)) else "跑偏"
        print(f"  {label:<16}{str(a):<46}{str(b)}")
        print(f"  {'':<16}{'-> ' + a_ok:<46}{'-> ' + b_ok}")

    print()
    print("  storage_dir 解析为绝对路径后：")
    print(f"    写法A: {Path(n.storage_dir).resolve()}")
    print(f"    写法B: {Path(s.storage_dir).resolve()}")


if __name__ == "__main__":
    print("=" * 94)
    print("相对路径解析对比")
    print("=" * 94)
    show()
    print()
    print("=" * 94)
    print("结论：")
    print("  从项目根目录跑，两种写法一致；")
    print("  从别的目录跑，写法 A 会把数据写到那个目录下（跑偏），写法 B 始终落在项目内。")
    print("=" * 94)
