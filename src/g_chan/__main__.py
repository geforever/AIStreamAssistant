"""g_chan 入口 — python -m g_chan。"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from g_chan.chat.twitch import TwitchChatAdapter
from g_chan.config import load_config
from g_chan.live2d.model_loader import (
    Live2DModel,
    discover_model_path,
    load_model_info,
)
from g_chan.llm.factory import create_provider
from g_chan.logging_setup import setup_logging
from g_chan.orchestrator import Orchestrator
from g_chan.persona.loader import PersonaLoader
from g_chan.persona.stream_context import StreamContextProvider, TwitchHelixClient
from g_chan.prompts import render_output_rules
from g_chan.tts.edge import EdgeTTSEngine
from g_chan.tts.file_sink import FileAudioSink

log = logging.getLogger("g_chan")


def _load_live2d_model(model_path_str: str) -> Live2DModel:
    """根据 config.live2d.model_path 加载模型。空字符串 → auto-detect。"""
    if model_path_str:
        path = Path(model_path_str)
        if not path.exists():
            raise FileNotFoundError(
                f"live2d.model_path does not exist: {path}"
            )
    else:
        path = discover_model_path(Path("Live2D"))
        if path is None:
            raise FileNotFoundError(
                "live2d.enabled=true but no model found. "
                "Either put a .model3.json under Live2D/<folder>/ "
                "or set live2d.model_path explicitly."
            )
    log.info("loading Live2D model: %s", path)
    return load_model_info(path)


async def amain() -> int:
    cfg_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config.yaml")
    cfg = load_config(cfg_path)
    setup_logging(level=cfg.logging.level, file=cfg.logging.file)

    # Live2D 模型(可选)
    live2d_model: Live2DModel | None = None
    if cfg.live2d.enabled:
        live2d_model = _load_live2d_model(cfg.live2d.model_path)
        log.info(
            "live2d enabled — expressions=%d motions=%d",
            len(live2d_model.expressions), len(live2d_model.motions),
        )
    else:
        log.info("live2d disabled — pure chat mode")

    log.info(
        (
            "starting G酱 — channel=#%s provider=%s "
            "vip_window=%dms batch=%.1fs cooldown=%dms buffer=%d"
        ),
        cfg.twitch.channel, cfg.llm.provider,
        cfg.interaction.vip_window_ms,
        cfg.interaction.batch_window_s,
        cfg.interaction.batch_cooldown_ms,
        cfg.interaction.buffer_size,
    )

    # 连接TwitchChat
    # TODO: 后期需要支持YouTube等其他平台，需重构ChatAdapter接口以适配不同平台的聊天系统
    chat = TwitchChatAdapter(
        channel=cfg.twitch.channel,
        bot_username=cfg.twitch.bot_username,
        oauth_token=cfg.twitch.oauth_token,
        trigger=cfg.twitch.trigger,
    )

    # 注入 Live2DModel 到 factory(可能为 None)
    llm = create_provider(cfg.llm, live2d_cfg=cfg.live2d, live2d_model=live2d_model)

    # 预 render output rules 文本,然后注入 PersonaLoader
    # 模型未加载时 expressions/motions 为空 → LLM 只能选 "None"(归一化为 "")
    output_rules_text = render_output_rules(
        expressions=live2d_model.expressions if live2d_model else [],
        motions=live2d_model.motions if live2d_model else [],
    )

    # 加载人格设定
    persona = PersonaLoader(
        base_path=cfg.persona.prompt_file,
        output_rules_text=output_rules_text,
        include_stream_context=cfg.stream_context.enabled,
    )

    # 创建获取Twitch直播标题内容以提供上下文（如果启用）
    # TODO : 目前StreamContextProvider仅支持Twitch，后续需要重构以适配其他平台的直播上下文获取
    sctx: StreamContextProvider | _NullStreamCtx
    polling: asyncio.Task | None = None
    if cfg.stream_context.enabled:
        helix = TwitchHelixClient(
            client_id=cfg.twitch.client_id,
            client_secret=cfg.twitch.client_secret,
        )
        sctx = StreamContextProvider(channel=cfg.twitch.channel, helix=helix)
    else:
        log.info("stream_context disabled — skipping Helix polling")
        sctx = _NullStreamCtx()

    # 创建TTS引擎与音频文件接收方(如果启用)
    tts_engine: EdgeTTSEngine | None = None
    audio_sink: FileAudioSink | None = None
    if cfg.tts.enabled:
        tts_engine = EdgeTTSEngine(
            voices=cfg.tts.voices,
            rate=cfg.tts.rate,
            pitch=cfg.tts.pitch,
        )
        audio_sink = FileAudioSink(output_dir=cfg.tts.output_dir)
        log.info("tts enabled — voices=%s, output_dir=%s",
                 cfg.tts.voices, cfg.tts.output_dir)
    else:
        log.info("tts disabled (config.tts.enabled=false)")

    orch = Orchestrator(
        chat=chat, llm=llm, persona=persona, stream_ctx=sctx,
        vip_window_ms=cfg.interaction.vip_window_ms,
        batch_window_s=cfg.interaction.batch_window_s,
        batch_cooldown_ms=cfg.interaction.batch_cooldown_ms,
        buffer_size=cfg.interaction.buffer_size,
        fallback_text=cfg.llm.fallback.text,
        fallback_kaomoji=cfg.llm.fallback.kaomoji,
        fallback_mood=cfg.llm.fallback.mood,
        fallback_language=cfg.llm.fallback.language,
        default_expression=cfg.live2d.default_expression,
        default_motion=cfg.live2d.default_motion,
        expression_change_frequency=cfg.live2d.expression_change_frequency,
        motion_change_frequency=cfg.live2d.motion_change_frequency,
        tts=tts_engine,
        audio_sink=audio_sink,
    )
    orch.wire()

    # include_stream_context = true时，启动轮询以定期更新直播上下文；否则跳过
    if isinstance(sctx, StreamContextProvider):
        polling = asyncio.create_task(
            sctx.start_polling(cfg.stream_context.poll_interval_ms)
        )
    try:
        await chat.connect()
        log.info("ready — listening for %s in #%s",
                 cfg.twitch.trigger, cfg.twitch.channel)
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
