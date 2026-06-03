"""文件 sink — 把 TTSAudio 写到 <output_dir>/<ts>_<user>.<ext>。"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

from g_chan.tts.base import AudioSink, TTSAudio

log = logging.getLogger(__name__)

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9_\-]")


def _sanitize(s: str) -> str:
    cleaned = _UNSAFE_CHARS.sub("_", s)
    return cleaned or "unknown"


class FileAudioSink(AudioSink):
    def __init__(self, output_dir: str):
        self._dir = Path(output_dir)

    async def write(self, audio: TTSAudio, *, user: str) -> Path:
        self._dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        ts = now.strftime("%Y%m%d-%H%M%S-") + f"{now.microsecond // 1000:03d}"
        safe_user = _sanitize(user)
        filename = f"{ts}_{safe_user}.{audio.format}"
        path = self._dir / filename
        path.write_bytes(audio.data)
        log.info("wrote audio: %s (%d bytes, voice=%s)",
                 path, len(audio.data), audio.voice)
        return path
