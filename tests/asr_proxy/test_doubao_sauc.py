import base64
import gzip
import hashlib
import json
import socket
import struct
import threading
import unittest
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from asr_proxy.doubao_sauc import (
    WS_GUID,
    WebSocketClient,
    build_audio_only,
    build_full_client,
    extract_text,
    language_to_doubao,
    parse_sauc_frame,
    recognize_wav,
)
from asr_proxy.select import PremiumFailure


def _sauc_header(msg_type: int, flags: int, serial: int, compression: int) -> bytes:
    return bytes(
        [
            (0b0001 << 4) | 0b0001,
            (msg_type << 4) | flags,
            (serial << 4) | compression,
            0x00,
        ]
    )


def _server_full(text: str, *, final: bool) -> bytes:
    payload = gzip.compress(
        json.dumps({"result": {"text": text}}, ensure_ascii=False).encode("utf-8")
    )
    flags = 0b0011 if final else 0b0001
    return (
        _sauc_header(0b1001, flags, 0b0001, 0b0001)
        + struct.pack(">i", 1)
        + struct.pack(">I", len(payload))
        + payload
    )


def _ws_accept(key: str) -> str:
    digest = hashlib.sha1((key + WS_GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def _read_ws_frame(conn: socket.socket) -> bytes:
    header = conn.recv(2)
    while len(header) < 2:
        chunk = conn.recv(2 - len(header))
        if not chunk:
            raise RuntimeError("client closed")
        header += chunk
    length = header[1] & 0x7F
    masked = bool(header[1] & 0x80)
    if length == 126:
        length = struct.unpack(">H", conn.recv(2))[0]
    elif length == 127:
        length = struct.unpack(">Q", conn.recv(8))[0]
    mask = conn.recv(4) if masked else b""
    payload = b""
    while len(payload) < length:
        chunk = conn.recv(length - len(payload))
        if not chunk:
            raise RuntimeError("client closed mid-frame")
        payload += chunk
    if masked:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return payload


def _send_ws_frame(conn: socket.socket, payload: bytes) -> None:
    header = bytearray([0x82])
    length = len(payload)
    if length < 126:
        header.append(length)
    elif length < 1 << 16:
        header.append(126)
        header.extend(struct.pack(">H", length))
    else:
        header.append(127)
        header.extend(struct.pack(">Q", length))
    conn.sendall(header + payload)


class DoubaoSaucUnitTests(unittest.TestCase):
    def test_language_mapping(self):
        self.assertEqual(language_to_doubao("zh"), "zh-CN")
        self.assertEqual(language_to_doubao("en"), "en-US")

    def test_build_and_parse_roundtrip_text(self):
        frame = build_full_client("zh-CN")
        self.assertGreater(len(frame), 8)
        audio = build_audio_only(b"RIFFWAVEdata", seq=2, last=True)
        self.assertEqual(audio[1] & 0x0F, 0b0011)
        seq = struct.unpack(">i", audio[4:8])[0]
        self.assertEqual(seq, -2)

        server = _server_full("你好", final=True)
        kind, _seq, flags, body = parse_sauc_frame(server)
        self.assertEqual(kind, "SERVER")
        self.assertTrue(flags & 0b0010)
        self.assertEqual(extract_text(body), "你好")

    def test_fake_websocket_recognize(self):
        server = socket.socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        host, port = server.getsockname()
        ready = threading.Event()
        errors = []

        def serve():
            try:
                conn, _addr = server.accept()
                with conn:
                    request = b""
                    while b"\r\n\r\n" not in request:
                        request += conn.recv(4096)
                    headers = {}
                    for line in request.split(b"\r\n")[1:]:
                        if not line or b":" not in line:
                            continue
                        key, value = line.split(b":", 1)
                        headers[key.decode().lower()] = value.decode().strip()
                    if headers.get("x-api-key") != "test-key":
                        raise AssertionError("missing api key")
                    accept = _ws_accept(headers["sec-websocket-key"])
                    response = (
                        "HTTP/1.1 101 Switching Protocols\r\n"
                        "Upgrade: websocket\r\n"
                        "Connection: Upgrade\r\n"
                        f"Sec-WebSocket-Accept: {accept}\r\n"
                        "\r\n"
                    )
                    conn.sendall(response.encode("utf-8"))
                    ready.set()
                    _ = _read_ws_frame(conn)
                    _send_ws_frame(conn, _server_full("", final=False))
                    _ = _read_ws_frame(conn)
                    _send_ws_frame(conn, _server_full("豆包结果", final=True))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                ready.set()

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        text = recognize_wav(
            b"RIFF....WAVE",
            "zh",
            api_key="test-key",
            endpoint=f"ws://127.0.0.1:{port}/api/v3/sauc/bigmodel_nostream",
            resource_id="volc.seedasr.sauc.duration",
            timeout_sec=3,
            connect=WebSocketClient.connect,
        )
        thread.join(timeout=3)
        server.close()
        self.assertEqual(errors, [])
        self.assertEqual(text, "豆包结果")

    def test_auth_401(self):
        server = socket.socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        host, port = server.getsockname()

        def serve():
            conn, _addr = server.accept()
            with conn:
                request = b""
                while b"\r\n\r\n" not in request:
                    request += conn.recv(4096)
                conn.sendall(b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\n\r\n")

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        with self.assertRaises(PremiumFailure) as ctx:
            recognize_wav(
                b"RIFF",
                "zh",
                api_key="bad",
                endpoint=f"ws://127.0.0.1:{port}/x",
                resource_id="rid",
                timeout_sec=2,
            )
        thread.join(timeout=2)
        server.close()
        self.assertEqual(ctx.exception.kind, "auth")


if __name__ == "__main__":
    unittest.main()
