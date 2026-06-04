from g_chan.chat.base import ChatMessage
from g_chan.prompts import build_batch_user_message


def _msg(user: str, body: str) -> ChatMessage:
    return ChatMessage(user=user, body=body, raw=f"@G酱 {body}")


def test_builds_numbered_list_of_messages():
    msgs = [
        _msg("alice", "你今天玩了啥"),
        _msg("bob", "笨蛋"),
        _msg("charlie", "哈哈"),
    ]
    out = build_batch_user_message(msgs)
    assert "[1] alice: 你今天玩了啥" in out
    assert "[2] bob: 笨蛋" in out
    assert "[3] charlie: 哈哈" in out


def test_template_var_messages_is_substituted():
    """{{messages}} 占位符必须被替换 — 不能在最终文本里残留 {{...}}。"""
    msgs = [_msg("alice", "嗨")]
    out = build_batch_user_message(msgs)
    assert "{{messages}}" not in out
    assert "{{" not in out
    assert "alice" in out


def test_empty_list_still_returns_valid_string():
    """空 buffer 仍返回合法 string(不崩),且不残留 {{messages}}。"""
    out = build_batch_user_message([])
    assert isinstance(out, str)
    assert len(out) > 0
    assert "{{messages}}" not in out
