"""把 qianwen_demo 的文本备份、分段合成、裁静音并拼接为 WAV。"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
import re
import shutil
import subprocess
import sys
import wave

import requests


PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_DIR / "output"
TEXT_BACKUP_DIR = OUTPUT_DIR / "text_backup"
TTS_RUNS_DIR = OUTPUT_DIR / "tts"
VOICE_ID_FILE = OUTPUT_DIR / "voice_id.txt"

CREATE_SPEECH_URL = (
    "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
)
VOICE_MODEL = "qwen3-tts-vc-2026-01-22"
SAMPLE_RATE = 24_000


@dataclass(frozen=True)
class TextBackup:
    """一次文本生成对应的原始备份信息。"""

    run_id: str
    path: Path
    created_at: str


@dataclass(frozen=True)
class SpeechSegment:
    """一段需要单独合成的文字及其后面的静音长度。"""

    index: int
    text: str
    pause_after_ms: int
    paragraph_end: bool


@dataclass(frozen=True)
class TtsResult:
    """最终语音和便于复盘的清单路径。"""

    run_id: str
    audio_path: Path
    manifest_path: Path


def _timestamp() -> str:
    """生成精确到毫秒的时间戳，作为每次保存的基础文件名。"""
    return datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")[:-3]


def _new_run_id() -> str:
    """挑选一个当前尚未使用的运行编号，避免任何文件被覆盖。"""
    base = f"qianwen_{_timestamp()}"
    for number in range(1, 1000):
        suffix = "" if number == 1 else f"_{number:02d}"
        run_id = base + suffix
        backup_path = TEXT_BACKUP_DIR / f"{run_id}.txt"
        tts_path = TTS_RUNS_DIR / run_id
        if not backup_path.exists() and not tts_path.exists():
            return run_id
    raise RuntimeError("无法分配新的保存编号，请稍后重试。")


def backup_generated_text(answer: str) -> TextBackup:
    """把模型的原始返回文本原样存到专用备份目录。"""
    if not answer or not answer.strip():
        raise ValueError("没有可备份的文本。")

    run_id = _new_run_id()
    TEXT_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = TEXT_BACKUP_DIR / f"{run_id}.txt"
    if path.exists():
        raise FileExistsError(f"备份文件已经存在，不会覆盖：{path}")
    path.write_text(answer, encoding="utf-8")

    return TextBackup(
        run_id=run_id,
        path=path.resolve(),
        created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
    )


def _load_voice_id() -> str:
    """读取从 qwen_tts_demo 复制过来的已创建音色。"""
    if not VOICE_ID_FILE.is_file():
        raise FileNotFoundError(f"找不到 Voice ID 文件：{VOICE_ID_FILE}")

    voice_id = VOICE_ID_FILE.read_text(encoding="utf-8-sig").strip()
    if not voice_id:
        raise ValueError("voice_id.txt 为空。")
    return voice_id


def _speech_text(answer: str) -> str:
    """去掉仅用于排版的标记，保留真正需要朗读的文字。"""
    cleaned = answer.strip().replace("```text", "").replace("```", "").strip()
    lines: list[str] = []
    for line in cleaned.splitlines():
        line = line.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        # 即使模型偶尔输出结构标签，也不让 TTS 念出“读题”“回应”。
        line = line.replace("【读题】", "").replace("【回应】", "").strip()
        if line:
            lines.append(line)

    result = "\n".join(lines).strip()
    if not result:
        raise ValueError("去除排版标记后没有可朗读的文字。")
    return result


def _ending_mark(text: str) -> str:
    """返回末尾实际标点；右引号和括号不影响判断。"""
    return text.rstrip("”’）)】").rstrip()[-1:]


def _default_pause(text: str, *, paragraph_end: bool) -> int:
    """统一管理停顿规则，避免 TTS 自己留下不稳定的句间空白。"""
    if paragraph_end:
        return 700

    mark = _ending_mark(text)
    if mark in {"，", "、", "："}:
        return 200
    if mark in {"；", ";"}:
        return 400
    if mark in {"？", "?", "！", "!"}:
        return 500
    # 普通句号或被长度规则切开的片段，保留中等停顿。
    return 400


def _clause_parts(paragraph: str) -> list[str]:
    """按自然标点取出短语；不会按固定字数直接切断一个词。"""
    pattern = r"[^，、：；。！？!?]+(?:[，、：；。！？!?][”’）)】]?)?"
    return [item.strip() for item in re.findall(pattern, paragraph) if item.strip()]


def _group_paragraph(paragraph: str) -> list[str]:
    """短语按语义拼组，长句才在逗号等自然位置拆开。"""
    target_chars = 42
    max_chars = 64
    groups: list[str] = []
    current = ""

    for clause in _clause_parts(paragraph):
        if current and len(current) + len(clause) > max_chars:
            groups.append(current)
            current = ""

        current += clause
        mark = _ending_mark(current)
        strong_stop = mark in {"。", "？", "?", "！", "!", "；", ";"}
        weak_stop = mark in {"，", "、", "："} and len(current) >= target_chars
        if strong_stop or weak_stop:
            groups.append(current)
            current = ""

    if current:
        groups.append(current)
    return groups


def segment_text(answer: str) -> list[SpeechSegment]:
    """按段落、句号和较长的逗号短语分段，给每段分配精确停顿。"""
    text = _speech_text(answer)
    paragraphs = [
        re.sub(r"\s+", "", paragraph)
        for paragraph in re.split(r"\n\s*\n", text)
        if paragraph.strip()
    ]
    grouped: list[tuple[str, bool]] = []
    for paragraph in paragraphs:
        parts = _group_paragraph(paragraph)
        for index, part in enumerate(parts):
            grouped.append((part, index == len(parts) - 1))

    if not grouped:
        raise ValueError("文本中没有可合成的语义分段。")

    segments: list[SpeechSegment] = []
    for index, (text_part, paragraph_end) in enumerate(grouped, start=1):
        is_final = index == len(grouped)
        segments.append(
            SpeechSegment(
                index=index,
                text=text_part,
                pause_after_ms=0
                if is_final
                else _default_pause(text_part, paragraph_end=paragraph_end),
                paragraph_end=paragraph_end,
            )
        )
    return segments


def _get_api_key() -> str:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("没有找到环境变量 DASHSCOPE_API_KEY。")
    return api_key


def _post_json(url: str, payload: dict, action: str) -> dict:
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {_get_api_key()}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=(30, 180),
        )
    except requests.RequestException as error:
        raise RuntimeError(f"{action}失败：{error}") from error

    if response.status_code != 200:
        raise RuntimeError(f"{action}失败：HTTP {response.status_code}\n{response.text}")
    try:
        return response.json()
    except requests.JSONDecodeError as error:
        raise RuntimeError(f"{action}失败：服务器返回的不是 JSON。") from error


def _download_audio(audio_url: str, output_path: Path) -> Path:
    """下载接口返回的临时音频地址；失败时自动使用 Windows curl。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    requests_error = ""
    try:
        response = requests.get(audio_url, timeout=(30, 180))
        response.raise_for_status()
        output_path.write_bytes(response.content)
        if output_path.stat().st_size > 0:
            return output_path.resolve()
        requests_error = "下载结果为空。"
    except requests.RequestException as error:
        requests_error = str(error)

    curl_path = shutil.which("curl.exe") or shutil.which("curl")
    if curl_path is None:
        raise RuntimeError(f"下载合成音频失败：{requests_error}；且没有找到 curl。")

    temporary_path = output_path.with_suffix(output_path.suffix + ".part")
    if temporary_path.exists():
        temporary_path.unlink()
    completed = subprocess.run(
        [
            curl_path,
            "--fail",
            "--location",
            "--silent",
            "--show-error",
            "--connect-timeout",
            "30",
            "--max-time",
            "180",
            "--output",
            str(temporary_path),
            audio_url,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        if temporary_path.exists():
            temporary_path.unlink()
        details = completed.stderr.strip() or f"退出码 {completed.returncode}"
        raise RuntimeError(f"下载合成音频失败：{requests_error}\ncurl：{details}")
    if not temporary_path.is_file() or temporary_path.stat().st_size == 0:
        raise RuntimeError("下载命令没有报错，但得到的是空文件。")

    temporary_path.replace(output_path)
    return output_path.resolve()


def _create_speech(text: str, voice_id: str, output_path: Path) -> Path:
    """让 Qwen3-TTS-VC 合成一个分段，并下载为本地文件。"""
    payload = {
        "model": VOICE_MODEL,
        "input": {
            "text": text,
            "voice": voice_id,
            "language_type": "Chinese",
        },
    }
    result = _post_json(CREATE_SPEECH_URL, payload, "语音合成")
    try:
        audio_url = result["output"]["audio"]["url"]
    except (KeyError, TypeError) as error:
        raise RuntimeError(f"语音合成响应缺少音频地址：{result}") from error
    return _download_audio(audio_url, output_path)


def _find_ffmpeg() -> Path:
    candidates = [
        shutil.which("ffmpeg"),
        str(Path(sys.executable).parent / "Library" / "bin" / "ffmpeg.exe"),
        r"D:\ANAconda\Library\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"D:\ffmpeg\bin\ffmpeg.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise RuntimeError("找不到 FFmpeg，无法裁掉静音和拼接 WAV。")


def _run_command(command: list[str], action: str) -> None:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"{action}失败：{details[-1000:]}")


def _trim_wav(ffmpeg: Path, source: Path, destination: Path) -> None:
    """只去掉首尾静音，不触碰中间由语音模型产生的自然停顿。"""
    filter_chain = (
        "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB,"
        "areverse,"
        "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB,"
        "areverse"
    )
    _run_command(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-af",
            filter_chain,
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "-c:a",
            "pcm_s16le",
            str(destination),
        ],
        "裁剪音频首尾静音",
    )


def _create_silence(path: Path, duration_ms: int) -> None:
    """用 WAV 标准库产生指定毫秒数的零音量片段。"""
    frames = round(SAMPLE_RATE * duration_ms / 1000)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(b"\x00\x00" * frames)


def _concat_line(path: Path) -> str:
    """生成 FFmpeg concat 文件需要的一行绝对路径。"""
    return f"file '{path.resolve().as_posix()}'"


def _write_manifest(
    path: Path,
    *,
    backup: TextBackup,
    source_question: str | None,
    segments: list[SpeechSegment],
    audio_path: Path,
) -> Path:
    payload = {
        "schema_version": "1.0",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "run_id": backup.run_id,
        "source_question": source_question,
        "text_backup": str(backup.path),
        "voice_id_file": str(VOICE_ID_FILE.resolve()),
        "pause_rules_ms": {
            "逗号_顿号_冒号": 200,
            "分号": 400,
            "问号_叹号": 500,
            "普通句间": 400,
            "自然段结束": 700,
        },
        "segments": [asdict(segment) for segment in segments],
        "audio_path": str(audio_path),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path.resolve()


def synthesize_answer(
    answer: str,
    backup: TextBackup,
    *,
    source_question: str | None = None,
) -> TtsResult:
    """合成所有分段、裁剪首尾空白、插入停顿并保存一套独立产物。"""
    voice_id = _load_voice_id()
    segments = segment_text(answer)
    ffmpeg = _find_ffmpeg()

    run_dir = TTS_RUNS_DIR / backup.run_id
    if run_dir.exists():
        raise FileExistsError(f"本次语音目录已经存在，不会覆盖：{run_dir}")
    raw_dir = run_dir / "raw_segments"
    trimmed_dir = run_dir / "trimmed_segments"
    pause_dir = run_dir / "pause_segments"
    for directory in (raw_dir, trimmed_dir, pause_dir):
        directory.mkdir(parents=True, exist_ok=False)

    parts: list[Path] = []
    for segment in segments:
        print(f"正在合成第 {segment.index}/{len(segments)} 段……")
        raw_path = raw_dir / f"{segment.index:03d}_raw.wav"
        trimmed_path = trimmed_dir / f"{segment.index:03d}_trimmed.wav"
        _create_speech(segment.text, voice_id, raw_path)
        _trim_wav(ffmpeg, raw_path, trimmed_path)
        parts.append(trimmed_path)

        if segment.pause_after_ms:
            pause_path = pause_dir / (
                f"{segment.index:03d}_pause_{segment.pause_after_ms}ms.wav"
            )
            _create_silence(pause_path, segment.pause_after_ms)
            parts.append(pause_path)

    concat_list = run_dir / "concat.txt"
    concat_list.write_text(
        "\n".join(_concat_line(path) for path in parts) + "\n",
        encoding="utf-8",
    )
    final_path = run_dir / f"qianwen_tts_{backup.run_id}.wav"
    _run_command(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c:a",
            "pcm_s16le",
            str(final_path),
        ],
        "拼接分段音频",
    )
    manifest_path = _write_manifest(
        run_dir / "manifest.json",
        backup=backup,
        source_question=source_question,
        segments=segments,
        audio_path=final_path.resolve(),
    )
    return TtsResult(
        run_id=backup.run_id,
        audio_path=final_path.resolve(),
        manifest_path=manifest_path,
    )
