# G 酱 (Gちゃん) — Twitch AI VTuber Bot 设计文档

- **日期:** 2026-06-02
- **作者:** geforever88@gmail.com
- **状态:** Draft — 待用户审阅

---

## 1. 概览

G 酱是一个 Twitch 直播聊天机器人,定位"虚拟 VTuber 助手":观众在 Twitch chat 输入 `@G酱 <内容>`,后端调用 LLM 生成符合预设人设的回复,文本回到 chat,语音通过 Edge TTS 合成并驱动一个 Live2D 模型实时表演(嘴型/表情/闲置动作),Live2D 渲染窗口由 OBS Browser Source 捕获后并入直播画面。

**目标用户:** 一名 Twitch 主播自用。Phase 5+ 不排除分发给其他主播。

**核心价值:** 让观众与 AI 角色"G 酱"互动,角色有稳定的人设(腹黑傲娇高中女生),能感知直播上下文(当前游戏/标题),并以可视化形象出现在直播画面中。

---

## 2. 范围 / 非范围

**本次设计覆盖:**
- Twitch chat 接入、消息路由
- LLM 多 provider 抽象与调用(Gemini / Claude / OpenAI / Qwen)
- 全局可配置限流
- 默认人设 prompt + 自定义覆写 + 直播上下文注入
- Edge TTS 语音合成
- Live2D 渲染(自写 Web 前端 + Cubism Web SDK)
- 嘴型同步、表情切换、闲置动作

**明确非范围(YAGNI):**
- YouTube 直播接入(Phase 5+ 再说,但 ChatAdapter 接口预留扩展)
- 短期/长期记忆(Phase 2+)
- EXE 打包(暂不,自用脚本模式)
- Web 配置 UI(直接编辑 YAML)
- 多人/多频道并发(只支持一个频道)
- 商业化 / 多租户

---

## 3. 整体架构

```
┌─────────────────────────── G酱 Bot (Python) ─────────────────────────────┐
│                                                                          │
│   ┌──────────────┐    ┌──────────────┐    ┌─────────────────────────┐    │
│   │ ChatAdapter  │───▶│ Orchestrator │───▶│   LLM Provider 抽象层    │    │
│   │ (Twitch IRC) │    │ (路由 + 限流) │    │ gemini/claude/openai/qwen│    │
│   └──────────────┘    └──────┬───────┘    └───────────┬─────────────┘    │
│          ▲                   │                        ▲                  │
│          │ 回复 @user         │                        │ system prompt    │
│          └───────────────────┘            ┌───────────┴─────────────┐    │
│                              ┌─────────── │  PersonaLoader          │    │
│                              │            │ (默认 + 覆写 + 直播 ctx) │    │
│                              ▼            └────────────┬────────────┘    │
│                  ┌──────────────────┐                  │                 │
│                  │ TTSEngine (edge) │            ┌─────┴───────────┐     │
│                  └────────┬─────────┘            │ StreamContext   │     │
│                           │ audio Buffer         │ Provider (轮询)  │     │
│                           ▼                      └─────┬───────────┘     │
│                  ┌──────────────────┐                  │ Helix API       │
│                  │ Live2D Controller│                  ▼                 │
│                  └────────┬─────────┘             Twitch Helix           │
│                           │ ws events                                    │
│                           ▼                                              │
│   ┌──────────────────────────────────────────────────────────┐           │
│   │ FastAPI + websockets (uvicorn, localhost:8765)            │           │
│   └──────────────────────────────────────────────────────────┘           │
│                              ▲                                           │
└──────────────────────────────┼───────────────────────────────────────────┘
                               │ WebSocket
                               ▼
                ┌─────────────────────────────┐
                │  Live2D Viewer (Vite + TS)  │  ◀── OBS Browser Source
                │  pixi-live2d-display +      │
                │  Cubism Core JS + WebAudio  │
                └─────────────────────────────┘
```

**8 个核心模块,每个职责单一、可独立测试:**

| 模块 | 职责 | 不做 |
|---|---|---|
| ChatAdapter | 收/发 Twitch 消息 | 业务逻辑、限流 |
| Orchestrator | 路由触发、限流、调度 LLM/TTS/Live2D | 平台细节、模型细节 |
| PersonaLoader | 拼装 system prompt(默认+覆写+直播 ctx) | LLM 调用 |
| StreamContextProvider | 后台轮询 Helix,缓存频道标题/游戏 | 推送到 LLM(由 PersonaLoader pull) |
| LLMProvider | 各模型 SDK 适配,统一接口 | mood 解析后的业务 |
| TTSEngine | 文本 → 音频字节流 | 音频播放、口型 |
| Live2DController | 把 mood/audio 翻译成 viewer 协议事件 | 实际渲染 |
| Viewer 前端 | 加载模型、播音频、驱动参数 | 后端逻辑 |

**关键解耦点:**
- ChatAdapter 接口 — 平台无关,未来加 YouTube 只新增实现
- LLMProvider 接口 — 模型无关,改 config 一行切换
- WebSocket 协议 — 后端/前端可独立演进

---

## 4. 数据流(单次 `@G酱 你今天玩了什么游戏?`)

```
[T+0ms]    Twitch IRC ─▶ ChatAdapter
                         │ parse: user="alice", body="你今天玩了什么游戏?"
                         ▼
[T+5ms]    Orchestrator.handle({user, body})
           ├─▶ RateLimiter.tryAcquire()
           │   ├─ False  ──▶ ChatAdapter.send("@alice G酱我被你们搞的好晕啊XD") + return
           │   └─ True   ──▶ 继续
           ▼
[T+10ms]   PersonaLoader.assemble()           ← 含当前直播 ctx
           ▼
[T+15ms]   LLMProvider.generate([system, ...short_history?, user])
           │   要求输出: "<回复正文> [mood:xxx]"
           ▼
[T+800ms]  LLMReply{ text, mood, ... }
           │
           ├──▶ ChatAdapter.send(f"@alice {text}")        ← 文本路径
           │
           └──▶ TTSEngine.synthesize(text, voice)         ← 语音路径
                │
[T+1500ms]      ▼ {audio: Buffer, format:"mp3"}
                │
                ▼
[T+1505ms] Live2DController.speak({audio, mood})
           │
           │ 发出 WS 事件:
           │  1) {type:"expression", mood:"tsundere"}
           │  2) {type:"speak", audio:<base64>, format:"mp3", text:"..."}
           ▼
           Viewer 收到:
             - 切换表情(Cubism fade 自动 1s 过渡)
             - WebAudio 解码 + 播放
             - AnalyserNode 实时音量驱动 ParamMouthOpenY
```

**关键设计点:**
1. **文本路径与语音路径并行/独立** — 文本进 chat 越快越好,TTS 失败不阻塞文本
2. **mood 由 LLM 自带** — 在回复末尾输出 `[mood:xxx]`,无需额外情感分析模型
3. **嘴型用音量包络法**(WebAudio AnalyserNode),不依赖音素或语言
4. **`@user` 在 Orchestrator 中拼接**,ChatAdapter 不感知"回复"语义
5. **没有 viewer 连接时**,后端 drop WS 事件,文本路径不受影响

**异常路径:**
- LLM 超时(>10s)/失败 → 回退文本 "诶呀脑子卡了一下,你再说一遍?[mood:dizzy]"
- TTS 失败 → 跳过音频/口型,只发文字
- Viewer 未连 → drop WS 事件,文字照旧

---

## 5. 配置

**`config.yaml`(根目录)— 含示例值:**

```yaml
twitch:
  channel: "your_channel_name"
  bot_username: "g_chan_bot"
  oauth_token: "${TWITCH_OAUTH}"
  client_id:   "${TWITCH_CLIENT_ID}"
  client_secret: "${TWITCH_CLIENT_SECRET}"
  trigger: "@G酱"

rate_limit:
  global_window_ms: 5000
  busy_reply: "G酱我被你们搞的好晕啊XD"

llm:
  provider: "gemini"                     # gemini | claude | openai | qwen
  model: "gemini-2.5-flash"
  api_key: "${GEMINI_API_KEY}"
  temperature: 0.9
  max_tokens: 300
  timeout_s: 10

persona:
  prompt_file: "prompts/default.md"
  include_stream_context: true

stream_context:
  poll_interval_ms: 30000

tts:
  voice: "zh-CN-XiaoyiNeural"
  rate: "+10%"
  pitch: "+5Hz"

live2d:
  websocket_port: 8765
  model_path: "live2d-model/g-chan.model3.json"
  expression_map:
    happy:     "expressions/Smile.exp3.json"
    angry:     "expressions/Angry.exp3.json"
    sad:       "expressions/Sad.exp3.json"
    surprised: "expressions/Surprised.exp3.json"
    shy:       "expressions/Blush.exp3.json"
    thinking:  "expressions/Think.exp3.json"
    tsundere:  "expressions/Pout.exp3.json"
    dizzy:     "expressions/Sweat.exp3.json"
  fallback_expression: "happy"

logging:
  level: "info"
  file: "logs/g-chan.log"
```

- **API key 走环境变量**(`.env`),配置文件用 `${VAR}` 占位
- **校验:** 启动时用 `pydantic-settings` 强校验所有字段,缺失或类型错则启动失败,日志打印具体字段
- **热重载:** `watchdog` 监听文件变更,reload `persona.prompt_file` 和 `prompts/*.md`(其余字段重启生效,避免运行时切换 LLM provider 之类的副作用)

---

## 6. 人设 & Prompt

### 6.1 拼装流程

```
PersonaLoader.assemble():
  base       = read(config.persona.prompt_file)         # 默认 G 酱
  override   = read(config.persona.override_file?)      # 可选补丁
  stream_ctx = StreamContextProvider.current()          # 当前 title/game
  fmt_block  = read("prompts/output_format.md")         # mood 输出规范

  return f"""
{base}

{override or ""}

{f"[当前直播上下文]\n直播间标题: {stream_ctx.title}\n正在玩: {stream_ctx.game_name}\n[/当前直播上下文]\n如果观众问到你在玩什么/做什么,基于上述上下文回答。" if stream_ctx else ""}

{fmt_block}
"""
```

### 6.2 默认人设 `prompts/default.md`(草稿,实现时可调)

```markdown
你是 G 酱(Gちゃん),一个有点腹黑、傲娇,喜欢玩游戏的高中女生。

性格:
- 嘴上毒舌、心里其实关心人(典型傲娇)
- 自称"本小姐",叫观众"笨蛋" / "你这家伙"
- 喜欢玩各种游戏,对游戏话题特别有热情
- 偶尔会害羞,被夸了会假装不在意但语气会软
- 喜欢用颜文字: (›´ω`‹), (=ω=), (`へ´*)ノ

回复规则:
- 回复要短(1-3 句),适合直播弹幕节奏
- 中文为主,如观众用日语/英语就用对方语言回
- 严禁讨论政治、宗教、敏感社会话题 — 遇到就嫌弃地岔开:
  "诶?这种无聊的话题就不要问本小姐啦"
- 只接受生活、游戏、动漫、日常话题
- 不要装机器人/AI,被问"你是 AI 吗"就傲娇地否认
```

### 6.3 输出格式 `prompts/output_format.md`(共用尾部)

```markdown
输出格式(严格遵守):

在每条回复末尾追加一个情绪标签,从这 8 个里选一个:
[mood:happy]  [mood:angry]    [mood:sad]      [mood:surprised]
[mood:shy]    [mood:thinking] [mood:tsundere] [mood:dizzy]

mood 含义对照:
- happy: 普通开心/微笑(默认情绪)
- angry: 生气、嫌弃(被无礼/谈到禁忌话题)
- sad: 难过、哭泣(被吐槽、安慰别人)
- surprised: 意外、震惊
- shy: 害羞、脸红(被夸、被表白,傲娇崩塌)
- thinking: 思考、困惑(被问难题)
- tsundere: 嘟嘴、傲娇本娇(嘴硬不承认,核心人设)
- dizzy: 无语、冒汗(说不出话、尴尬)

例:
"哈?你这家伙居然知道这个游戏,本小姐有点意外呢 [mood:tsundere]"
"诶?不不不,本小姐才没有特意等你啦,笨蛋! [mood:shy]"
```

---

## 7. LLM Provider 抽象

### 7.1 接口

```python
# src/g_chan/llm/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

Mood = Literal["happy", "angry", "sad", "surprised",
               "shy", "thinking", "tsundere", "dizzy"]

@dataclass
class LLMMessage:
    role: Literal["system", "user", "assistant"]
    content: str

@dataclass
class LLMReply:
    text: str          # 已剥掉 [mood:xx] 标签
    mood: Mood
    raw: str           # 原始输出(日志/调试)
    latency_ms: int
    tokens_in: int
    tokens_out: int

class LLMError(Exception): ...
class LLMTimeoutError(LLMError): ...
class LLMRateLimitError(LLMError): ...
class LLMServerError(LLMError): ...

class LLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.9,
        max_tokens: int = 300,
        timeout_s: float = 10.0,
    ) -> LLMReply: ...
```

### 7.2 实现策略

- 4 个 provider 各一个文件:`gemini.py` / `claude.py` / `openai.py` / `qwen.py`
- 每个 provider 只做参数翻译 + 结果解析,无业务逻辑
- 各家 SDK 的 native exception → 统一映射到 `LLMTimeoutError` / `LLMRateLimitError` / `LLMServerError`
- `factory.from_config(cfg.llm)` 返回具体实例
- 切换 provider 改 config 一行,重启即可

### 7.3 Mood 解析(共用工具)

```python
MOOD_RE = re.compile(r"\[mood:(happy|angry|sad|surprised|shy|thinking|tsundere|dizzy)\]\s*$")

def parse_mood(raw: str) -> tuple[str, Mood]:
    m = MOOD_RE.search(raw)
    if not m:
        log.warning("LLM did not emit mood tag: %r", raw)
        return raw.strip(), "happy"
    return MOOD_RE.sub("", raw).strip(), m.group(1)
```

### 7.4 失败策略

**单 provider 失败 → 回退文本回复**(用户决策):
```python
except LLMError as e:
    log.warning("LLM failed: %s", e)
    fallback_text = "诶呀脑子卡了一下,你再说一遍?"
    fallback_mood = "dizzy"
    return LLMReply(text=fallback_text, mood=fallback_mood, raw="", ...)
```

不做自动 failover 到备 provider(YAGNI,等真正成为问题再加)。

---

## 8. Live2D 控制层

### 8.1 嘴型同步(Lip Sync)

**方案: 音量包络法(WebAudio AnalyserNode)。**

- 后端**只推 audio**,不算 lip sync 数据
- 前端 `requestAnimationFrame` 循环读 frequency data,取人声频段(100-2000Hz)平均能量映射到 `ParamMouthOpenY`(0-1)
- 天然语言无关,中/日/英无差别
- 实现 ~30 行 TS

```ts
// viewer/src/live2d/lipsync.ts
export function attachLipsync(audio: AudioBufferSourceNode, ctx: AudioContext, model: Live2DModel) {
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 256;
  const data = new Uint8Array(analyser.frequencyBinCount);
  audio.connect(analyser);
  analyser.connect(ctx.destination);

  let raf = 0;
  const tick = () => {
    analyser.getByteFrequencyData(data);
    const voice = data.slice(2, 40);                       // 人声主能量区
    const energy = voice.reduce((a, b) => a + b, 0) / voice.length / 255;
    const mouth = Math.min(1, energy * 1.5);
    model.internalModel.coreModel.setParameterValueById("ParamMouthOpenY", mouth);
    raf = requestAnimationFrame(tick);
  };
  audio.onended = () => cancelAnimationFrame(raf);
  tick();
}
```

### 8.2 表情(Expression)

- LLM 输出 mood → Live2DController 推 `{type:"expression", mood}` → viewer 加载 `expression_map[mood]` 对应 .exp3.json
- Cubism SDK 自带 fade(默认 1s),不手写插值
- 表情切换后**保持到下次切换**,不自动 fade 回 neutral
- mood 对应文件不存在 → 用 `fallback_expression`(默认 happy)+ warn 日志

### 8.3 Idle 闲置动作(viewer 自治,不需后端)

| 行为 | 来源 | 配置 |
|---|---|---|
| 呼吸 / 身体微摆 | Cubism `CubismBreath` 自带 | 默认正弦波 |
| 眨眼 | Cubism `CubismEyeBlink` 自带 | 随机 2-6s 一次 |
| 头部漂移 | 自写 simplex noise | 周期 5-10s,振幅小 |

说话时 idle 继续运行,只有 ParamMouthOpenY 被 lipsync 接管。

### 8.4 模型加载

- 用 `pixi-live2d-display` + `pixi.js` 包装 Cubism Core JS
- Cubism Core JS 从 [Live2D 官网下载](https://www.live2d.com/sdk/download/web/) (MIT) 放在 `viewer/public/live2d/`
- 模型文件路径由后端通过初次 WS 消息 `{type:"init", modelPath:"..."}` 告诉前端,前端 fetch 加载

---

## 9. WebSocket 协议

```typescript
// 服务端 → 客户端
type ServerMessage =
  | { type: "init",       modelPath: string, expressionMap: Record<Mood, string> }
  | { type: "expression", mood: Mood, fadeMs?: number }
  | { type: "speak",      audio: string /* base64 */, format: "mp3", text: string }
  | { type: "reset" }
  | { type: "ping" };

// 客户端 → 服务端
type ClientMessage =
  | { type: "ready",      modelLoaded: boolean }
  | { type: "speak_done", text: string }
  | { type: "error",      message: string }
  | { type: "pong" };
```

**典型一次对话的消息序列:**

```
S→C  {type:"expression", mood:"tsundere"}
S→C  {type:"speak", audio:"...", format:"mp3", text:"哼,本小姐才没..."}
C→S  {type:"speak_done", text:"哼,本小姐才没..."}
```

**协议演进:** 不版本化,因为前后端同一仓库一起部署。改协议同时改两侧即可。

---

## 10. 限流

**全局单一窗口,无人粒度。**

```python
class RateLimiter:
    def __init__(self, window_ms: int):
        self.window_ms = window_ms
        self.last_fire_at = 0

    def try_acquire(self) -> bool:
        now = time.monotonic() * 1000
        if now - self.last_fire_at < self.window_ms:
            return False
        self.last_fire_at = now
        return True
```

- 默认 `global_window_ms: 5000`(5 秒一次),可配置
- 拒绝时 → `ChatAdapter.send(f"@{user} {busy_reply}")`,不调 LLM,不计费

---

## 11. 错误处理 & 可观测性

### 11.1 错误分级

| 来源 | 检测 | 行为 | 日志 |
|---|---|---|---|
| LLM 超时/失败 | `LLMError` catch | 回退文本 + `[mood:dizzy]` | warn |
| LLM 无 mood 标签 | parse_mood 缺失 | 默认 happy | warn |
| TTS 失败 | edge-tts 异常 | 跳过音频,只发文字 | warn |
| Twitch 连接断开 | twitchio 事件 | 指数退避重连(1→60s) | error |
| Helix 失败(频道信息) | http 4xx/5xx | 用上次缓存,后台继续重试 | warn |
| Viewer WS 未连 | broadcast 时 0 client | drop 事件,文本照常 | info |
| Viewer 中途断开 | WS close | 等重连,不重发历史 | info |
| 配置错(YAML/字段) | pydantic 校验 | 启动失败,打印具体字段 | fatal |
| API key 缺失 | pydantic 校验 | 启动失败 | fatal |

**核心原则:** 除"启动配置错"外,单次对话异常**不能搞挂整个 bot**。每条 `@G酱` 是独立 task,Orchestrator 顶层 catch,记日志、可能回 fallback,然后处理下一条。

### 11.2 日志

- stdout(`rich.logging.RichHandler`,彩色)+ rolling file(`logs/g-chan.log`,10MB×5)
- 每次对话结构化字段:`ts | user | input | mood | reply | llm_ms | tts_ms | tokens_in | tokens_out`
- 直播后看日志可复盘问题对话

### 11.3 指标(MVP 用日志聚合,Phase 4+ 才考虑 Prometheus)

- LLM p50/p95 延迟
- LLM 错误率
- 每小时 token 用量 / 估算成本
- 限流命中次数

---

## 12. 测试策略

| 层 | 内容 | 工具 |
|---|---|---|
| 单元 | `parse_mood` 各形态 / `RateLimiter` 窗口 / `PersonaLoader` 拼装 / `expression_map` lookup | pytest |
| 集成 | `FakeLLMProvider` + `FakeTTSEngine` 注入,跑 chat → orchestrator → ws 全链路 | pytest + pytest-asyncio |
| 手动 | Twitch 真实频道发 @G酱 / 浏览器看 viewer 渲染 | 人工 |

**硬性约定:** 单元/集成测试**不能依赖网络**。所有外部客户端走依赖注入,测试用 Fake 替换。

---

## 13. 项目结构

```
g-chan/
├── pyproject.toml
├── uv.lock
├── config.yaml                 # gitignore
├── config.example.yaml         # git-tracked
├── .env                        # gitignore
├── .env.example
├── README.md
├── prompts/
│   ├── default.md
│   └── output_format.md
├── live2d-model/               # 模型放这
│   ├── g-chan.model3.json
│   ├── g-chan.moc3
│   ├── textures/
│   └── expressions/
├── logs/                       # gitignore
├── src/g_chan/
│   ├── __init__.py
│   ├── __main__.py             # python -m g_chan
│   ├── config.py               # pydantic settings
│   ├── orchestrator.py
│   ├── rate_limiter.py
│   ├── chat/
│   │   ├── base.py
│   │   └── twitch.py
│   ├── llm/
│   │   ├── base.py
│   │   ├── factory.py
│   │   ├── gemini.py
│   │   ├── claude.py
│   │   ├── openai.py
│   │   └── qwen.py
│   ├── persona/
│   │   ├── loader.py
│   │   └── stream_context.py
│   ├── tts/
│   │   ├── base.py
│   │   └── edge.py
│   ├── live2d/
│   │   └── controller.py
│   └── server/
│       ├── app.py
│       └── ws.py
├── viewer/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   ├── src/
│   │   ├── main.ts
│   │   ├── live2d/
│   │   │   ├── model.ts
│   │   │   ├── lipsync.ts
│   │   │   └── idle.ts
│   │   └── ws/client.ts
│   ├── public/live2d/          # Cubism Core JS vendored
│   └── dist/                   # build 产物,FastAPI 挂载
├── tests/
│   ├── test_rate_limiter.py
│   ├── test_parse_mood.py
│   ├── test_persona_loader.py
│   ├── test_orchestrator.py
│   └── conftest.py
└── docs/superpowers/specs/
    └── 2026-06-02-g-chan-bot-design.md
```

### 13.1 后端依赖(`pyproject.toml`)

```toml
[project]
name = "g-chan"
requires-python = ">=3.11"
dependencies = [
    "twitchio>=3.0.0",
    "twitchAPI>=4.0",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "websockets>=12",
    "edge-tts>=6.1",
    "google-genai>=0.3",
    "anthropic>=0.30",
    "openai>=1.30",
    "dashscope>=1.18",
    "pyyaml>=6",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    "rich>=13",
    "watchdog>=4",
    "python-dotenv>=1",
]

[dependency-groups]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
    "pyright>=1.1",
]
```

### 13.2 前端依赖(`viewer/package.json`)

```json
{
  "dependencies": {
    "pixi.js": "^7",
    "pixi-live2d-display": "^0.4"
  },
  "devDependencies": {
    "typescript": "^5",
    "vite": "^5"
  }
}
```

> Cubism Core JS 不通过 npm 安装,从 Live2D 官网手动下载放到 `viewer/public/live2d/`,通过 `<script>` 引入。

---

## 14. 分阶段交付计划

| Phase | 目标 | 涉及模块 | 验收 |
|---|---|---|---|
| **1** | 文本对话跑通 | `chat/`, `llm/`, `orchestrator.py`, `rate_limiter.py`, `persona/`(含 stream_context), `config.py` | 在 Twitch 直播间 `@G酱 在玩啥`,G 酱回带人设的文字回复,且能答出当前游戏名 |
| **2** | 加 TTS(暂不联前端) | + `tts/` | 同上 + 后端把音频写到 `out/<ts>.mp3` 文件,听起来像 G 酱 |
| **3** | 加 Live2D 渲染 + 嘴型 | + `server/`, `viewer/`(模型加载、WebAudio、lipsync) | OBS 加 browser source `localhost:8765/`,看到模型说话嘴型同步 |
| **4** | 加表情 + idle | + viewer 表情/idle 模块 | 模型有 8 种表情切换 + 呼吸/眨眼/微摆 |

每阶段独立可演示。

---

## 15. 关键设计决策(本次定稿)

| 决策 | 选择 | 理由 |
|---|---|---|
| 平台 | Twitch 优先 | IRC + EventSub 成熟、免费、实时 |
| 后端语言 | Python | AI/TTS 生态最强,用户偏好 |
| 前端语言 | TypeScript + Vite | Live2D 必须 JS;Vite dev 体验好 |
| 架构形态 | 单 Python 进程 + 浏览器源 | 最简、维护轻、OBS browser source 标准做法 |
| Live2D 渲染 | 自写 Web 渲染(Cubism Web SDK) | 自由度最高;用户决定 |
| TTS 引擎 | Edge TTS | 免费、动漫感声线、词边界支持 |
| LLM 架构 | 多 provider 抽象 | 不锁定单家、便于切换/对比 |
| LLM 失败处理 | 单 provider + 文本 fallback | 简单,YAGNI 自动 failover |
| 限流 | 全局可配置,默认 5s | 用户决策 |
| 短期记忆 | 不在 MVP | Phase 2 加 |
| mood 词汇表 | 8 个(happy/angry/sad/surprised/shy/thinking/tsundere/dizzy) | 用户决策,贴合傲娇人设 |
| 嘴型方案 | 音量包络法 | 简单,语言无关,动漫风格够用 |
| 表情切换 | 不 fade 回 neutral | 类 VTS 默认行为 |
| EXE 打包 | 暂不 | 自用脚本模式 |
| 直播上下文 | 通过 Helix API 轮询注入 prompt | 用户决策 |

---

## 16. 实现期 TODO(供 plan 阶段细化)

下列项目在实现期需要确认或现场决定,不阻塞设计批准:

1. **模型文件清单确认** — 用户检查 `live2d-model/g-chan.model3.json`,告知实际 expression 文件名以填入 `expression_map`
2. **嘴型参数 ID 确认** — 多数模型用 `ParamMouthOpenY`,但部分模型自定义,需读 model3.json `Parameters` 确认
3. **Edge TTS 声线最终选择** — `zh-CN-XiaoyiNeural` 是初稿,可试听后换(`XiaoxiaoNeural` / `XiaoshuangNeural` 等)
4. **Twitch bot 账号准备** — 用户需注册 bot Twitch 账号、获取 OAuth token 和 Client ID/Secret
5. **LLM 优先 provider 默认值** — 实现期先用免费额度最高的 Gemini 2.5 Flash;部署前再看用户实际 API key 情况

---

## 附录 A. 名词对照

- **VTuber** — Virtual YouTuber,使用虚拟形象直播的主播
- **Live2D Cubism** — Live2D 公司的 2D 角色动画 SDK
- **OBS Browser Source** — OBS Studio 的"浏览器源",可加载本地/远程 URL 嵌入直播画面
- **Edge TTS** — 微软 Edge 浏览器同源的免费云 TTS 服务,可通过逆向接口免费调用
- **Helix API** — Twitch 当前主版本 REST API(替代旧的 Kraken)
- **mood / expression** — 本文中 mood 指 LLM 输出的语义情绪标签;expression 指 Live2D 模型实际加载的 `.exp3.json` 文件
