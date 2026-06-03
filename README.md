# G酱 (Gちゃん)

Twitch AI VTuber chatbot — Phase 1: 文本对话。

## 启动(开发模式)

```bash
# 一次性
uv sync                              # 创建 .venv 并安装依赖
cp .env.example .env                  # 填入真实 API key
cp config.example.yaml config.yaml    # 改 channel 名

# 跑测试
uv run pytest -v

# 启动 bot
uv run python -m g_chan
```
