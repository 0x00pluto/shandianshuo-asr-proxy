# 启动本地 Whisper 转写代理

一条命令拉起本机 whisper-server，并对外提供闪电说可用的 `POST /v1/chat/completions`。闪电说自定义服务商地址填 `http://127.0.0.1:<port>/v1`（`<port>` 来自配置）。

选用文本规则（本地 / 高级并行、回落、空文本）见 [`specs/prds/prd-00001-dual-write.md`](../../specs/prds/prd-00001-dual-write.md)，本篇只写启动与配置入口。

## 入口

```bash
cd /Users/peng.zhi/Documents/Codex/0012-语音转写代理
.venv/bin/python scripts/whisper_openai_asr_proxy.py
```

端口、模型、whisper 路径都在 [`configs/proxy.json`](../../configs/proxy.json)，无需再传 `--port` / `--model`。

```bash
.venv/bin/python scripts/whisper_openai_asr_proxy.py --help
# 可选：指定其它配置文件
.venv/bin/python scripts/whisper_openai_asr_proxy.py --config /path/to/proxy.json
```

## 配置

| 文件 | 入库 | 说明 |
|---|---|---|
| [`configs/proxy.json`](../../configs/proxy.json) | 是 | `bind_host`、`port`、whisper 路径/模型/超时 |
| [`configs/premium.json`](../../configs/premium.json) | 是 | 高级模型列表（无密钥；`api_key_env` 为变量名） |
| [`.env.example`](../../.env.example) → `.env` | 模板是 / `.env` 否 | 豆包密钥 `DOUBAO_ASR_API_KEY` |

监听关系（由 `port` 推导，不单独配置内部端口）：

| 地址 | 用途 |
|---|---|
| `http://<bind_host>:<port>/v1` | 闪电说自定义服务商 |
| `http://<bind_host>:<port+1>` | 本机 whisper-server（仅代理转发） |

改端口或模型：编辑 `configs/proxy.json` 后重启。

## 密钥

```bash
cp .env.example .env
# 编辑 .env：DOUBAO_ASR_API_KEY=你的新版 API Key
```

启动脚本会加载本机 `.env`，且不覆盖已有环境变量。未设置密钥也可启动，仅走本地 Whisper。

## 日常步骤

1. 确认本机已编译 whisper-server，且 `proxy.json` 里的路径与模型可用。
2. 若要用高级模型：配置 `.env` 中的 `DOUBAO_ASR_API_KEY`。
3. 无参启动；日志出现「对外地址」和「whisper-server 已就绪」后可用。
4. 闪电说地址填日志里的 `http://127.0.0.1:<port>/v1`。
5. 停服务：终端 Ctrl+C。

## 产物

- 无落盘产物；识别文本经 HTTP 返回给闪电说。
- 控制台日志含结局、提供商名、失败种类、WAV 字节数与文本长度；不含密钥与音频内容。

## 失败排查

| 现象 | 处理 |
|---|---|
| 找不到 whisper-server / 模型 | 检查 `configs/proxy.json` 的 `whisper.root` / `bin` / `model` |
| 无法监听端口 | 改 `proxy.json` 的 `port`，或停掉占用 `port` 与 `port+1` 的进程 |
| 闪电说 404 `/v1/chat/completions` | 地址须带 `/v1` |
| whisper-server 就绪超时 | 调大 `whisper.ready_timeout_sec`；先看子进程是否提前退出 |
| 豆包鉴权失败回落本地 | 核对 `.env` 里 `DOUBAO_ASR_API_KEY`；重启后再试 |

## 测试

```bash
cd /Users/peng.zhi/Documents/Codex/0012-语音转写代理
.venv/bin/python scripts/whisper_openai_asr_proxy.py --help
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests/asr_proxy -p 'test_*.py' -v
```
