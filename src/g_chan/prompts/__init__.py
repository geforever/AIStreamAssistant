"""程序定义的 prompt 契约。"""
from g_chan.prompts.batch import build_batch_user_message
from g_chan.prompts.output_rules import render_output_rules

__all__ = ["build_batch_user_message", "render_output_rules"]
