#!/usr/bin/env python3
"""Live smoke test: Gemini Indonesian TTS audio is transcribed by Gemini Live STT."""

from __future__ import annotations

import asyncio
import base64
import json
import subprocess
import sys
import time
import wave
from array import array
from io import BytesIO
from pathlib import Path

import httpx
from websockets.asyncio.client import connect

ROOT = Path(__file__).resolve().parents[1]
API = "http://127.0.0.1:8000"


def api_ready() -> bool:
    try:
        return httpx.get(f"{API}/health", timeout=1, trust_env=False).is_success
    except httpx.HTTPError:
        return False


def ensure_api() -> subprocess.Popen[bytes] | None:
    if api_ready():
        return None
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.api.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("API lokal berhenti saat tes suara sedang disiapkan.")
        if api_ready():
            return process
        time.sleep(0.25)
    process.terminate()
    raise RuntimeError("API lokal belum siap setelah 25 detik.")


def resample_mono_pcm16(audio: bytes, source_rate: int, target_rate: int = 16_000) -> bytes:
    samples = array("h")
    samples.frombytes(audio)
    if source_rate == target_rate:
        return samples.tobytes()
    output = array("h")
    target_length = max(1, round(len(samples) * target_rate / source_rate))
    for index in range(target_length):
        source_index = min(len(samples) - 1, round(index * source_rate / target_rate))
        output.append(samples[source_index])
    return output.tobytes()


async def transcribe(study_id: str, pcm: bytes) -> str:
    uri = f"ws://127.0.0.1:8000/api/voice/live-transcription?study_session_id={study_id}"
    async with connect(uri, max_size=8 * 1024 * 1024) as websocket:
        while True:
            message = json.loads(await asyncio.wait_for(websocket.recv(), timeout=15))
            if message.get("type") == "ready":
                break
        chunk_size = 3_200
        for offset in range(0, len(pcm), chunk_size):
            chunk = pcm[offset : offset + chunk_size]
            await websocket.send(json.dumps({"audio": base64.b64encode(chunk).decode()}))
            await asyncio.sleep(0.04)
        silence = bytes(3_200)
        for _ in range(12):
            await websocket.send(json.dumps({"audio": base64.b64encode(silence).decode()}))
            await asyncio.sleep(0.05)
        while True:
            message = json.loads(await asyncio.wait_for(websocket.recv(), timeout=20))
            if message.get("type") == "error":
                raise RuntimeError(str(message.get("message")))
            if message.get("type") == "final" and message.get("text"):
                return str(message["text"]).strip()


async def main() -> int:
    api_process = ensure_api()
    try:
        artifact_dir = ROOT / ".runtime" / "test-artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        with httpx.Client(base_url=API, timeout=60, trust_env=False) as client:
            session = client.post("/api/study/automatic", json={"condition_id": "C0"})
            session.raise_for_status()
            study_id = session.json()["study_session_id"]
            speech = client.post(
                "/api/voice/speech",
                json={"text": "Iya, saya siap. Tolong lanjut ke kegiatan berikutnya."},
            )
            speech.raise_for_status()
            wav_bytes = speech.content
            (artifact_dir / "tts-indonesia-live-check.wav").write_bytes(wav_bytes)

        with wave.open(BytesIO(wav_bytes), "rb") as source:
            if source.getsampwidth() != 2 or source.getnchannels() != 1:
                raise RuntimeError("TTS tidak menghasilkan PCM16 mono.")
            pcm = resample_mono_pcm16(
                source.readframes(source.getnframes()), source.getframerate()
            )
        transcript = await transcribe(study_id, pcm)
        normalized = transcript.casefold()
        words = set(normalized.replace(",", "").replace(".", "").split())
        if "lanjut" not in normalized or not ({"iya", "ya"} & words):
            raise RuntimeError(f"Transkrip live tidak sesuai: {transcript}")
        print(f"PASS live TTS -> STT: {transcript}")
        return 0
    finally:
        if api_process is not None:
            api_process.terminate()
            try:
                api_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                api_process.kill()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
