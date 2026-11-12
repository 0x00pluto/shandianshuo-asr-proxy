---
name: prd-00001-dual-write
sequence: 1
description: 本地 Whisper 与高级云端模型并行双写；成功用高级文本，失败用本地文本
status: accepted
created: 2026-11-12T11:35:00+08:00
last_accepted_at: 2026-11-12T05:48:54Z
accepted_branch: feat/prd-00001-dual-write
accepted_scope: R0,R1
---

# PRD: 多提供商双写转写

| 属性 | 内容 |
|------|------|
| 状态 | 工程：accepted（见文末「工程验收状态」） |
| 范围 | 本仓代理进程内的识别路由；闪电说客户端、云账号开通与计费不在本仓 |
| 关联 | [`docs/workflows/asr-proxy.md`](../../docs/workflows/asr-proxy.md)；现有入口 `scripts/whisper_openai_asr_proxy.py` |

## 背景与问题

闪电说经自定义服务商打到本仓代理。当前只有本地 Whisper，中文效果不如豆包流式语音识别。需要在保持闪电说只连一个本地地址的前提下，引入可替换的高级云端模型，并在云端异常时仍能返回本地结果。

## 目标与非目标

### 目标

- 每次请求**两路同时开始**：本地 Whisper 必定转写；高级模型按配置列表只打**当前第一家**。
- 高级模型返回了结果（含识别成功但文本为空）：闪电说拿到高级文本；本地文本只留日志。
- 高级模型断网、超时、鉴权失败或协议错误：用已经转好的本地文本。
- 高级列表可扩展（豆包 → 未来字节 / 阿里等）；顺序只表示「当前高级是谁」，不是排队重试多家长云端。
- 豆包走新版 API Key；资源 ID 小时版 `volc.seedasr.sauc.duration`；一句话识别 `wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream`。
- 密钥只来自环境变量 `DOUBAO_ASR_API_KEY`，不进 `configs/`，不从闪电说配置抄。

### 非目标

- 抽仓当中实现双写或豆包 WebSocket（本 PRD 落地前，代理行为保持纯本地 Whisper）。
- 豆包失败后再顺序打第二家云端。
- 把 whisper.cpp 或模型文件迁进本仓。
- 改造闪电说客户端，或要求用户在闪电说里直接配火山引擎（本仓继续扮演自定义服务商）。

## 已拍板规则

| 项 | 决定 |
|----|------|
| 对外协议 | 仍为 `POST /v1/chat/completions` + `input_audio` WAV；地址 `http://127.0.0.1:<port>/v1` |
| 并发 | 本地与当前高级模型并行启动；不是「先高级再本地」的排队 |
| 选用文本 | 高级成功 → 高级；高级失败 → 本地；两路都失败 → 502 |
| 空文本 | 高级识别成功但文本为空视为有效结果，不再改用本地 |
| 高级列表 | 配置项（如 `premium`）有序；一次请求只调用排在最前且密钥齐全的一家 |
| 缺密钥 | 启动成功；高级路跳过，本次只返回本地，并打日志 |
| 豆包超时 | 默认约 12 秒后采用本地结果 |
| 日志 | 可记提供商名与失败类型；不写密钥、不写音频 |

## 验收口径（实现本 PRD 时）

1. 单测或等价验证：两路都被调用；高级成功时返回高级文本。
2. 高级超时 / 鉴权失败时返回本地文本，且本地与高级同时开始。
3. 无 `DOUBAO_ASR_API_KEY` 时仍能启动并完成本地转写。
4. 闪电说地址与请求形状相对现有 workflow 不变。

## 1. 工程验收状态

> 由 `/team:prd-accept` 维护；勿手工编造「通过」。最后更新：2026-11-12T05:48:54Z，feat/prd-00001-dual-write@working-tree（尚无 commit），范围：R0,R1。

### 总览

- 工程状态：`accepted`（本 PRD 关闭）
- 验收判定：通过
- 最近验收：对照实现终验 + 人用闪电说联调确认可用
- 摘要：
  - 四条验收口径均有证据；非目标未纳入
  - `run_dual` 并行双写；豆包 SAUC；失败回落本地
  - 密钥仅 `.env` / `DOUBAO_ASR_API_KEY`；行为配置在 `configs/proxy.json` + `configs/premium.json`
  - 对外仍为 `http://127.0.0.1:<port>/v1`（当前配置 port=18888）

### Release 交付

| Release | 状态 | 说明 |
|---------|------|------|
| R0 | 通过 | 双写路由、缺密钥回落、对外协议不变 |
| R1 | 通过 | 豆包 SAUC、超时/鉴权回落、真实外网与闪电说联调 |

### 功能验收清单（Agent 优先读此表）

| ID | 能力摘要 | Release | 状态 | 证据 |
|----|----------|---------|------|------|
| A1 | 两路同时调用；高级成功返回高级文本 | R0 | 通过 | `src/asr_proxy/select.py` `run_dual`；`tests/asr_proxy/test_select.py` |
| A2 | 超时/鉴权失败回落本地 | R0 | 通过 | 同文件 timeout/auth 用例 |
| A3 | 无密钥可启动并完成本地转写 | R0 | 通过 | 既有 HTTP `58431`（高级未启用 + 本地 200） |
| A4 | 闪电说地址形状不变 | R0 | 通过 | `docs/workflows/asr-proxy.md`；`configs/proxy.json` → `http://127.0.0.1:18888/v1`；人确认闪电说可用 |
| A5 | 豆包 nostream + seedasr.duration + 新版 API Key | R1 | 通过 | `configs/premium.json`；`src/asr_proxy/doubao_sauc.py`；HTTP「高级 doubao」 |
| A6 | 密钥不进 configs | R1 | 通过 | `.env.example` / `.env` gitignore；`api_key_env` 仅为变量名 |

### 未完成与遗留

- 仓库尚无 commit，`accepted_commit` 未填（不阻塞关闭）。

### 质量检查

| 检查项 | 状态 |
|--------|------|
| `.venv/bin/python scripts/whisper_openai_asr_proxy.py --help` | 通过 |
| `.venv/bin/python -m py_compile scripts/whisper_openai_asr_proxy.py`（及 `src/asr_proxy/*.py`） | 通过 |
| `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests/asr_proxy -p 'test_*.py' -q` | 通过（19） |
| 文档与配置同步 | 通过（`docs/workflows/asr-proxy.md`、`configs/proxy.json`、`configs/premium.json`） |

---
统计：通过 6 / 部分 0 / 未实现 0 / 范围外 0
