"""豆包 SAUC bigmodel_nostream 客户端（标准库 WebSocket + 二进制帧）。

参数由调用方传入；本模块不读 configs/，也不读环境变量。
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import socket
import ssl
import struct
import time
import uuid
from typing import Callable
from urllib.parse import urlparse

from .select import PremiumFailure

PROTOCOL_VERSION = 0b0001
HEADER_SIZE = 0b0001
FULL_CLIENT = 0b0001
AUDIO_ONLY = 0b0010
FULL_SERVER = 0b1001
ERROR_RESP = 0b1111
NO_SERIAL = 0b0000
JSON_SERIAL = 0b0001
GZIP = 0b0001

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def recognize_wav(
    wav: bytes,
    language: str,
    *,
    api_key: str,
    endpoint: str,
    resource_id: str,
    timeout_sec: float,
    connect: Callable[..., "WebSocketClient"] | None = None,
) -> str:
    """整段 WAV 一句话识别；成功返回 result.text（可为空字符串）。"""
    deadline = time.monotonic() + timeout_sec
    connector = connect or WebSocketClient.connect
    headers = {
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": str(uuid.uuid4()),
        "X-Api-Connect-Id": str(uuid.uuid4()),
    }
    try:
        ws = connector(endpoint, headers=headers, timeout_sec=_remaining(deadline))
    except PremiumFailure:
        raise
    except Exception as exc:  # noqa: BLE001
        raise PremiumFailure("network", f"连接豆包失败：{exc}") from exc

    try:
        # full client 占用 sequence=1；随后音频包从 2 起算。
        # 整段一次发完时末包必须为 -2，否则服务端报 sequence mismatch。
        ws.send_binary(build_full_client(language_to_doubao(language)))
        _recv_until_server(ws, deadline, expect_text=False)
        ws.send_binary(build_audio_only(wav, seq=2, last=True))
        return _recv_until_final_text(ws, deadline)
    finally:
        ws.close()


def language_to_doubao(language: str) -> str:
    lang = (language or "zh").strip().lower().replace("_", "-")
    if lang in {"zh", "zh-cn", "zh-hans", "chinese", "cmn"} or lang.startswith("zh-"):
        return "zh-CN"
    if lang in {"en", "en-us", "english"}:
        return "en-US"
    if "-" in lang:
        return language
    return language


def build_full_client(language: str) -> bytes:
    params = {
        "user": {"uid": "asr-proxy"},
        "audio": {
            "format": "wav",
            "codec": "raw",
            "rate": 16000,
            "bits": 16,
            "channel": 1,
            "language": language,
        },
        "request": {
            "model_name": "bigmodel",
            "enable_punc": True,
            "enable_itn": True,
            "enable_ddc": False,
            "show_utterances": False,
            "result_type": "full",
        },
    }
    body = gzip.compress(json.dumps(params, ensure_ascii=False).encode("utf-8"))
    return (
        _sauc_header(FULL_CLIENT, 0b0001, JSON_SERIAL, GZIP)
        + struct.pack(">i", 1)
        + struct.pack(">I", len(body))
        + body
    )


def build_audio_only(chunk: bytes, *, seq: int, last: bool) -> bytes:
    body = gzip.compress(chunk)
    if last:
        flags = 0b0011
        seq_value = -abs(seq)
    else:
        flags = 0b0001
        seq_value = abs(seq)
    return (
        _sauc_header(AUDIO_ONLY, flags, NO_SERIAL, GZIP)
        + struct.pack(">i", seq_value)
        + struct.pack(">I", len(body))
        + body
    )


def parse_sauc_frame(data: bytes) -> tuple[str, int | None, int, object]:
    if len(data) < 4:
        raise PremiumFailure("protocol", "豆包响应帧过短")
    header_size = (data[0] & 0x0F) * 4
    msg_type = data[1] >> 4
    flags = data[1] & 0x0F
    compression = data[2] & 0x0F
    rest = data[header_size:]

    if msg_type == ERROR_RESP:
        if len(rest) < 8:
            raise PremiumFailure("protocol", "豆包错误帧过短")
        code = struct.unpack(">I", rest[:4])[0]
        size = struct.unpack(">I", rest[4:8])[0]
        payload = rest[8 : 8 + size]
        if compression == GZIP and payload:
            try:
                payload = gzip.decompress(payload)
            except OSError:
                pass
        message = payload.decode("utf-8", "replace")
        raise PremiumFailure("protocol", f"豆包错误 {code}: {message}")

    if msg_type == FULL_SERVER:
        seq = None
        if flags & 0b0001:
            if len(rest) < 4:
                raise PremiumFailure("protocol", "豆包响应缺少 sequence")
            seq = struct.unpack(">i", rest[:4])[0]
            rest = rest[4:]
        if len(rest) < 4:
            raise PremiumFailure("protocol", "豆包响应缺少 payload size")
        size = struct.unpack(">I", rest[:4])[0]
        body = rest[4 : 4 + size]
        if compression == GZIP and body:
            try:
                body = gzip.decompress(body)
            except OSError as exc:
                raise PremiumFailure("protocol", f"豆包响应无法解压：{exc}") from exc
        if not body:
            return ("SERVER", seq, flags, {})
        try:
            obj = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PremiumFailure("protocol", f"豆包响应不是 JSON：{exc}") from exc
        return ("SERVER", seq, flags, obj)

    return ("OTHER", None, flags, data[:16].hex())


def extract_text(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    result = payload.get("result")
    if isinstance(result, dict):
        text = result.get("text")
        if isinstance(text, str):
            return text
    if isinstance(result, list) and result:
        first = result[0]
        if isinstance(first, dict) and isinstance(first.get("text"), str):
            return first["text"]
    return None


def _sauc_header(msg_type: int, flags: int, serial: int, compression: int) -> bytes:
    return bytes(
        [
            (PROTOCOL_VERSION << 4) | HEADER_SIZE,
            (msg_type << 4) | flags,
            (serial << 4) | compression,
            0x00,
        ]
    )


def _remaining(deadline: float) -> float:
    left = deadline - time.monotonic()
    if left <= 0:
        raise PremiumFailure("timeout", "豆包识别超时")
    return left


def _recv_until_server(
    ws: "WebSocketClient",
    deadline: float,
    *,
    expect_text: bool,
) -> str:
    text = ""
    while True:
        frame = ws.recv_binary(_remaining(deadline))
        kind, _seq, flags, body = parse_sauc_frame(frame)
        if kind != "SERVER":
            continue
        got = extract_text(body)
        if got is not None:
            text = got
        if expect_text:
            if flags & 0b0010:
                return text
            continue
        return text


def _recv_until_final_text(ws: "WebSocketClient", deadline: float) -> str:
    text = ""
    while True:
        frame = ws.recv_binary(_remaining(deadline))
        kind, _seq, flags, body = parse_sauc_frame(frame)
        if kind != "SERVER":
            continue
        got = extract_text(body)
        if got is not None:
            text = got
        if flags & 0b0010:
            return text


class WebSocketClient:
    """最小客户端：握手、掩码二进制帧、自动应答 ping。"""

    def __init__(self, sock: ssl.SSLSocket | socket.socket):
        self._sock = sock
        self._buffer = bytearray()
        self._closed = False

    @classmethod
    def connect(
        cls,
        endpoint: str,
        *,
        headers: dict[str, str],
        timeout_sec: float,
    ) -> "WebSocketClient":
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"wss", "ws"}:
            raise PremiumFailure("protocol", f"不支持的 endpoint：{endpoint}")
        host = parsed.hostname
        if not host:
            raise PremiumFailure("protocol", f"endpoint 缺少主机名：{endpoint}")
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        raw = socket.create_connection((host, port), timeout=timeout_sec)
        raw.settimeout(timeout_sec)
        if parsed.scheme == "wss":
            context = ssl.create_default_context()
            try:
                sock = context.wrap_socket(raw, server_hostname=host)
            except ssl.SSLError as exc:
                raw.close()
                raise PremiumFailure("network", f"TLS 握手失败：{exc}") from exc
        else:
            sock = raw

        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request_lines = [
            f"GET {path} HTTP/1.1",
            f"Host: {host}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}",
            "Sec-WebSocket-Version: 13",
        ]
        for name, value in headers.items():
            request_lines.append(f"{name}: {value}")
        request_lines.append("")
        request_lines.append("")
        try:
            sock.sendall("\r\n".join(request_lines).encode("utf-8"))
            response = _read_http_response(sock, timeout_sec)
        except PremiumFailure:
            sock.close()
            raise
        except Exception as exc:  # noqa: BLE001
            sock.close()
            raise PremiumFailure("network", f"WebSocket 握手失败：{exc}") from exc

        status_line = response.split(b"\r\n", 1)[0].decode("latin1", "replace")
        parts = status_line.split(" ", 2)
        status = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
        if status in {401, 403}:
            sock.close()
            raise PremiumFailure("auth", f"豆包鉴权失败：HTTP {status}")
        if status != 101:
            sock.close()
            raise PremiumFailure(
                "network" if status == 0 else "protocol",
                f"WebSocket 握手失败：{status_line}",
            )

        expected = base64.b64encode(
            hashlib.sha1((key + WS_GUID).encode("ascii")).digest()
        ).decode("ascii")
        accept = _header_value(response, "Sec-WebSocket-Accept")
        if accept != expected:
            sock.close()
            raise PremiumFailure("protocol", "Sec-WebSocket-Accept 不匹配")
        return cls(sock)

    def send_binary(self, payload: bytes) -> None:
        self._send_frame(0x2, payload)

    def recv_binary(self, timeout_sec: float) -> bytes:
        deadline = time.monotonic() + timeout_sec
        while True:
            opcode, payload = self._recv_frame(_remaining(deadline))
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            if opcode == 0x8:
                raise PremiumFailure("network", "豆包 WebSocket 已关闭")
            if opcode == 0x2:
                return payload
            if opcode == 0x1:
                raise PremiumFailure("protocol", "收到文本帧，期望二进制帧")
            raise PremiumFailure("protocol", f"未支持的 WebSocket opcode：{opcode}")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._send_frame(0x8, b"")
        except Exception:  # noqa: BLE001
            pass
        try:
            self._sock.close()
        except Exception:  # noqa: BLE001
            pass

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        length = len(payload)
        header = bytearray()
        header.append(0x80 | (opcode & 0x0F))
        mask_bit = 0x80
        if length < 126:
            header.append(mask_bit | length)
        elif length < (1 << 16):
            header.append(mask_bit | 126)
            header.extend(struct.pack(">H", length))
        else:
            header.append(mask_bit | 127)
            header.extend(struct.pack(">Q", length))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        try:
            self._sock.sendall(header + masked)
        except OSError as exc:
            raise PremiumFailure("network", f"发送失败：{exc}") from exc

    def _recv_frame(self, timeout_sec: float) -> tuple[int, bytes]:
        deadline = time.monotonic() + timeout_sec
        header = self._read_exact(2, _remaining(deadline))
        opcode = header[0] & 0x0F
        masked = bool(header[1] & 0x80)
        length = header[1] & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._read_exact(2, _remaining(deadline)))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._read_exact(8, _remaining(deadline)))[0]
        mask = self._read_exact(4, _remaining(deadline)) if masked else b""
        payload = self._read_exact(length, _remaining(deadline))
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return opcode, payload

    def _read_exact(self, size: int, timeout_sec: float) -> bytes:
        deadline = time.monotonic() + timeout_sec
        while len(self._buffer) < size:
            left = _remaining(deadline)
            self._sock.settimeout(left)
            try:
                chunk = self._sock.recv(65536)
            except socket.timeout as exc:
                raise PremiumFailure("timeout", "豆包识别超时") from exc
            except OSError as exc:
                raise PremiumFailure("network", f"接收失败：{exc}") from exc
            if not chunk:
                raise PremiumFailure("network", "连接在读帧时关闭")
            self._buffer.extend(chunk)
        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        return data


def _read_http_response(sock: socket.socket, timeout_sec: float) -> bytes:
    deadline = time.monotonic() + timeout_sec
    buffer = bytearray()
    while b"\r\n\r\n" not in buffer:
        left = _remaining(deadline)
        sock.settimeout(left)
        try:
            chunk = sock.recv(4096)
        except socket.timeout as exc:
            raise PremiumFailure("timeout", "WebSocket 握手超时") from exc
        except OSError as exc:
            raise PremiumFailure("network", f"WebSocket 握手读失败：{exc}") from exc
        if not chunk:
            raise PremiumFailure("network", "WebSocket 握手连接关闭")
        buffer.extend(chunk)
        if len(buffer) > 65536:
            raise PremiumFailure("protocol", "WebSocket 握手响应过长")
    end = buffer.index(b"\r\n\r\n") + 4
    return bytes(buffer[:end])


def _header_value(response: bytes, name: str) -> str | None:
    target = name.lower()
    for line in response.split(b"\r\n")[1:]:
        if not line:
            break
        if b":" not in line:
            continue
        key, value = line.split(b":", 1)
        if key.decode("latin1", "replace").strip().lower() == target:
            return value.decode("latin1", "replace").strip()
    return None
