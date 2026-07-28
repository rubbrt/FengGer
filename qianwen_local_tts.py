"""Synthesize qianwen_demo output with the local feng_voice GPT-SoVITS model."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from gpt_sovits_demo import (
    DEMO_CONFIG,
    GPT_SOVITS_PACKAGE,
    GPT_SOVITS_ROOT,
    GPT_WEIGHTS,
    LOCAL_MODEL_ROOT,
    NLTK_DATA_DIR,
    REFERENCE_AUDIO,
    REFERENCE_TEXT,
    SOVITS_WEIGHTS,
    require_file,
)
from qianwen_tts import TtsResult, TextBackup, _speech_text, backup_generated_text


PROJECT_DIR = Path(__file__).resolve().parent
LOCAL_TTS_RUNS_DIR = PROJECT_DIR / "output" / "gpt_sovits_tts"


def _prepare_speech_text(answer: str) -> str:
    """提取朗读正文，并分别去掉 Qwen 常见的最外层中文引号。"""
    speech_text = _speech_text(answer).strip()
    return speech_text.removeprefix("“").removesuffix("”").strip()


def _allocate_run_dir(run_id: str) -> Path:
    """Allocate a fresh output directory, including after an interrupted run."""
    base = LOCAL_TTS_RUNS_DIR / run_id
    if not base.exists():
        return base
    for retry_number in range(2, 1000):
        candidate = LOCAL_TTS_RUNS_DIR / f"{run_id}_retry_{retry_number:02d}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"无法为本地 TTS 分配新的重试目录：{run_id}")


def _validate_runtime() -> None:
    for path, description in (
        (GPT_WEIGHTS, "GPT weight"),
        (SOVITS_WEIGHTS, "SoVITS weight"),
        (REFERENCE_AUDIO, "reference audio"),
        (
            GPT_SOVITS_PACKAGE
            / "pretrained_models"
            / "chinese-hubert-base"
            / "pytorch_model.bin",
            "CN-HuBERT model",
        ),
        (
            GPT_SOVITS_PACKAGE
            / "pretrained_models"
            / "chinese-roberta-wwm-ext-large"
            / "pytorch_model.bin",
            "Chinese BERT model",
        ),
        (
            GPT_SOVITS_PACKAGE
            / "pretrained_models"
            / "sv"
            / "pretrained_eres2netv2w24s4ep4.ckpt",
            "v2Pro speaker-verification model",
        ),
        (
            GPT_SOVITS_PACKAGE / "text" / "G2PWModel" / "g2pW.onnx",
            "G2PW pronunciation model",
        ),
    ):
        require_file(path, description)


def _write_manifest(
    path: Path,
    *,
    backup: TextBackup,
    source_question: str | None,
    speech_text: str,
    audio_path: Path,
    sample_rate: int,
    duration_seconds: float,
) -> Path:
    payload = {
        "schema_version": "2.0",
        "tts_backend": "local_gpt_sovits_v2pro",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "run_id": backup.run_id,
        "source_question": source_question,
        "text_backup": str(backup.path),
        "speech_text": speech_text,
        "audio_path": str(audio_path),
        "audio": {
            "sample_rate_hz": sample_rate,
            "duration_seconds": round(duration_seconds, 3),
            "channels": 1,
            "subtype": "PCM_16",
        },
        "model": {
            "framework": "GPT-SoVITS",
            "version": "v2Pro",
            "gpt_weights": str(GPT_WEIGHTS),
            "sovits_weights": str(SOVITS_WEIGHTS),
            "reference_audio": str(REFERENCE_AUDIO),
            "reference_text": REFERENCE_TEXT,
        },
        "inference": {
            "device": "cuda",
            "half_precision": True,
            "text_lang": "zh",
            "prompt_lang": "zh",
            "text_split_method": "cut1",
            "top_k": 5,
            "top_p": 1.0,
            "temperature": 1.0,
            "speed_factor": 0.95,
            "fragment_interval": 0.3,
            "seed": 42,
            "parallel_infer": True,
            "repetition_penalty": 1.35,
        },
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
    """Load the local model once and synthesize the complete Qwen answer."""
    _validate_runtime()
    speech_text = _prepare_speech_text(answer)

    run_dir = _allocate_run_dir(backup.run_id)
    run_dir.mkdir(parents=True, exist_ok=False)
    audio_path = (run_dir / f"gpt_sovits_{run_dir.name}.wav").resolve()
    manifest_path = run_dir / "manifest.json"

    previous_cwd = Path.cwd()
    try:
        # GPT-SoVITS has internal model paths relative to its checkout root.
        os.chdir(GPT_SOVITS_ROOT)
        os.environ.setdefault("MPLCONFIGDIR", str(LOCAL_MODEL_ROOT / ".matplotlib"))
        os.environ.setdefault("NLTK_DATA", str(NLTK_DATA_DIR))
        for import_path in (str(GPT_SOVITS_PACKAGE), str(GPT_SOVITS_ROOT)):
            if import_path not in sys.path:
                sys.path.insert(0, import_path)

        import soundfile as sf
        import torch
        from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config

        if not torch.cuda.is_available():
            raise RuntimeError("本地 GPT-SoVITS 需要 CUDA，但当前 PyTorch 看不到显卡。")

        config = TTS_Config(
            {
                "custom": {
                    "device": "cuda",
                    "is_half": True,
                    "version": "v2Pro",
                    "t2s_weights_path": str(GPT_WEIGHTS),
                    "vits_weights_path": str(SOVITS_WEIGHTS),
                    "bert_base_path": str(
                        GPT_SOVITS_PACKAGE
                        / "pretrained_models"
                        / "chinese-roberta-wwm-ext-large"
                    ),
                    "cnhuhbert_base_path": str(
                        GPT_SOVITS_PACKAGE
                        / "pretrained_models"
                        / "chinese-hubert-base"
                    ),
                }
            }
        )
        # Keep generated settings outside the upstream source checkout.
        config.configs_path = str(DEMO_CONFIG)
        pipeline = TTS(config)

        request = {
            "text": speech_text,
            "text_lang": "zh",
            "ref_audio_path": str(REFERENCE_AUDIO),
            "aux_ref_audio_paths": [],
            "prompt_text": REFERENCE_TEXT,
            "prompt_lang": "zh",
            "top_k": 5,
            "top_p": 1.0,
            "temperature": 1.0,
            "text_split_method": "cut1",
            "batch_size": 1,
            "batch_threshold": 0.75,
            "split_bucket": True,
            "speed_factor": 0.95,
            "fragment_interval": 0.3,
            "seed": 42,
            "parallel_infer": True,
            "repetition_penalty": 1.35,
        }

        print("正在用本地 feng_voice GPT-SoVITS 合成千问结果……")
        sample_rate, audio = next(pipeline.run(request))
        sf.write(audio_path, audio, sample_rate, subtype="PCM_16")
        duration_seconds = len(audio) / sample_rate
    finally:
        os.chdir(previous_cwd)

    resolved_manifest = _write_manifest(
        manifest_path,
        backup=backup,
        source_question=source_question,
        speech_text=speech_text,
        audio_path=audio_path,
        sample_rate=sample_rate,
        duration_seconds=duration_seconds,
    )
    return TtsResult(
        run_id=backup.run_id,
        audio_path=audio_path,
        manifest_path=resolved_manifest,
    )
