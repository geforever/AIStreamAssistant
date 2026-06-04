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


def test_includes_instructions_in_message():
    msgs = [_msg("alice", "嗨")]
    out = build_batch_user_message(msgs)
    # 包含挑选 / 沉默 / 不要@ 这些关键指令
    assert "挑选" in out
    assert "沉默" in out
    assert "@user" in out  # 提到不要在 text 里 @user


def test_empty_list_still_returns_valid_string():
    out = build_batch_user_message([])
    assert isinstance(out, str)
    assert len(out) > 0
