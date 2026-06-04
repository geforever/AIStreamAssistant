"""程序定义的 prompt 契约 — 跟 LLM 输出 schema、解析逻辑强绑定。

注意: 这跟项目根目录的 `prompts/` 不是一回事。
- `prompts/default.md` 是用户(主播)可编辑的角色性格定义
- `src/g_chan/prompts/` 是开发者维护的程序契约
"""
from g_chan.prompts.batch import build_batch_user_message
from g_chan.prompts.output_rules import OUTPUT_RULES

__all__ = ["OUTPUT_RULES", "build_batch_user_message"]
