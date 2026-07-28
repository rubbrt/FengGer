"""Generate the current HyperFrames composition from a web storyboard."""

from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path
from typing import Iterable, Sequence


def _copy_media(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.is_file() or source.stat().st_size != destination.stat().st_size:
        shutil.copy2(source, destination)
    return destination


def _split_scene_copy(text: str) -> tuple[str, str | None]:
    """Split long copy into an editorial lead and supporting paragraph."""
    cleaned = text.strip()
    explicit = [part.strip() for part in re.split(r"\n\s*\n+", cleaned) if part.strip()]
    if len(explicit) > 1:
        return explicit[0], " ".join(explicit[1:])

    compact_length = len(re.sub(r"\s+", "", cleaned))
    if compact_length < 34:
        return cleaned, None

    candidates: list[int] = []
    for index, char in enumerate(cleaned, start=1):
        if char in "：；。！？" and compact_length * 0.32 <= index <= compact_length * 0.7:
            candidates.append(index)
    if not candidates:
        return cleaned, None

    split_at = min(candidates, key=lambda value: abs(value - compact_length * 0.48))
    return cleaned[:split_at].strip(), cleaned[split_at:].strip() or None


def _scene_markup(
    *,
    scene: dict,
    index: int,
    count: int,
    image_src: str,
    quote_topic: str,
) -> str:
    start = float(scene["start_seconds"])
    duration = float(scene["duration_seconds"])
    raw_text = str(scene["text"]).strip()
    lead, detail = _split_scene_copy(raw_text)
    compact_length = len(re.sub(r"\s+", "", raw_text))
    caption_size = (
        68
        if compact_length <= 28
        else 60
        if compact_length <= 44
        else 52
        if compact_length <= 62
        else 46
    )
    detail_markup = (
        f'<p class="caption-detail">{html.escape(detail)}</p>' if detail else ""
    )
    topic = html.escape(quote_topic)
    scene_number = index + 1
    initial_style = "" if index == 0 else ' style="opacity:0"'
    return f"""
      <section id="scene-{scene_number}" class="scene"{initial_style}>
        <div class="scene-surface" aria-hidden="true"></div>
        <div
          class="archive-code archive-code-left"
          data-code="F / ARCHIVE — {scene_number:02d}"
          aria-hidden="true"
        ></div>
        <div
          class="archive-code archive-code-right"
          data-code="FIELD NOTE · EDIT {scene_number:02d}"
          aria-hidden="true"
        ></div>
        <div class="editorial-grid">
          <div class="photo-frame">
            <img
              id="scene-{scene_number}-image"
              class="scene-image"
              data-layout-allow-overflow
              src="{html.escape(image_src)}"
              alt=""
            />
            <span class="photo-index" data-layout-allow-overlap>{scene_number:02d}</span>
          </div>
          <div
            class="copy-zone"
            data-layout-allow-overlap
            data-layout-allow-occlusion
          >
            <div class="brand-label">FENG STUDIO / VOICE NOTE</div>
            <div
              id="scene-{scene_number}-caption"
              class="caption"
              style="--caption-size:{caption_size}px"
            >
              <p class="caption-lead">{html.escape(lead)}</p>
              {detail_markup}
            </div>
            <div class="quote-topic">《{topic}》</div>
            <div class="scene-rule"></div>
            <div class="scene-footer">
              <span>SCENE {scene_number:02d} / {count:02d}</span>
              <span>{start:06.2f}s — {start + duration:06.2f}s</span>
            </div>
          </div>
        </div>
        <div class="progress-track">
          <div class="progress-value"></div>
        </div>
      </section>
    """


def _timeline_script(scenes: Sequence[dict]) -> str:
    lines = [
        'window.__timelines = window.__timelines || {};',
        'var tl = gsap.timeline({ paused: true });',
    ]
    for index, scene in enumerate(scenes):
        number = index + 1
        start = float(scene["start_seconds"])
        duration = float(scene["duration_seconds"])
        entrance = start if index == 0 else start + 0.1
        image_motion_duration = max(0.4, duration - (0.65 if index else 0.1))

        if index > 0:
            previous = number - 1
            previous_duration = float(scenes[index - 1]["duration_seconds"])
            transition_duration = min(
                0.72,
                max(0.08, min(previous_duration, duration) * 0.28),
            )
            transition_start = max(0.0, start - transition_duration * 0.72)
            lines.extend(
                [
                    (
                        f'tl.to("#scene-{previous}", '
                        '{ filter: "blur(12px)", scale: 1.012, opacity: 0, '
                        f'duration: {transition_duration:.3f}, ease: "sine.inOut" }}, '
                        f'{transition_start:.3f});'
                    ),
                    (
                        f'tl.fromTo("#scene-{number}", '
                        '{ filter: "blur(8px)", scale: 0.995, opacity: 0 }, '
                        '{ filter: "blur(0px)", scale: 1, opacity: 1, '
                        f'duration: {transition_duration:.3f}, ease: "sine.inOut" }}, '
                        f'{transition_start:.3f});'
                    ),
                ]
            )
            lines.append(
                f'tl.set("#scene-{previous}", '
                '{ opacity: 0, scale: 1, filter: "blur(0px)" }, '
                f'{transition_start + transition_duration + 0.02:.3f});'
            )

        lines.extend(
            [
                (
                    f'tl.fromTo("#scene-{number}-image", '
                    '{ scale: 1.012 }, '
                    f'{{ scale: 1.045, duration: {image_motion_duration:.3f}, '
                    f'ease: "none" }}, {start:.3f});'
                ),
                (
                    f'tl.fromTo("#scene-{number}-caption", '
                    '{ y: 22, opacity: 0 }, '
                    f'{{ y: 0, opacity: 1, duration: 0.72, ease: "power2.out" }}, '
                    f'{entrance:.3f});'
                ),
                (
                    f'tl.fromTo("#scene-{number} .brand-label", '
                    '{ x: -14, opacity: 0 }, '
                    f'{{ x: 0, opacity: 1, duration: 0.58, ease: "power1.out" }}, '
                    f'{entrance + 0.06:.3f});'
                ),
                (
                    f'tl.fromTo("#scene-{number} .quote-topic", '
                    '{ y: 12, opacity: 0 }, '
                    f'{{ y: 0, opacity: 1, duration: 0.62, ease: "power1.out" }}, '
                    f'{entrance + 0.16:.3f});'
                ),
                (
                    f'tl.fromTo("#scene-{number} .scene-rule", '
                    '{ scaleX: 0, opacity: 0.35 }, '
                    f'{{ scaleX: 1, opacity: 1, duration: 0.72, ease: "power2.out" }}, '
                    f'{entrance + 0.2:.3f});'
                ),
                (
                    f'tl.fromTo("#scene-{number} .scene-footer", '
                    '{ y: 10, opacity: 0 }, '
                    f'{{ y: 0, opacity: 1, duration: 0.58, ease: "power1.out" }}, '
                    f'{entrance + 0.25:.3f});'
                ),
                (
                    f'tl.fromTo("#scene-{number} .photo-index", '
                    '{ x: -10, opacity: 0 }, '
                    f'{{ x: 0, opacity: 1, duration: 0.48, ease: "power2.out" }}, '
                    f'{entrance + 0.12:.3f});'
                ),
            ]
        )

    last_number = len(scenes)
    total_duration = sum(float(scene["duration_seconds"]) for scene in scenes)
    fade_start = max(0, total_duration - 0.65)
    lines.append(
        f'tl.to("#scene-{last_number}", '
        f'{{ opacity: 0, duration: 0.6, ease: "sine.inOut" }}, {fade_start:.3f});'
    )
    lines.append('window.__timelines["main"] = tl;')
    return "\n      ".join(lines)


def _composition_html(
    *,
    width: int,
    height: int,
    audio_src: str,
    quote_topic: str,
    scenes: Sequence[dict],
    image_sources: Sequence[str],
) -> str:
    total_duration = round(sum(float(scene["duration_seconds"]) for scene in scenes), 3)
    portrait = height > width
    scene_markup = "\n".join(
        _scene_markup(
            scene=scene,
            index=index,
            count=len(scenes),
            image_src=image_sources[index],
            quote_topic=quote_topic,
        )
        for index, scene in enumerate(scenes)
    )
    timeline = _timeline_script(scenes)
    layout_class = "portrait" if portrait else "landscape"

    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={width}, height={height}" />
    <title>峰言峰语动态表情包</title>
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      @font-face {{
        font-family: "Feng Editorial Serif";
        src: url("assets/fonts/STZHONGS.TTF") format("truetype");
        font-style: normal;
        font-weight: 400;
        font-display: block;
      }}
      * {{ box-sizing: border-box; }}
      html, body {{
        width: {width}px;
        height: {height}px;
        margin: 0;
        overflow: hidden;
        background: #0D1217;
      }}
      body {{
        color: #EDE8DE;
        font-family: "Space Mono", monospace;
      }}
      #root {{
        position: relative;
        width: {width}px;
        height: {height}px;
        overflow: hidden;
      }}
      .scene {{
        position: absolute;
        inset: 0;
        width: {width}px;
        height: {height}px;
        overflow: hidden;
        isolation: isolate;
        background-color: #0D1217;
      }}
      .scene-surface {{
        position: absolute;
        z-index: 0;
        inset: 0;
        background:
          radial-gradient(circle at 72% 36%, rgba(23, 35, 44, 0.92) 0%, rgba(13, 18, 23, 0) 46%),
          radial-gradient(circle at 10% 84%, rgba(45, 49, 50, 0.22) 0%, rgba(13, 18, 23, 0) 34%),
          #0D1217;
      }}
      .scene-surface::before {{
        content: "";
        position: absolute;
        inset: 0;
        opacity: 0.09;
        background-image:
          url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='220' height='220' viewBox='0 0 220 220'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.78' numOctaves='3' seed='8' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='.45'/%3E%3C/svg%3E"),
          repeating-linear-gradient(
            104deg,
            rgba(237, 232, 222, 0) 0,
            rgba(237, 232, 222, 0) 112px,
            rgba(237, 232, 222, 0.12) 113px,
            rgba(237, 232, 222, 0) 114px
          );
        mix-blend-mode: soft-light;
      }}
      .scene-surface::after {{
        content: "";
        position: absolute;
        inset: 0;
        box-shadow:
          inset 0 0 {int(min(width, height) * 0.17)}px rgba(0, 0, 0, 0.72),
          inset 0 0 1px rgba(237, 232, 222, 0.08);
      }}
      .archive-code {{
        position: absolute;
        z-index: 1;
        color: rgba(201, 154, 82, 0.13);
        font-family: "Space Mono", monospace;
        font-size: {max(16, int(min(width, height) * 0.017))}px;
        letter-spacing: 0.18em;
        white-space: nowrap;
      }}
      .archive-code::before {{
        content: attr(data-code);
      }}
      .archive-code-left {{
        top: 48%;
        left: 28px;
        transform: rotate(-90deg) translateX(-50%);
        transform-origin: left top;
      }}
      .archive-code-right {{
        top: 34px;
        right: 42px;
      }}
      .editorial-grid {{
        position: absolute;
        z-index: 2;
        inset: 0;
        display: grid;
        min-width: 0;
        min-height: 0;
      }}
      .landscape .editorial-grid {{
        grid-template-columns: minmax(0, 42fr) minmax(0, 48fr);
        gap: {int(width * 0.052)}px;
        padding: {int(height * 0.07)}px {int(width * 0.058)}px {int(height * 0.115)}px;
      }}
      .portrait .editorial-grid {{
        grid-template-rows: minmax(0, 50fr) minmax(0, 42fr);
        gap: {int(height * 0.032)}px;
        padding: {int(height * 0.046)}px {int(width * 0.07)}px {int(height * 0.075)}px;
      }}
      .photo-frame {{
        position: relative;
        align-self: center;
        width: 100%;
        height: 100%;
        max-height: {int(height * (0.76 if not portrait else 0.48))}px;
        overflow: hidden;
        background: #090C0F;
        border: 1px solid rgba(237, 232, 222, 0.68);
        box-shadow: 0 {int(min(width, height) * 0.026)}px {int(min(width, height) * 0.075)}px rgba(0, 0, 0, 0.34);
      }}
      .scene-image {{
        display: block;
        width: 100%;
        height: 100%;
        object-fit: cover;
        object-position: center;
        filter: grayscale(1) contrast(1.1) brightness(0.9);
        transform-origin: center;
      }}
      .photo-index {{
        position: absolute;
        top: {max(20, int(min(width, height) * 0.028))}px;
        left: {max(20, int(min(width, height) * 0.028))}px;
        display: grid;
        min-width: {max(46, int(min(width, height) * 0.047))}px;
        height: {max(42, int(min(width, height) * 0.043))}px;
        padding: 0 12px;
        place-items: center;
        color: #11171C;
        background: #C99A52;
        font-family: "Space Mono", monospace;
        font-size: {max(18, int(min(width, height) * 0.02))}px;
        font-weight: 700;
        letter-spacing: 0.06em;
      }}
      .copy-zone {{
        position: relative;
        z-index: 3;
        display: flex;
        min-width: 0;
        flex-direction: column;
        justify-content: center;
        padding: {int(min(width, height) * 0.014)}px 0;
      }}
      .brand-label {{
        margin-bottom: {max(28, int(min(width, height) * 0.041))}px;
        color: #C99A52;
        font-family: "Space Mono", monospace;
        font-size: {max(17, int(min(width, height) * 0.018))}px;
        font-weight: 400;
        letter-spacing: 0.25em;
        line-height: 1.4;
      }}
      .caption {{
        max-width: 100%;
        color: #EDE8DE;
        font-family: "Feng Editorial Serif", serif;
        font-size: var(--caption-size);
        font-weight: 400;
        letter-spacing: 0.015em;
        text-align: left;
        text-wrap: pretty;
      }}
      .caption p {{
        margin: 0;
      }}
      .caption-lead {{
        line-height: 1.46;
      }}
      .caption-detail {{
        margin-top: {max(24, int(min(width, height) * 0.033))}px !important;
        color: rgba(237, 232, 222, 0.94);
        font-size: 0.88em;
        line-height: 1.58;
      }}
      .quote-topic {{
        display: block;
        margin-top: {max(24, int(min(width, height) * 0.03))}px;
        color: #C99A52;
        font-family: "Feng Editorial Serif", serif;
        font-size: {max(20, int(min(width, height) * (0.023 if portrait else 0.021)))}px;
        font-weight: 400;
        letter-spacing: 0.035em;
        line-height: 1.55;
        text-align: left;
        text-wrap: balance;
      }}
      .scene-rule {{
        display: block;
        width: 100%;
        height: 1px;
        margin: {max(26, int(min(width, height) * 0.033))}px 0 {max(16, int(min(width, height) * 0.019))}px;
        background-color: rgba(201, 154, 82, 0.72);
        transform-origin: left center;
      }}
      .scene-footer {{
        display: flex;
        justify-content: space-between;
        color: rgba(237, 232, 222, 0.68);
        font-family: "Space Mono", monospace;
        font-size: {max(16, int(min(width, height) * 0.017))}px;
        font-variant-numeric: tabular-nums;
        letter-spacing: 0.13em;
        line-height: 1.4;
      }}
      .progress-track {{
        position: absolute;
        z-index: 4;
        right: {int(width * (0.058 if not portrait else 0.07))}px;
        bottom: {int(height * 0.055)}px;
        left: {int(width * (0.058 if not portrait else 0.07))}px;
        height: 2px;
        background-color: rgba(201, 154, 82, 0.2);
      }}
      .progress-value {{
        display: block;
        width: 7.5%;
        height: 100%;
        background-color: #C99A52;
      }}
      .portrait .copy-zone {{
        justify-content: flex-start;
        padding-top: 0;
      }}
      .portrait .brand-label {{
        margin-bottom: 24px;
      }}
      .portrait .caption {{
        font-size: min(var(--caption-size), 50px);
      }}
      .portrait .caption-detail {{
        margin-top: 22px !important;
      }}
      .portrait .quote-topic {{
        margin-top: 22px;
      }}
      .portrait .scene-rule {{
        margin-top: 24px;
      }}
    </style>
  </head>
  <body>
    <div
      id="root"
      class="{layout_class}"
      data-composition-id="main"
      data-start="0"
      data-duration="{total_duration}"
      data-width="{width}"
      data-height="{height}"
    >
      {scene_markup}
      <audio
        id="voice-track"
        class="clip"
        src="{html.escape(audio_src)}"
        data-start="0"
        data-duration="{total_duration}"
        data-track-index="90"
        data-volume="1"
      ></audio>
    </div>
    <script>
      {timeline}
    </script>
  </body>
</html>
"""


def prepare_hyperframes_project(
    *,
    renderer_root: Path,
    run_id: str,
    audio_path: Path,
    aspect_ratio: str,
    quote_topic: str,
    scenes: Sequence[dict],
    assets: Sequence[Path],
) -> Path:
    """Write the current storyboard into the initialized HyperFrames project."""
    if not scenes:
        raise ValueError("至少需要一个分镜。")
    normalized_topic = str(quote_topic).strip().removeprefix("《").removesuffix("》").strip()
    if not normalized_topic:
        raise ValueError("语录主题不能为空。")
    width, height = (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)
    run_assets = renderer_root / "assets" / "runs" / run_id
    audio_target = _copy_media(audio_path, run_assets / f"voice{audio_path.suffix.lower()}")
    image_sources: list[str] = []

    for index, scene in enumerate(scenes):
        asset_id = int(scene["asset_id"])
        if asset_id < 0 or asset_id >= len(assets):
            raise ValueError(f"无效的素材编号：{asset_id}")
        source = assets[asset_id]
        target = _copy_media(
            source,
            run_assets / f"scene_{index + 1:03d}{source.suffix.lower()}",
        )
        image_sources.append(target.relative_to(renderer_root).as_posix())

    audio_src = audio_target.relative_to(renderer_root).as_posix()
    composition = _composition_html(
        width=width,
        height=height,
        audio_src=audio_src,
        quote_topic=normalized_topic,
        scenes=scenes,
        image_sources=image_sources,
    )
    (renderer_root / "index.html").write_text(composition, encoding="utf-8")
    manifest = {
        "run_id": run_id,
        "aspect_ratio": aspect_ratio,
        "width": width,
        "height": height,
        "audio": audio_src,
        "quote_topic": normalized_topic,
        "scenes": list(scenes),
    }
    (renderer_root / "current_storyboard.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return renderer_root
