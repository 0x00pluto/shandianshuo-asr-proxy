# 语音转写代理（ASR Proxy）

把[闪电说](https://shandianshuo.cn) 自定义语音识别（Chat 音频）接到本机：本地 SenseVoice / Whisper 二选一兜底，并可并行走豆包等高级云端模型。对外是 OpenAI 风格的 `POST /v1/chat/completions`。

## 安装 UV

本仓用 [UV](https://docs.astral.sh/uv/) 管 Python 依赖。若本机还没有：

```bash
# macOS（Homebrew）
brew install uv
```

```bash
# macOS / Linux 官方安装脚本
curl -LsSf https://astral.sh/uv/install.sh | sh
```

装完后新开一个终端，确认：

```bash
uv --version
```

## 用法

```bash
cd <本仓目录>
uv sync
```

（可选）启用豆包高级模型：

```bash
cp .env.example .env
# 编辑 .env，填入 DOUBAO_ASR_API_KEY=…
```

行为配置：出厂默认在 [`config-templates/`](config-templates/)；首次启动会拷到本仓 [`configs/`](configs/)（该目录不入库，可改可写回）。改分发默认请改 templates；本机调端口/Whisper 路径请改 `configs/`。

启动：

```bash
.venv/bin/python scripts/whisper_openai_asr_proxy.py
```

控制台会打印两段摘要：

1. **运行状态**：对外地址、高级模型、本地引擎  
2. **闪电说自定义服务商（Chat 音频）**：接入方式、Base URL、API Key、模型，以及是否已写入/更新本机闪电说配置  

在闪电说里：若提示已写入/已更新配置，刷新设置即可；若提示未写入，按摘要四项手填 Chat 音频服务商。

停止：在运行代理的终端按 `Ctrl+C`。

## 更多

端口、引擎选择、路径与排查见 [`docs/workflows/asr-proxy.md`](docs/workflows/asr-proxy.md)。文档总索引：[`docs/doc_index.md`](docs/doc_index.md)。
