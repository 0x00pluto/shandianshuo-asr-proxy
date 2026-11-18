### **Q: 如何用一条命令装好 SenseVoice 依赖，而不是手敲一串 pip 包名？**

**A:**
本仓已把 `onnxruntime`、`numpy`、`kaldi-native-fbank` 写进 `pyproject.toml`。在仓库根执行 `uv sync` 即可；代理启动时若仍缺包只会提示再跑 `uv sync`，不会自动联网安装。

**问题症状：**
- 启动摘要里本地为 `off · sensevoice_deps_missing`
- 或日志出现依赖相关失败，并提示安装命令

**根本原因：**
SenseVoice 走进程内 ONNX，需要上述第三方包；旧说明曾让人手敲 `uv pip install …` 长列表，易漏、难复现版本。

**解决方案：**
1. 若没有 UV：见仓库根 [`README.md`](../../README.md)「安装 UV」。
2. 在本仓根执行：

```bash
uv sync
.venv/bin/python scripts/whisper_openai_asr_proxy.py
```

**关键配置要点：**
- 一律用 `.venv/bin/python`，不依赖是否 `activate`
- 锁文件 `uv.lock` 入库，保证别人装到同一套版本
- 启动路径**不会**替你执行 `uv pip install`

**参考文档：**
- [README.md](../../README.md)
- [docs/workflows/asr-proxy.md](../workflows/asr-proxy.md)
