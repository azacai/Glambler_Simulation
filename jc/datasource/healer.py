"""LLM spec 自愈（v0.2 实现，本文件为占位与设计契约）。

流程：
1. specio 抛出 SpecError（HTTP 403 / 成功判据失败 / 字段大面积缺失）；
2. healer 携带 旧 spec + 错误上下文 + data/last_onsale.json 原始报文
   （或官方页面 JS 源码），调用 OpenAI 兼容端点（config.LLM_*）；
3. 模型产出新 spec JSON（结构需通过本地 schema 校验）；
4. 写入 specs/ 待人工确认后替换生效——LLM 只生成候选，不自动上线。
"""

from __future__ import annotations


class SpecHealer:
    def __init__(self) -> None:
        raise NotImplementedError("v0.2 交付：见 docs/00-框架设计方案.md D12")
