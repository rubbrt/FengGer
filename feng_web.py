"""Local web studio for Qwen copy, feng_voice TTS, memes, and storyboards."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel, Field

from gpt_sovits_demo import GPT_WEIGHTS, REFERENCE_AUDIO, SOVITS_WEIGHTS
from qianwen_demo import build_message, generate_answer
from qianwen_local_tts import backup_generated_text, synthesize_answer


PROJECT_DIR = Path(__file__).resolve().parent
WEB_DIR = PROJECT_DIR / "web"
ASSET_DIR = PROJECT_DIR / "峰哥表情包"
OUTPUT_DIR = PROJECT_DIR / "output"
VIDEO_OUTPUT_DIR = OUTPUT_DIR / "videos"
VIDEO_RENDERER_DIR = PROJECT_DIR / "video_renderer"
VIDEO_TEMPLATE_VERSION = "documentary-v2"
FFMPEG_PATH = Path(r"D:\ANAconda\Library\bin\ffmpeg.exe")
NPX_PATH = Path(r"D:\ANAconda\npx.cmd")

ASSETS = tuple(
    sorted(
        (
            path
            for path in ASSET_DIR.iterdir()
            if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        ),
        key=lambda path: path.name,
    )
)

app = FastAPI(title="峰言峰语工作台", version="0.1.0")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

TTS_LOCK = asyncio.Lock()
RENDER_LOCK = asyncio.Lock()


class GenerateRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    attempt: int = Field(default=1, ge=1, le=100)


class QwenSettingsRequest(BaseModel):
    api_key: str = Field(min_length=8, max_length=500)


class TtsRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1)


class StoryboardRequest(BaseModel):
    answer: str = Field(min_length=1)
    duration_seconds: float = Field(gt=0, le=3600)
    max_chars: int = Field(default=38, ge=12, le=80)


class StoryboardScene(BaseModel):
    id: str
    text: str
    asset_id: int
    start_seconds: float
    duration_seconds: float


class RenderRequest(BaseModel):
    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    audio_path: str
    topic: str = Field(min_length=1, max_length=500)
    aspect_ratio: Literal["16:9", "9:16"] = "16:9"
    scenes: list[StoryboardScene] = Field(min_length=1, max_length=200)


def _client() -> OpenAI:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="没有找到 DASHSCOPE_API_KEY 环境变量。",
        )
    return OpenAI(
        api_key=api_key,
        base_url=os.getenv(
            "QWEN_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
    )


def _relative_output_url(path: Path) -> str:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(OUTPUT_DIR.resolve())
    except ValueError as error:
        raise RuntimeError(f"输出文件不在 output 目录内：{resolved}") from error
    return "/api/output/" + "/".join(relative.parts)


def _safe_child(root: Path, relative_path: str) -> Path:
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as error:
        raise HTTPException(status_code=404, detail="文件不存在。") from error
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="文件不存在。")
    return candidate


def _split_storyboard_text(text: str, max_chars: int) -> list[str]:
    cleaned = text.strip().removeprefix("“").removesuffix("”").strip()
    sentences = [
        part.strip()
        for part in re.findall(r".+?(?:[。！？!?；;]|$)", cleaned, flags=re.S)
        if part.strip()
    ]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if not current:
            current = sentence
            continue
        if len(current) + len(sentence) <= max_chars:
            current += sentence
        else:
            chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)

    # Very long punctuation-free passages still need usable scene cards.
    normalized: list[str] = []
    for chunk in chunks:
        if len(chunk) <= max_chars * 2:
            normalized.append(chunk)
            continue
        normalized.extend(
            chunk[index : index + max_chars]
            for index in range(0, len(chunk), max_chars)
        )
    return normalized or [cleaned]


def _storyboard(answer: str, duration_seconds: float, max_chars: int) -> list[dict]:
    chunks = _split_storyboard_text(answer, max_chars)
    weights = [max(1, len(re.sub(r"\s+", "", chunk))) for chunk in chunks]
    total_weight = sum(weights)
    cursor = 0.0
    previous_asset = -1
    scenes: list[dict] = []

    for index, (chunk, weight) in enumerate(zip(chunks, weights, strict=True)):
        duration = duration_seconds * weight / total_weight
        digest = hashlib.sha256(f"{index}:{chunk}".encode("utf-8")).digest()
        asset_id = int.from_bytes(digest[:4], "big") % len(ASSETS)
        if asset_id == previous_asset and len(ASSETS) > 1:
            asset_id = (asset_id + 1) % len(ASSETS)
        previous_asset = asset_id
        scenes.append(
            {
                "id": f"scene-{index + 1:02d}",
                "text": chunk,
                "asset_id": asset_id,
                "start_seconds": round(cursor, 3),
                "duration_seconds": round(duration, 3),
            }
        )
        cursor += duration

    # Make the rounded final scene land exactly on the audio duration.
    scenes[-1]["duration_seconds"] = round(
        duration_seconds - scenes[-1]["start_seconds"],
        3,
    )
    return scenes


@app.get("/")
def home() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/production")
def production_page() -> FileResponse:
    return FileResponse(WEB_DIR / "production.html")


@app.get("/api/status")
def status() -> dict:
    return {
        "qwen_ready": bool(os.getenv("DASHSCOPE_API_KEY")),
        "tts_ready": all(
            path.is_file() for path in (GPT_WEIGHTS, SOVITS_WEIGHTS, REFERENCE_AUDIO)
        ),
        "asset_count": len(ASSETS),
        "renderer_ready": VIDEO_RENDERER_DIR.is_dir()
        and NPX_PATH.is_file()
        and FFMPEG_PATH.is_file(),
        "model": os.getenv("QWEN_MODEL", "qwen-plus"),
        "voice": "feng_voice v2Pro",
    }


@app.post("/api/settings/qwen")
def configure_qwen(payload: QwenSettingsRequest) -> dict:
    """Keep the key only in the current local server process."""
    os.environ["DASHSCOPE_API_KEY"] = payload.api_key.strip()
    return {"ok": True, "model": os.getenv("QWEN_MODEL", "qwen-plus")}


@app.get("/api/assets")
def list_assets() -> dict:
    return {
        "items": [
            {
                "id": index,
                "filename": path.name,
                "url": f"/api/assets/{index}",
            }
            for index, path in enumerate(ASSETS)
        ]
    }


@app.get("/api/assets/{asset_id}")
def asset_file(asset_id: int) -> FileResponse:
    if asset_id < 0 or asset_id >= len(ASSETS):
        raise HTTPException(status_code=404, detail="素材不存在。")
    return FileResponse(ASSETS[asset_id])


@app.get("/api/output/{relative_path:path}")
def output_file(relative_path: str) -> FileResponse:
    return FileResponse(
        _safe_child(OUTPUT_DIR, relative_path),
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.post("/api/generate")
async def generate(payload: GenerateRequest) -> dict:
    question = payload.question.strip()
    try:
        answer = await run_in_threadpool(
            generate_answer,
            _client(),
            build_message(question),
            payload.attempt,
        )
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"调用千问失败：{error}") from error
    return {"answer": answer, "attempt": payload.attempt}


@app.post("/api/tts")
async def tts(payload: TtsRequest) -> dict:
    async with TTS_LOCK:
        backup = backup_generated_text(payload.answer)
        try:
            result = await run_in_threadpool(
                synthesize_answer,
                payload.answer,
                backup,
                source_question=payload.question,
            )
        except Exception as error:
            raise HTTPException(
                status_code=500,
                detail=f"语音合成失败，文本备份已保留：{error}",
            ) from error

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    return {
        "run_id": result.audio_path.parent.name,
        "audio_url": _relative_output_url(result.audio_path),
        "manifest_url": _relative_output_url(result.manifest_path),
        "text_backup": str(backup.path),
        "duration_seconds": manifest["audio"]["duration_seconds"],
    }


@app.post("/api/storyboard")
def storyboard(payload: StoryboardRequest) -> dict:
    return {
        "scenes": _storyboard(
            payload.answer,
            payload.duration_seconds,
            payload.max_chars,
        )
    }


def _render_video(payload: RenderRequest) -> Path:
    """Prepare and render one HyperFrames project. Called behind RENDER_LOCK."""
    if not VIDEO_RENDERER_DIR.is_dir():
        raise RuntimeError("视频渲染器尚未初始化。")
    audio_file = _safe_child(OUTPUT_DIR, payload.audio_path.removeprefix("/api/output/"))
    import video_composer

    # The local studio is long-lived. Reload the generator on every render so
    # template edits on disk cannot be shadowed by an older imported module.
    importlib.invalidate_caches()
    video_composer = importlib.reload(video_composer)

    project_dir = video_composer.prepare_hyperframes_project(
        renderer_root=VIDEO_RENDERER_DIR,
        run_id=payload.run_id,
        audio_path=audio_file,
        aspect_ratio=payload.aspect_ratio,
        quote_topic=payload.topic,
        scenes=[scene.model_dump() for scene in payload.scenes],
        assets=ASSETS,
    )
    VIDEO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = (
        VIDEO_OUTPUT_DIR / f"{payload.run_id}_{VIDEO_TEMPLATE_VERSION}.mp4"
    ).resolve()
    env = os.environ.copy()
    env["PATH"] = (
        str(FFMPEG_PATH.parent)
        + os.pathsep
        + str(NPX_PATH.parent)
        + os.pathsep
        + env.get("PATH", "")
    )
    command = [
        str(NPX_PATH),
        "--yes",
        "hyperframes@0.7.25",
        "render",
        "--quality=high",
        "--strict",
        f"--output={output_path}",
    ]
    completed = subprocess.run(
        command,
        cwd=project_dir,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=1800,
        check=False,
    )
    if completed.returncode != 0 or not output_path.is_file():
        details = (completed.stderr or completed.stdout)[-4000:]
        raise RuntimeError(details or "视频渲染失败。")
    return output_path


@app.post("/api/render")
async def render(payload: RenderRequest) -> dict:
    async with RENDER_LOCK:
        try:
            output_path = await run_in_threadpool(_render_video, payload)
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(status_code=500, detail=f"视频生成失败：{error}") from error
    cache_version = output_path.stat().st_mtime_ns
    return {
        "video_url": f"{_relative_output_url(output_path)}?v={cache_version}",
        "template_version": VIDEO_TEMPLATE_VERSION,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("feng_web:app", host="127.0.0.1", port=7860, reload=False)
