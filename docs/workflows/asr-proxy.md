# 启动本地转写代理（SenseVoice / Whisper 兜底）

一条命令启动代理，对外提供闪电说可用的 `POST /v1/chat/completions`。本地兜底在 **SenseVoice** 与 **Whisper** 中二选一（`configs/proxy.json` → `local.engine`）；远程豆包规则见 [`specs/prds/prd-00001-dual-write.md`](../../specs/prds/prd-00001-dual-write.md)。本地引擎选择见 [`specs/prds/prd-00002-local-fallback.md`](../../specs/prds/prd-00002-local-fallback.md)。

默认对外端口 **18888**（`proxy.json` 的 `port`）。

## 入口

```bash
cd /Users/peng.zhi/Documents/Codex/0012-语音转写代理
uv sync
.venv/bin/python scripts/whisper_openai_asr_proxy.py
```

```bash
.venv/bin/python scripts/whisper_openai_asr_proxy.py --help
# 可选：指定其它配置文件
.venv/bin/python scripts/whisper_openai_asr_proxy.py --config /path/to/proxy.json
```

## 配置

| 文件 | 入库 | 说明 |
|---|---|---|
| [`configs/proxy.json`](../../configs/proxy.json) | 是 | `bind_host`、`port`（默认 18888）、`local`（引擎意图）、whisper 路径/超时、日志 |
| [`configs/premium.json`](../../configs/premium.json) | 是 | 高级模型列表（无密钥；`api_key_env` 为变量名） |
| [`.env.example`](../../.env.example) → `.env` | 模板是 / `.env` 否 | 豆包密钥 `DOUBAO_ASR_API_KEY` |

### `local.engine`

| 值 | 含义 |
|---|---|
| `auto`（默认） | 有 SenseVoice 三件套 → SenseVoice；否则 Whisper 文件齐全 → Whisper；否则本地关闭 |
| `sensevoice` | 只尝试 SenseVoice；不可用则本地关闭（不偷偷切 Whisper） |
| `whisper` | 只尝试 Whisper；不可用则本地关闭 |
| `off` | 不跑本地 |

`local.engine` 是用户意图，启动后不会被改成探测结果。探测结果写在 `local.last_resolved`；若 `sensevoice.model_dir` 为空则会填上找到的路径。

SenseVoice 三件套：`model.onnx` + `tokens.json` + `config.yaml`。默认探测：

- macOS：`~/Library/Application Support/Shandianshuo/workspace/models/sensevoice-small`
- Windows：`%APPDATA%\Shandianshuo\workspace\models\sensevoice-small`，其次 `%APPDATA%\cn.shandianshuo.desktop\...`

### 依赖安装（一条命令）

```bash
cd /Users/peng.zhi/Documents/Codex/0012-语音转写代理
uv sync
```

会按 `pyproject.toml` / `uv.lock` 装齐 SenseVoice 所需包。缺依赖时本路关闭，进程仍监听；日志提示再执行 `uv sync`（启动时不自动联网装包）。

监听关系：

| 地址 | 用途 |
|---|---|
| `http://<bind_host>:<port>/v1` | 闪电说自定义服务商（默认 `http://127.0.0.1:18888/v1`） |
| `http://<bind_host>:<port+1>` | 仅当本地引擎为 Whisper 时才拉起 whisper-server |

## 密钥

```bash
cp .env.example .env
# 编辑 .env：DOUBAO_ASR_API_KEY=你的新版 API Key
```

未设置密钥也可启动：有本地则仅本地；无本地则请求会 502。

## 闪电说怎么填（Chat 音频）

启动后控制台用 Rich 打一块 **ASR Proxy** 摘要，分两段：

1. **运行状态**：对外地址、高级模型、本地引擎  
2. **闪电说自定义服务商（Chat 音频）**：始终给出接入方式、Base URL、API Key `local`、模型 `medium`；以及配置结果  
   - 成功：`已写入/已更新自定义服务商配置` + `config.json` 路径；提示在闪电说里刷新设置  
   - 失败：`未写入：…`；按上面四项在闪电说里手填  

## 日常步骤

1. `uv sync`；若要用 Whisper 兜底，再准备好 whisper-server + ggml。
2. （可选）配置 `.env` 豆包密钥。
3. 无参启动；看摘要两段。
4. 闪电说：配置已写入/更新则刷新设置；未写入则按摘要四项手填。
5. 停服务：Ctrl+C。

## 产物

- 无业务落盘产物；识别文本经 HTTP 返回。
- 请求日志：`temp/logs/asr-proxy.log`（约 2MB×5）。

| 字段 | 含义 |
|---|---|
| `chosen` | `doubao` / `local` / `failed` |
| `local_engine` | `sensevoice` / `whisper` / `off` |
| `wav_bytes` / `wav_sec≈` | 入站 WAV |
| `premium_*` / `local_*` / `reply_chars` | 双写耗时与长度 |

## 失败排查

| 现象 | 处理 |
|---|---|
| 本地关闭且提示 deps_missing | 在本仓根目录执行 `uv sync` |
| 找不到 SenseVoice 三件套 | 在闪电说下载 SenseVoice，或填 `local.sensevoice.model_dir` |
| 找不到 whisper-server / 模型 | 检查 `whisper.*`；或改用 `auto`/`sensevoice` |
| 无法监听 18888 | 停占用进程，或改 `port`（内部 Whisper 为 port+1） |
| 闪电说配置未改写 | 看摘要「配置 未写入」；按同段四项手填 |

## 测试

```bash
cd /Users/peng.zhi/Documents/Codex/0012-语音转写代理
.venv/bin/python scripts/whisper_openai_asr_proxy.py --help
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests/asr_proxy -p 'test_*.py' -v
```
