#!/usr/bin/env python3
"""一条命令拉起 whisper-server，并把闪电说的 Chat Completions ASR 转成 /inference。

行为配置见 configs/proxy.json 与 configs/premium.json；密钥见本机 .env。
对外监听 bind_host:port，whisper-server 固定绑在 port+1。
"""

import argparse
import atexit
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from asr_proxy.doubao_sauc import recognize_wav
from asr_proxy.local_engine import (
    ENGINE_OFF,
    ENGINE_SENSEVOICE,
    ENGINE_WHISPER,
    INSTALL_HINT,
    ResolvedLocal,
    resolve_local_engine,
    write_resolved_back,
)
from asr_proxy.premium_config import ActivePremium, load_premium_runtime
from asr_proxy.proxy_config import ProxyConfig, default_config_path, load_proxy_config
from asr_proxy import request_log
from asr_proxy.select import DualOutcome, run_dual
from asr_proxy.shandianshuo_config import align_custom_provider
from asr_proxy.sensevoice_onnx import SenseVoiceEngine
from asr_proxy.startup_banner import StartupStatus, print_startup_banner

WAV_MIME_TYPES = {"audio/wav", "audio/x-wav", "audio/wave"}

_whisper_proc = None
_sensevoice_engine: SenseVoiceEngine | None = None


def load_dotenv(path: Path | None = None) -> None:
    """加载本机 .env：只填充尚未设置的环境变量，不覆盖已有值。"""
    env_path = path or (REPO_ROOT / ".env")
    if not env_path.is_file():
        return
    try:
        raw = env_path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in raw.splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if text.startswith("export "):
            text = text[len("export ") :].strip()
        if "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[key] = value


def main():
    global _sensevoice_engine
    args = parse_args()
    load_dotenv()
    config_path = args.config or default_config_path()
    config = load_proxy_config(config_path)
    request_log.setup_request_logging(config.logging, REPO_ROOT)
    public_port = config.port
    internal_port = config.internal_port

    resolved = resolve_local_engine(config)
    try:
        write_resolved_back(config.config_path, config.local, resolved)
    except OSError as exc:
        print(f"写回 local.last_resolved 失败（忽略）：{exc}", flush=True)

    _providers, active_premium = load_premium_runtime()
    if active_premium is None:
        premium_label = "未启用"
    else:
        premium_label = (
            f"{active_premium.provider.id} · {active_premium.provider.timeout_sec:g}s"
        )

    local_transcribe = None
    local_detail = ""
    hint_uv_sync = False
    if resolved.engine == ENGINE_SENSEVOICE:
        try:
            _sensevoice_engine = SenseVoiceEngine(Path(resolved.model_dir))
            engine = _sensevoice_engine

            def local_transcribe(wav: bytes, language: str, _engine=engine) -> str:
                return _engine.transcribe(wav, language)

        except Exception as exc:
            print(f"SenseVoice 加载失败，本地关闭：{exc}", flush=True)
            if INSTALL_HINT.split()[0] in str(exc) or "onnxruntime" in str(exc).lower():
                hint_uv_sync = True
            resolved = ResolvedLocal(
                ENGINE_OFF, resolved.model_dir, f"sensevoice_load_failed:{exc}"
            )
            local_transcribe = _local_off_transcribe
            local_detail = resolved.skip_reason
    elif resolved.engine == ENGINE_WHISPER:
        model_path = resolve_model_path(config)
        ensure_whisper_files(config, model_path)
        proc = start_whisper(config, internal_port, model_path)
        atexit.register(stop_whisper)
        try:
            wait_until_ready(config, proc, internal_port)
        except Exception:
            stop_whisper()
            raise
        local_transcribe = make_whisper_transcribe(config, internal_port)
        local_detail = model_display_name(model_path)
    else:
        local_transcribe = _local_off_transcribe
        local_detail = resolved.skip_reason or ""
        if "sensevoice_deps_missing" in local_detail:
            hint_uv_sync = True

    endpoint = f"http://{config.bind_host}:{public_port}/v1"
    align = align_custom_provider(endpoint)

    handler = make_handler(
        config,
        active_premium,
        local_transcribe=local_transcribe,
        local_engine_name=resolved.engine,
    )
    try:
        server = ThreadingHTTPServer((config.bind_host, public_port), handler)
    except OSError as exc:
        stop_whisper()
        raise SystemExit(
            f"无法监听 {config.bind_host}:{public_port}（{exc}）。"
            "请先停掉占用该端口的进程，或修改 configs/proxy.json 的 port。"
        ) from exc

    server.daemon_threads = True
    print_startup_banner(
        StartupStatus(
            endpoint=endpoint,
            premium_label=premium_label,
            local_engine=resolved.engine,
            local_detail=local_detail,
            align=align,
            hint_uv_sync=hint_uv_sync,
        )
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在退出…", flush=True)
    finally:
        server.server_close()
        stop_whisper()


def _local_off_transcribe(_wav: bytes, _language: str) -> str:
    raise RuntimeError("local_off")


def make_whisper_transcribe(config: ProxyConfig, internal_port: int):
    inference_url = f"http://{config.bind_host}:{internal_port}/inference"
    inference_timeout = config.whisper.inference_timeout_sec

    def local_transcribe(wav: bytes, language: str) -> str:
        status, body, _content_type = transcribe(
            inference_url, wav, language, inference_timeout
        )
        if status != 200:
            raise RuntimeError(f"whisper-server HTTP {status}: {body[:200]!r}")
        try:
            text = json.loads(body.decode("utf-8")).get("text", "")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"whisper-server 返回的不是 JSON: {exc}") from exc
        if not isinstance(text, str):
            text = str(text)
        return text

    return local_transcribe


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "按 configs/proxy.json 启动本地兜底（SenseVoice 或 whisper-server），"
            "并提供闪电说用的 /v1/chat/completions。"
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=f"代理配置路径，默认 {default_config_path()}",
    )
    return parser.parse_args()


def list_local_model_names(models_dir: Path):
    if not models_dir.is_dir():
        return []
    names = []
    for path in sorted(models_dir.glob("ggml-*.bin")):
        name = path.name
        if name.startswith("ggml-") and name.endswith(".bin"):
            names.append(name[len("ggml-") : -len(".bin")])
    return names


def resolve_model_path(config: ProxyConfig):
    model_arg = config.whisper.model
    candidate = Path(model_arg).expanduser()
    if candidate.is_file():
        return candidate.resolve()

    short_name = model_arg
    if short_name.startswith("ggml-") and short_name.endswith(".bin"):
        short_name = short_name[len("ggml-") : -len(".bin")]
    elif short_name.endswith(".bin"):
        short_name = short_name[: -len(".bin")]

    model_path = config.whisper.models_dir / f"ggml-{short_name}.bin"
    if model_path.is_file():
        return model_path.resolve()

    available = list_local_model_names(config.whisper.models_dir)
    available_text = "、".join(available) if available else "（无）"
    raise SystemExit(
        f"找不到模型：{model_arg}\n"
        f"本地可用短名：{available_text}\n"
        f"也可在 configs/proxy.json 的 whisper.model 里写 ggml 文件路径。"
    )


def model_display_name(model_path: Path):
    name = model_path.name
    if name.startswith("ggml-") and name.endswith(".bin"):
        return name[len("ggml-") : -len(".bin")]
    return name


def model_arg_for_whisper(config: ProxyConfig, model_path: Path):
    try:
        return str(model_path.relative_to(config.whisper.root))
    except ValueError:
        return str(model_path)


def ensure_whisper_files(config: ProxyConfig, model_path: Path):
    if not config.whisper.bin.is_file():
        raise SystemExit(f"找不到 whisper-server：{config.whisper.bin}")
    if not model_path.is_file():
        raise SystemExit(f"找不到模型：{model_path}")


def start_whisper(config: ProxyConfig, internal_port: int, model_path: Path):
    global _whisper_proc
    model_arg = model_arg_for_whisper(config, model_path)
    command = [
        str(config.whisper.bin),
        "-m",
        model_arg,
        "--host",
        config.bind_host,
        "--port",
        str(internal_port),
        "-l",
        config.whisper.language,
    ]
    print(
        f"正在启动 whisper-server（模型 {model_display_name(model_path)}），"
        f"加载可能要几十秒：{' '.join(command)}",
        flush=True,
    )
    _whisper_proc = subprocess.Popen(
        command,
        cwd=config.whisper.root,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    return _whisper_proc


def stop_whisper():
    proc = _whisper_proc
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def wait_until_ready(config: ProxyConfig, proc, internal_port: int):
    url = f"http://{config.bind_host}:{internal_port}/health"
    deadline = time.monotonic() + config.whisper.ready_timeout_sec
    while time.monotonic() < deadline:
        exit_code = proc.poll()
        if exit_code is not None:
            raise SystemExit(f"whisper-server 提前退出，退出码 {exit_code}")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    print("whisper-server 已就绪", flush=True)
                    return
        except urllib.error.HTTPError as exc:
            if exc.code != 503:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            pass
        time.sleep(0.3)
    raise SystemExit(
        f"等待 whisper-server 就绪超过 {config.whisper.ready_timeout_sec:g} 秒"
    )


def make_handler(
    config: ProxyConfig,
    active_premium: ActivePremium | None,
    *,
    local_transcribe,
    local_engine_name: str,
):
    default_language = config.whisper.language

    premium_fn = None
    premium_name = None
    if active_premium is not None:
        premium_name = active_premium.provider.id

        def premium_fn(wav: bytes, language: str):
            return recognize_wav(
                wav,
                language,
                api_key=active_premium.api_key,
                endpoint=active_premium.provider.endpoint,
                resource_id=active_premium.provider.resource_id,
                timeout_sec=active_premium.provider.timeout_sec,
            )

    class ChatCompletionsHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            if self.path.split("?", 1)[0] != "/v1/chat/completions":
                self.send_error_body(404, "not found")
                return
            req_id = request_log.new_request_id()
            try:
                payload = self.read_json()
                wav = extract_wav(payload)
                language = language_from_payload(payload, default_language)
                wav_sec = request_log.estimate_wav_seconds(wav)

                def log_local_later(local_result: dict, rid=req_id) -> None:
                    request_log.emit(
                        request_log.format_local_done(
                            req_id=rid,
                            local_result=local_result,
                            local_engine=local_engine_name,
                        )
                    )

                result = run_dual(
                    wav,
                    language,
                    local_transcribe=local_transcribe,
                    premium_transcribe=premium_fn,
                    premium_provider=premium_name,
                    on_local_settled=log_local_later,
                )
            except ValueError as exc:
                self.send_error_body(400, str(exc))
                return
            except Exception as exc:
                self.send_error_body(502, f"双写转写失败: {exc}")
                return

            request_log.emit(
                request_log.format_asr_summary(
                    req_id=req_id,
                    result=result,
                    wav_bytes=len(wav),
                    wav_sec=wav_sec,
                    local_engine=local_engine_name,
                )
            )
            if result.premium_diag:
                request_log.emit(
                    request_log.format_premium_diag(
                        req_id=req_id, diag=result.premium_diag
                    )
                )

            if result.outcome is DualOutcome.FAILED:
                message = result.error or "本地与高级模型均失败"
                self.send_error_body(502, message)
                return

            write_completion(self, result.text, bool(payload.get("stream")))

        def read_json(self):
            length_header = self.headers.get("Content-Length")
            if length_header is None:
                raise ValueError("缺少 Content-Length")
            try:
                length = int(length_header)
            except ValueError as exc:
                raise ValueError("Content-Length 不是整数") from exc
            if length < 0:
                raise ValueError("Content-Length 无效")
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"请求体不是 JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError("请求体必须是 JSON 对象")
            return payload

        def send_error_body(self, status, message):
            encoded = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
            self.send_raw(status, "application/json; charset=utf-8", encoded)

        def send_raw(self, status, content_type, body):
            self.send_response(status)
            self.send_header("Content-Type", content_type or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            return

    return ChatCompletionsHandler


def extract_wav(payload):
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise ValueError("缺少 messages")
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        parts = content if isinstance(content, list) else [content]
        for part in parts:
            wav = wav_from_part(part)
            if wav is not None:
                return wav
    raise ValueError("请求里没有 input_audio")


def wav_from_part(part):
    if not isinstance(part, dict) or part.get("type") != "input_audio":
        return None
    audio = part.get("input_audio")
    if not isinstance(audio, dict):
        raise ValueError("input_audio 格式不对")
    data = audio.get("data")
    if not isinstance(data, str) or not data:
        raise ValueError("input_audio.data 为空")
    raw, declared = decode_audio_payload(data, audio.get("format"))
    if declared not in {None, "wav"} and declared not in WAV_MIME_TYPES:
        raise ValueError(f"只接受 WAV，收到 {declared}")
    if not (raw.startswith(b"RIFF") and raw[8:12] == b"WAVE"):
        raise ValueError("音频不是 WAV")
    return raw


def decode_audio_payload(data, fmt):
    declared = None
    if isinstance(fmt, str) and fmt.strip():
        declared = fmt.strip().lower()
    encoded = data
    if data.startswith("data:"):
        header, separator, encoded = data.partition(",")
        if not separator:
            raise ValueError("data URL 缺少逗号")
        meta = header[5:]
        mime = meta.split(";", 1)[0].strip().lower()
        declared = mime or declared
        if "base64" not in meta.lower():
            raise ValueError("data URL 不是 base64")
    try:
        raw = base64.b64decode(encoded, validate=False)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"音频 base64 无法解码: {exc}") from exc
    return raw, declared


def language_from_payload(payload, default_language: str = "zh"):
    options = payload.get("asr_options")
    raw = None
    if isinstance(options, dict):
        raw = options.get("language")
    if not isinstance(raw, str) or not raw.strip():
        return default_language
    lang = raw.strip().lower().replace("_", "-")
    if lang in {"zh-cn", "zh-hans", "zh-hant", "chinese", "cmn"} or lang.startswith("zh-"):
        return "zh"
    if "-" in lang:
        return lang.split("-", 1)[0]
    return lang


def transcribe(inference_url, wav, language, timeout_sec: float):
    body, content_type = encode_multipart(
        {"response_format": "json", "language": language},
        wav,
    )
    request = urllib.request.Request(
        inference_url,
        data=body,
        headers={"Content-Type": content_type},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            return (
                response.status,
                response.read(),
                response.headers.get("Content-Type", "application/json"),
            )
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers.get("Content-Type", "text/plain")


def encode_multipart(fields, wav):
    boundary = "----whisperproxy" + uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        chunks.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )
    chunks.append(
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
            "Content-Type: audio/wav\r\n\r\n"
        ).encode("utf-8")
        + wav
        + b"\r\n"
    )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def write_completion(handler, text, stream):
    completion_id = "chatcmpl-" + uuid.uuid4().hex
    if stream:
        created = int(time.time())
        first = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": text},
                    "finish_reason": None,
                }
            ],
        }
        done = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        payload = (
            f"data: {json.dumps(first, ensure_ascii=False)}\n\n"
            f"data: {json.dumps(done, ensure_ascii=False)}\n\n"
            "data: [DONE]\n\n"
        ).encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Content-Length", str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)
        return

    body = json.dumps(
        {
            "id": completion_id,
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    handler.send_raw(200, "application/json; charset=utf-8", body)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        stop_whisper()
        sys.exit(0)
