# 0012-语音转写代理 — 闪电说本地 Whisper 转写代理

把闪电说自定义语音识别服务商的请求接到本机 whisper.cpp，并按配置与本地 Whisper 并行双写当前高级云端模型（默认豆包）。对外仍是 OpenAI 风格的 `POST /v1/chat/completions`，对内转成 whisper-server 的 `/inference`；选用规则见 `specs/prds/prd-00001-dual-write.md`。

## 脚手架

| 字段 | 值 |
|---|---|
| scaffold_version | 2.6.0 |

<!-- 来自 Vibecoding「自进化 Agent 工作区脚手架」母版。升级脚手架约定时改此号并对照母版 CHANGELOG；业务功能变更不要改此号。 -->

## 开始工作前

1. 先读 [`docs/doc_index.md`](./docs/doc_index.md) 找到相关文档，再动手。
2. 改动落进既有目录语义（见下表），不新增平级顶层目录。
3. 新增或改动文档后，登记进 `docs/doc_index.md`。
4. **分夹**：新建可复跑的**业务**工作流 → 只写 [`docs/workflows/<slug>.md`](./docs/workflows/)（先复制 `_TEMPLATE.md`）。**禁止**在 [`docs/builtin-workflows/`](./docs/builtin-workflows/) 新建业务 slug。
5. **任务后反思**：用户明确要求反思 / 任务后回顾 / 跑 post-task-reflect 时（建议在用户已验证本轮产物可用之后）→ 读并执行 [`docs/builtin-workflows/post-task-reflect.md`](./docs/builtin-workflows/post-task-reflect.md)。
6. **跳过反思**：当前任务就是在跑本反思（禁止套娃）；用户明确说不要回顾。
7. **提取经验**：用户明确要求提取经验 / 提炼最佳实践 / 抽跨项目共性时 → 读并执行 [`docs/builtin-workflows/extract-experience.md`](./docs/builtin-workflows/extract-experience.md)。落盘目录见该流（须问用户或读 AGENTS `experience_target`）。
8. **写备忘**：用户明确要求写成备忘 / 记进 memos / write-memo 时 → 读并执行 [`docs/builtin-workflows/write-memo.md`](./docs/builtin-workflows/write-memo.md)。命名 `memo-五位序号-slug`，索引 [`docs/memos/memo-wiki-index.md`](./docs/memos/memo-wiki-index.md)。
9. **记忆巩固与遗忘**：用户明确要求遗忘 / 记忆巩固 / consolidate-memory / 剪枝记忆时 → 读并执行 [`docs/builtin-workflows/consolidate-memory.md`](./docs/builtin-workflows/consolidate-memory.md)。
10. **发工牌**：用户明确要求发工牌 / 写工牌 / 首次发布 / 改合同字段（`name`·`origin`·`depends_on`）时 → 读并执行 [`docs/builtin-workflows/publish-evo-agent-pack.md`](./docs/builtin-workflows/publish-evo-agent-pack.md)。**日常发版不要从本条进门**。
11. **打发版 tag**：用户明确要求发版 / 打 tag / 建 Release 时 → 读并执行 [`docs/builtin-workflows/cut-release-tag.md`](./docs/builtin-workflows/cut-release-tag.md)。已有工牌与 remote 后，日常发版只雇本篇。
12. （可选总目录）若同级存在 [`../AgentWikiIndex/`](../AgentWikiIndex/)，改完「能力声明 / 兄弟关系」后执行：
   `python3 ../AgentWikiIndex/scripts/refresh_catalog.py`
   若不存在该目录，**跳过**，不要报错、不要去建。
13. **团队命令**：产品 / 开发 / 验收 / 测试 / 自主交付等角色在 [`.cursor/commands/team/`](./.cursor/commands/team/)；母版在 Vibecoding 团队成员库；命令全文不抄进本文件。
14. **FAQ**：一次踩坑用技能 `huyuan-ai-dev-faq-assistant`，目录固定 [`docs/faqs/`](./docs/faqs/)。

## 内置流分工

内置流**仅**用户显式触发；任务结束**不**自动跑；互不串联；当前任务已是某流则禁止套娃。职责边界只看本表，正文不重复。

| 流 | 管什么 | 不管什么 |
|---|---|---|
| `post-task-reflect` | 本轮步骤该不该在（删→程序化→鲁棒→加速） | 不写跨项目最佳实践；不写备忘；不剪枝记忆 |
| `extract-experience` | 项目无关最佳实践 | 不改本轮步骤；不写仓内备忘 |
| `write-memo` | 本仓稳定约束 → `docs/memos/` | 不复述 PRD；一次踩坑走 FAQ；跨项目共性走提取经验 |
| `consolidate-memory` | 仓内约定冲突消解、过期/一次性剪枝 | 不做平行记忆库/向量库 |
| `publish-evo-agent-pack` | 首次/改合同工牌 | 日常发版 |
| `cut-release-tag` | 日常发版（upgrades→tag→Release） | 改合同字段 |

## 基线规则

本仓自带；不依赖某家 IDE 的全局规则。若运行时另有全局规则（如 Cursor `~/.cursor/rules/`），一并遵守；冲突时取更严 / 更具体者。

- **设计**：KISS；模块化（高内聚低耦合）；DRY；YAGNI；单一职责
- **质量**：可读性优于简洁；明确优于隐晦
- **协作**：注释解释为什么；优先复用已有组件 / 工具
- **包管理**：npm / pnpm 安装或移除只把命令给用户手动执行；不改 `node_modules` / lockfile；不直接改 `package.json` 依赖字段；新增依赖默认最新稳定版（用户指定版本除外）

## 目录约定

| 目录 | 用途 | 入库 |
|---|---|---|
| `src/` | 业务逻辑包，可被 import | 是 |
| `scripts/` | CLI 入口，一个脚本 = 一个工作流入口 | 是 |
| `skills/` | 可发布成员技能；每个技能一个子目录 `skills/<slug>/` | 是 |
| `assets/` | 输入侧原料与样例 | 目录是；大媒体见 .gitignore |
| `configs/` | 程序行为配置（怎么跑：超时、静音、开关等）；出厂默认入库 | 是 |
| `tests/` | 测试，结构镜像 `src/` 与 `scripts/` | 是 |
| `docs/` | 文档，见 docs 约定 | 是 |
| `specs/prds/` | 产品需求（PRD）；索引见 `specs/prds/prd-wiki-index.md` | 是 |
| `upgrades/` | 发版说明（GitHub Release 正文）；文件名与 tag 一致；首次发版再建 | 是 |
| `cache/` | 可重建缓存，按内容哈希命名 | 否 |
| `temp/` | 中间产物，可随时清空 | 否 |
| `output/` | 最终产物，按 `output/<主题>/` 归档 | 否 |

约束：`cache/`、`temp/`、`output/`、`.env` 全部 gitignore；删掉它们不影响代码可运行。禁止根目录散文件。根目录 `evo_agent_pack.json` 首次发工牌再建（入库）。程序行为配置进 `configs/`，不要写进 `assets/`；密钥与本机私密走环境变量 / `.env`（可用 `.env.example` 作模板），不进 `configs/`。运行时用户覆盖由产品约定，不要为此再开顶层目录。

### skills/ 约定

- 每个技能独占 `skills/<slug>/`（含 `SKILL.md` 等）；slug = frontmatter `name`；**禁止**以 `huyuan-ai` 开头。
- 共用逻辑放 `src/`；技能专属脚本放该技能内 `scripts/`。

### 升格门槛

- 一次性脚本先放 `temp/<主题>/` 或 `output/<主题>/`；确认还会复用再升到 `src/` / `scripts/` / `skills/`。
- 只有「以后还会复跑」的**业务**流程才写 `docs/workflows/<slug>.md` 并登记进 `docs/doc_index.md`。内置流程不走这条（初始化就有，放在 `docs/builtin-workflows/`）。

## 文档约定

| 路径 | 内容 |
|---|---|
| `docs/doc_index.md` | 唯一入口索引，每行路径 + 一行摘要 |
| `docs/workflows/<slug>.md` | 业务可复跑动作；人/Agent 新建只放这里（入口 / 参数 / 步骤 / 产物 / 排查 / 测试） |
| `docs/builtin-workflows/<slug>.md` | 脚手架自带；改已有文件可以，禁止当业务目录用；每篇必须在「开始工作前」有触发，否则不要新增 |
| `docs/memos/` | 本仓稳定约束（备忘）；`memo-NNNNN-slug.md`；索引 `docs/memos/memo-wiki-index.md`（不占序号） |
| `specs/prds/` | 产品需求；`prd-NNNNN-slug.md`；产品经理写入，工程验收官回写文末状态；索引 `specs/prds/prd-wiki-index.md`（不占序号） |
| `docs/best-practices/<slug>.md` | 可选：项目无关最佳实践（提取经验时再建）；须含 semver `version` |
| `docs/faqs/<问题>.md` | 一次踩坑一篇，文件名即问题 |

## 环境

Python 用 **UV** 管理，虚拟环境在本仓 `.venv/`：

    uv venv
    .venv/bin/python scripts/whisper_openai_asr_proxy.py --help

一律显式用 `.venv/bin/python`，不依赖 shell 是否 activate。当前代理只用标准库，无需额外 pip 依赖。本机需已编译的 whisper.cpp（`whisper-server` 与 `models/ggml-*.bin`）；路径、端口、模型见 `configs/proxy.json`，无参启动：`.venv/bin/python scripts/whisper_openai_asr_proxy.py`。

## 能力声明

| 字段 | 值 |
|---|---|
| lifecycle | active |
| owns | 闪电说用的本地 Whisper 转写代理与高级模型双写路由（Chat Completions → whisper-server /inference + 可选豆包 SAUC） |
| not | 闪电说客户端；whisper.cpp 本体与模型训练；云账号开通和计费 |
