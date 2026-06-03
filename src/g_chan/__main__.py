"""g_chan 入口 — python -m g_chan。"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from g_chan.chat.twitch import TwitchChatAdapter
from g_chan.config import load_config
from g_chan.llm.factory import create_provider
from g_chan.logging_setup import setup_logging
from g_chan.orchestrator import Orchestrator
from g_chan.persona.loader import PersonaLoader
from g_chan.persona.stream_context import StreamContextProvider, TwitchHelixClient

log = logging.getLogger("g_chan")


async def amain() -> int:
    cfg_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config.yaml")
    cfg = load_config(cfg_path)
    setup_logging(level=cfg.logging.level, file=cfg.logging.file)

    log.info("starting G酱 — channel=#%s provider=%s",
             cfg.twitch.channel, cfg.llm.provider)

    chat = TwitchChatAdapter(
        channel=cfg.twitch.channel,
        bot_username=cfg.twitch.bot_username,
        oauth_token=cfg.twitch.oauth_token,
        trigger=cfg.twitch.trigger,
    )

    llm = create_provider(cfg.llm)

    persona = PersonaLoader(
        base_path=cfg.persona.prompt_file,
        output_format_path="prompts/output_format.md",
        include_stream_context=cfg.persona.include_stream_context,
    )

    sctx: StreamContextProvider | _NullStreamCtx
    polling: asyncio.Task | None = None
    if cfg.persona.include_stream_context:
        helix = TwitchHelixClient(
            client_id=cfg.twitch.client_id,
            client_secret=cfg.twitch.client_secret,
        )
        sctx = StreamContextProvider(channel=cfg.twitch.channel, helix=helix)
    else:
        log.info("stream_context disabled — skipping Helix polling")
        sctx = _NullStreamCtx()

    orch = Orchestrator(
        chat=chat, llm=llm, persona=persona, stream_ctx=sctx,
        rate_limit_ms=cfg.rate_limit.global_window_ms,
        busy_reply=cfg.rate_limit.busy_reply,
    )
    orch.wire()

    if isinstance(sctx, StreamContextProvider):
        polling = asyncio.create_task(
            sctx.start_polling(cfg.stream_context.poll_interval_ms)
        )
    try:
        await chat.connect()
        log.info("ready — listening for %s in #%s",
                 cfg.twitch.trigger, cfg.twitch.channel)
        # twitchio.Client.connect() 已是阻塞;此处等其结束
    except KeyboardInterrupt:
        log.info("shutting down")
    finally:
        if polling is not None:
            polling.cancel()
        await chat.disconnect()
    return 0


class _NullStreamCtx:
    """include_stream_context=False 时的空实现 — 满足 StreamCtxLike Protocol。"""
    def current(self) -> None:
        return None


def main() -> int:
    try:
        return asyncio.run(amain())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
