"""Generate a short local GPT-SoVITS v2Pro voice demo from the cloned weights."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
LOCAL_MODEL_ROOT = PROJECT_ROOT / "Local_model"
GPT_SOVITS_ROOT = LOCAL_MODEL_ROOT / "GPT-SoVITS"
GPT_SOVITS_PACKAGE = GPT_SOVITS_ROOT / "GPT_SoVITS"
VOICE_ROOT = LOCAL_MODEL_ROOT / "feng_voice"
DEMO_CONFIG = LOCAL_MODEL_ROOT / "gpt-sovits-demo-config.yaml"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output" / "local_gpt_sovits"
NLTK_DATA_DIR = LOCAL_MODEL_ROOT / "gpt-sovits-demo-env" / "nltk_data"

GPT_WEIGHTS = VOICE_ROOT / "feng_voice_4090-e20.ckpt"
SOVITS_WEIGHTS = VOICE_ROOT / "feng_voice_4090_e34_s4148.pth"
REFERENCE_AUDIO = VOICE_ROOT / "merged_000008.wav"
REFERENCE_TEXT = "你觉得他算是个成功的网红吗，毫无疑问呐"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local feng_voice GPT-SoVITS demo.")
    parser.add_argument(
        "--text",
        default="这事没那么复杂。先把眼前的活干明白，剩下的慢慢来。",
        help="Chinese text to synthesize.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output WAV path. Defaults to output/local_gpt_sovits/ with a timestamp.",
    )
    parser.add_argument(
        "--device",
        choices=("cuda", "cpu"),
        default="cuda",
        help="Use CUDA by default; CPU is primarily for diagnostics.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Use -1 for a random seed.")
    parser.add_argument("--speed", type=float, default=0.95, help="Speech speed factor.")
    return parser.parse_args()


def require_file(path: Path, description: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {description}: {path}")


def default_output_path() -> Path:
    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    return DEFAULT_OUTPUT_DIR / f"feng_voice_demo_{timestamp}.wav"


def main() -> None:
    args = parse_args()
    invocation_dir = Path.cwd().resolve()
    for path, description in (
        (GPT_WEIGHTS, "GPT weight"),
        (SOVITS_WEIGHTS, "SoVITS weight"),
        (REFERENCE_AUDIO, "reference audio"),
        (GPT_SOVITS_PACKAGE / "pretrained_models" / "chinese-hubert-base" / "pytorch_model.bin", "CN-HuBERT model"),
        (
            GPT_SOVITS_PACKAGE / "pretrained_models" / "chinese-roberta-wwm-ext-large" / "pytorch_model.bin",
            "Chinese BERT model",
        ),
        (GPT_SOVITS_PACKAGE / "pretrained_models" / "sv" / "pretrained_eres2netv2w24s4ep4.ckpt", "v2Pro speaker-verification model"),
        (GPT_SOVITS_PACKAGE / "text" / "G2PWModel" / "g2pW.onnx", "G2PW pronunciation model"),
    ):
        require_file(path, description)

    # GPT-SoVITS keeps some imports and the G2PW model path relative to its root.
    os.chdir(GPT_SOVITS_ROOT)
    # The process account cannot write its default matplotlib cache folder.
    os.environ.setdefault("MPLCONFIGDIR", str(LOCAL_MODEL_ROOT / ".matplotlib"))
    os.environ.setdefault("NLTK_DATA", str(NLTK_DATA_DIR))
    sys.path[:0] = [str(GPT_SOVITS_PACKAGE), str(GPT_SOVITS_ROOT)]

    import soundfile as sf
    import torch
    from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config

    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but PyTorch cannot see a CUDA device. Try --device cpu.")

    # Keep GPT-SoVITS' generated config separate from the upstream source checkout.
    config = TTS_Config(
        {
            "custom": {
                "device": args.device,
                "is_half": args.device == "cuda",
                "version": "v2Pro",
                "t2s_weights_path": str(GPT_WEIGHTS),
                "vits_weights_path": str(SOVITS_WEIGHTS),
                "bert_base_path": str(
                    GPT_SOVITS_PACKAGE / "pretrained_models" / "chinese-roberta-wwm-ext-large"
                ),
                "cnhuhbert_base_path": str(
                    GPT_SOVITS_PACKAGE / "pretrained_models" / "chinese-hubert-base"
                ),
            }
        }
    )
    config.configs_path = str(DEMO_CONFIG)
    pipeline = TTS(config)

    if args.output is None:
        output_path = default_output_path()
    elif args.output.is_absolute():
        output_path = args.output
    else:
        # `os.chdir(GPT_SOVITS_ROOT)` above is required by GPT-SoVITS internals;
        # keep a caller-supplied relative output path relative to the command's
        # original working directory instead.
        output_path = invocation_dir / args.output
    output_path = output_path.expanduser().resolve()
    if output_path.suffix.lower() != ".wav":
        raise ValueError("Only WAV output is supported; use an output path ending in .wav.")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    request = {
        "text": args.text.strip(),
        "text_lang": "zh",
        "ref_audio_path": str(REFERENCE_AUDIO),
        "aux_ref_audio_paths": [],
        "prompt_text": REFERENCE_TEXT,
        "prompt_lang": "zh",
        "top_k": 5,
        "top_p": 1.0,
        "temperature": 1.0,
        # "凑四句一切" is the model repository's recommended text split mode.
        "text_split_method": "cut1",
        "batch_size": 1,
        "batch_threshold": 0.75,
        "split_bucket": True,
        "speed_factor": args.speed,
        "fragment_interval": 0.3,
        "seed": args.seed,
        "parallel_infer": True,
        "repetition_penalty": 1.35,
    }
    if not request["text"]:
        raise ValueError("Text cannot be empty.")

    print("Loading finished. Synthesizing…")
    sample_rate, audio = next(pipeline.run(request))
    sf.write(output_path, audio, sample_rate, subtype="PCM_16")
    print(f"Saved: {output_path}")
    print(f"Sample rate: {sample_rate} Hz | device: {args.device} | seed: {args.seed}")


if __name__ == "__main__":
    main()
