from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx


class VisionAnalysisError(RuntimeError):
    """Raised when an image cannot be loaded or analyzed by a VLM."""


DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_GROQ_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
DEFAULT_MIME_TYPE = "image/jpeg"
FRAME_MIME_TYPE = "image/jpeg"


async def analyze_camera_image(source_url: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze a camera image and return normalized JSON for DAG conditions.

    Expected args:
      - prompt: visual task, e.g. "Detect whether smoke or fire is visible"
      - image_url or image_base64: optional direct image input
      - video_path or video_url: optional video input sampled into frames
      - source_method/capture_method and capture_args: optional camera capture call
      - provider: gemini or groq (defaults to VLM_PROVIDER/gemini)
      - model: optional provider model override
    """
    args = args or {}
    provider = str(args.get("provider") or os.getenv("VLM_PROVIDER", "gemini")).lower()
    model = str(args.get("model") or os.getenv("VLM_MODEL") or _default_model(provider))
    prompt = _build_prompt(args)

    video_frames, video_source = await _resolve_video_input(args)
    if video_frames:
        if provider == "gemini":
            raw_text = await _analyze_with_gemini_media(video_frames, prompt, model)
        elif provider == "groq":
            first_frame, first_mime = video_frames[0]
            raw_text = await _analyze_with_groq(first_frame, None, first_mime, prompt, model)
        else:
            raise VisionAnalysisError(
                f"Unsupported VLM provider '{provider}'. Supported providers: gemini, groq"
            )
        return _normalize_response(raw_text, provider, model, video_source)

    image_bytes, image_url, mime_type, image_source = await _resolve_image_input(
        source_url=source_url,
        args=args,
        prefer_url=provider == "groq",
    )

    if provider == "gemini":
        if image_bytes is None and image_url:
            image_bytes, mime_type = await _fetch_image_url(image_url, args)
        if image_bytes is None:
            raise VisionAnalysisError("Gemini analysis requires image bytes")
        raw_text = await _analyze_with_gemini(image_bytes, mime_type, prompt, model)
    elif provider == "groq":
        raw_text = await _analyze_with_groq(image_bytes, image_url, mime_type, prompt, model)
    else:
        raise VisionAnalysisError(
            f"Unsupported VLM provider '{provider}'. Supported providers: gemini, groq"
        )

    return _normalize_response(raw_text, provider, model, image_source)


def _default_model(provider: str) -> str:
    if provider == "groq":
        return DEFAULT_GROQ_MODEL
    return DEFAULT_GEMINI_MODEL


def _build_prompt(args: Dict[str, Any]) -> str:
    task = (
        args.get("prompt")
        or args.get("question")
        or "Analyze this camera image for conditions relevant to the automation policy."
    )
    target_labels = args.get("labels") or args.get("target_labels") or []
    if isinstance(target_labels, str):
        target_labels = [target_labels]

    label_hint = ""
    if target_labels:
        label_hint = (
            "Focus especially on these labels or conditions: "
            + ", ".join(str(label) for label in target_labels)
            + "."
        )

    return f"""
You are the visual perception step for an IoT policy automation engine.
Task: {task}
{label_hint}

Return only valid JSON with this shape:
{{
  "detected": true,
  "labels": ["person", "smoke"],
  "summary": "One short sentence describing the relevant visual evidence.",
  "confidence": 0.0,
  "observations": {{}},
  "recommended_action": null
}}

Rules:
- Set "detected" to true only when the requested condition is visible.
- "confidence" must be a number from 0 to 1.
- Keep labels short and machine-friendly.
- If the image is unclear, set detected=false and explain why in summary.
- If multiple frames are provided, treat them as chronological samples from one camera video.
""".strip()


async def _resolve_video_input(args: Dict[str, Any]) -> Tuple[List[Tuple[bytes, str]], Dict[str, Any]]:
    video_path = args.get("video_path") or args.get("video_file")
    if isinstance(video_path, str) and video_path.strip():
        frames = _sample_video_frames(video_path, args)
        return frames, {"type": "video_path", "value": video_path, "sampled_frames": len(frames)}

    video_url = args.get("video_url")
    if isinstance(video_url, str) and video_url.strip():
        local_path = await _download_video(video_url, args)
        frames = _sample_video_frames(str(local_path), args)
        return frames, {"type": "video_url", "value": video_url, "sampled_frames": len(frames)}

    return [], {}


async def _resolve_image_input(
    source_url: str,
    args: Dict[str, Any],
    prefer_url: bool,
) -> Tuple[Optional[bytes], Optional[str], str, Dict[str, Any]]:
    mime_type = str(args.get("mime_type") or DEFAULT_MIME_TYPE)

    for key in ("image_base64", "base64_image", "image_data", "data_uri", "frame_base64"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            image_bytes, detected_mime = _decode_base64_image(value, mime_type)
            return image_bytes, None, detected_mime, {"type": key}

    image_path = args.get("image_path") or args.get("file_path")
    if isinstance(image_path, str) and image_path.strip():
        image_bytes, detected_mime = _read_image_file(image_path, mime_type)
        return image_bytes, None, detected_mime, {"type": "file_path", "value": image_path}

    for key in ("image_url", "frame_url", "snapshot_url"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            if value.strip().lower().startswith("data:image/") and not prefer_url:
                image_bytes, detected_mime = _decode_base64_image(value, mime_type)
                return image_bytes, None, detected_mime, {"type": key}
            if prefer_url:
                return None, value, mime_type, {"type": key, "value": value}
            image_bytes, detected_mime = await _fetch_image_url(value, args)
            return image_bytes, None, detected_mime, {"type": key, "value": value}

    capture_url = str(args.get("source_url") or source_url or "").strip()
    if not capture_url:
        raise VisionAnalysisError(
            "No image source found. Provide image_url, image_base64, image_path, or a capability URL."
        )

    return await _capture_from_url(capture_url, args, prefer_url)


async def _capture_from_url(
    url: str,
    args: Dict[str, Any],
    prefer_url: bool,
) -> Tuple[Optional[bytes], Optional[str], str, Dict[str, Any]]:
    method = str(args.get("source_method") or args.get("capture_method") or "GET").upper()
    capture_args = args.get("capture_args") or {}
    if not isinstance(capture_args, dict):
        capture_args = {}

    timeout = float(args.get("capture_timeout_seconds") or 20)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if method in ("POST", "PUT", "PATCH"):
            response = await client.request(method, url, json=capture_args)
        else:
            response = await client.request(method, url, params=capture_args or None)

    response.raise_for_status()
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()

    if content_type.startswith("image/"):
        image_bytes = response.content
        _validate_image_size(image_bytes)
        return image_bytes, None, content_type, {"type": "capture_url", "value": url}

    try:
        payload = response.json()
    except Exception as exc:
        raise VisionAnalysisError(
            f"Camera capture URL did not return image bytes or JSON: {content_type or 'unknown'}"
        ) from exc

    return await _extract_image_from_json(payload, args, prefer_url, {"type": "capture_url", "value": url})


async def _extract_image_from_json(
    payload: Any,
    args: Dict[str, Any],
    prefer_url: bool,
    image_source: Dict[str, Any],
) -> Tuple[Optional[bytes], Optional[str], str, Dict[str, Any]]:
    if not isinstance(payload, dict):
        raise VisionAnalysisError("Camera capture JSON must be an object containing image data")

    mime_type = str(payload.get("mime_type") or args.get("mime_type") or DEFAULT_MIME_TYPE)

    for key in ("image_base64", "base64_image", "image_data", "data_uri", "frame_base64"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            image_bytes, detected_mime = _decode_base64_image(value, mime_type)
            return image_bytes, None, detected_mime, {**image_source, "field": key}

    for key in ("image_url", "frame_url", "snapshot_url", "file_url", "url"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            if value.strip().lower().startswith("data:image/") and not prefer_url:
                image_bytes, detected_mime = _decode_base64_image(value, mime_type)
                return image_bytes, None, detected_mime, {**image_source, "field": key}
            if prefer_url:
                return None, value, mime_type, {**image_source, "field": key, "value": value}
            image_bytes, detected_mime = await _fetch_image_url(value, args)
            return image_bytes, None, detected_mime, {**image_source, "field": key, "value": value}

    for key in ("image_path", "file_path", "file", "path"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            image_bytes, detected_mime = _read_image_file(value, mime_type)
            return image_bytes, None, detected_mime, {**image_source, "field": key, "value": value}

    raise VisionAnalysisError(
        "Camera capture JSON did not contain image_url, image_base64, or image_path"
    )


async def _fetch_image_url(url: str, args: Dict[str, Any]) -> Tuple[bytes, str]:
    timeout = float(args.get("image_timeout_seconds") or 20)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if not content_type.startswith("image/"):
        raise VisionAnalysisError(f"Image URL returned non-image content type: {content_type}")
    image_bytes = response.content
    _validate_image_size(image_bytes)
    return image_bytes, content_type


async def _download_video(url: str, args: Dict[str, Any]) -> Path:
    timeout = float(args.get("video_timeout_seconds") or 60)
    max_bytes = int(os.getenv("VLM_MAX_VIDEO_BYTES", str(100 * 1024 * 1024)))

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url)
    response.raise_for_status()

    content = response.content
    if len(content) > max_bytes:
        raise VisionAnalysisError(
            f"Video is too large for VLM frame sampling ({len(content)} bytes > {max_bytes} bytes)"
        )

    suffix = Path(url.split("?", 1)[0]).suffix or ".mp4"
    temp_dir = Path(tempfile.gettempdir()) / "fyp_vlm_video"
    temp_dir.mkdir(parents=True, exist_ok=True)
    path = temp_dir / f"video_input{suffix}"
    path.write_bytes(content)
    return path


def _sample_video_frames(path_value: str, args: Dict[str, Any]) -> List[Tuple[bytes, str]]:
    path = Path(path_value).expanduser()
    if not path.exists() or not path.is_file():
        raise VisionAnalysisError(f"Video file does not exist: {path_value}")

    max_bytes = int(os.getenv("VLM_MAX_VIDEO_BYTES", str(100 * 1024 * 1024)))
    if path.stat().st_size > max_bytes:
        raise VisionAnalysisError(
            f"Video is too large for VLM frame sampling ({path.stat().st_size} bytes > {max_bytes} bytes)"
        )

    frame_count = max(1, min(int(args.get("video_frame_count") or args.get("frame_count") or 4), 12))
    interval = max(1.0, float(args.get("video_frame_interval_seconds") or 4))
    start_seconds = max(0.0, float(args.get("video_start_seconds") or 0))
    max_width = max(320, min(int(args.get("video_frame_width") or 960), 1600))

    with tempfile.TemporaryDirectory(prefix="vlm_frames_") as temp_dir:
        frame_pattern = str(Path(temp_dir) / "frame_%03d.jpg")
        vf = f"fps=1/{interval},scale='min({max_width},iw)':-2"
        command = [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-ss",
            str(start_seconds),
            "-i",
            str(path),
            "-frames:v",
            str(frame_count),
            "-vf",
            vf,
            frame_pattern,
        ]

        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise VisionAnalysisError("ffmpeg is required to sample video frames for VLM analysis") from exc
        except subprocess.CalledProcessError as exc:
            error = (exc.stderr or exc.stdout or "").strip()
            raise VisionAnalysisError(f"ffmpeg failed to sample video frames: {error[:300]}") from exc

        frame_paths = sorted(Path(temp_dir).glob("frame_*.jpg"))
        if not frame_paths:
            raise VisionAnalysisError("No frames could be sampled from the video")

        frames: List[Tuple[bytes, str]] = []
        for frame_path in frame_paths[:frame_count]:
            frame_bytes = frame_path.read_bytes()
            _validate_image_size(frame_bytes)
            frames.append((frame_bytes, FRAME_MIME_TYPE))
        return frames


def _read_image_file(path_value: str, default_mime: str) -> Tuple[bytes, str]:
    path = Path(path_value).expanduser()
    if not path.exists() or not path.is_file():
        raise VisionAnalysisError(f"Image file does not exist: {path_value}")
    image_bytes = path.read_bytes()
    _validate_image_size(image_bytes)
    mime_type = mimetypes.guess_type(str(path))[0] or default_mime
    return image_bytes, mime_type


def _decode_base64_image(value: str, default_mime: str) -> Tuple[bytes, str]:
    data = value.strip()
    mime_type = default_mime

    match = re.match(r"^data:(image/[-+.\w]+);base64,(.*)$", data, re.IGNORECASE | re.DOTALL)
    if match:
        mime_type = match.group(1)
        data = match.group(2)

    try:
        image_bytes = base64.b64decode(data, validate=True)
    except Exception as exc:
        raise VisionAnalysisError("Invalid base64 image data") from exc

    _validate_image_size(image_bytes)
    return image_bytes, mime_type


def _validate_image_size(image_bytes: bytes) -> None:
    max_bytes = int(os.getenv("VLM_MAX_IMAGE_BYTES", str(10 * 1024 * 1024)))
    if len(image_bytes) > max_bytes:
        raise VisionAnalysisError(
            f"Image is too large for VLM analysis ({len(image_bytes)} bytes > {max_bytes} bytes)"
        )


async def _analyze_with_gemini(
    image_bytes: bytes,
    mime_type: str,
    prompt: str,
    model: str,
) -> str:
    return await _analyze_with_gemini_media([(image_bytes, mime_type)], prompt, model)


async def _analyze_with_gemini_media(
    media_parts: List[Tuple[bytes, str]],
    prompt: str,
    model: str,
) -> str:
    def call_gemini() -> str:
        try:
            from google import genai
            from google.genai import types
        except Exception as exc:
            raise VisionAnalysisError(
                "Gemini VLM requires the google-genai package. Install backend requirements first."
            ) from exc

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise VisionAnalysisError("Set GEMINI_API_KEY to use the Gemini VLM provider")

        client = genai.Client(api_key=api_key)
        contents = [
            types.Part.from_bytes(data=data, mime_type=mime_type)
            for data, mime_type in media_parts
        ]
        contents.append(prompt)

        kwargs: Dict[str, Any] = {"model": model, "contents": contents}
        try:
            kwargs["config"] = types.GenerateContentConfig(response_mime_type="application/json")
        except Exception:
            pass

        response = client.models.generate_content(**kwargs)
        return getattr(response, "text", None) or str(response)

    return await asyncio.to_thread(call_gemini)


async def _analyze_with_groq(
    image_bytes: Optional[bytes],
    image_url: Optional[str],
    mime_type: str,
    prompt: str,
    model: str,
) -> str:
    def call_groq() -> str:
        try:
            from groq import Groq
        except Exception as exc:
            raise VisionAnalysisError(
                "Groq VLM requires the groq package. Install backend requirements first."
            ) from exc

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise VisionAnalysisError("Set GROQ_API_KEY to use the Groq VLM provider")

        if image_url:
            groq_image_url = image_url
        elif image_bytes:
            encoded = base64.b64encode(image_bytes).decode("ascii")
            groq_image_url = f"data:{mime_type};base64,{encoded}"
        else:
            raise VisionAnalysisError("Groq analysis requires image_url or image bytes")

        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": groq_image_url}},
                    ],
                }
            ],
            temperature=0,
            max_completion_tokens=1024,
            response_format={"type": "json_object"},
        )
        return completion.choices[0].message.content or ""

    return await asyncio.to_thread(call_groq)


def _normalize_response(
    raw_text: str,
    provider: str,
    model: str,
    image_source: Dict[str, Any],
) -> Dict[str, Any]:
    parsed = _parse_json_object(raw_text)
    labels = parsed.get("labels", [])
    if isinstance(labels, str):
        labels = [labels]
    if not isinstance(labels, list):
        labels = []

    confidence = _as_float(parsed.get("confidence"))
    detected_value = parsed.get("detected", False)
    if not isinstance(detected_value, bool):
        detected_value = str(detected_value).strip().lower() in {"true", "yes", "1", "detected"}

    result = {
        "detected": detected_value,
        "labels": [str(label) for label in labels],
        "summary": str(parsed.get("summary") or parsed.get("description") or ""),
        "confidence": confidence,
        "observations": parsed.get("observations") if isinstance(parsed.get("observations"), dict) else {},
        "recommended_action": parsed.get("recommended_action"),
        "provider": provider,
        "model": model,
        "image_source": image_source,
        "raw": parsed,
    }

    return result


def _parse_json_object(raw_text: str) -> Dict[str, Any]:
    text = (raw_text or "").strip()
    if text.startswith("```json"):
        text = text[7:].strip()
    if text.startswith("```"):
        text = text[3:].strip()
    if text.endswith("```"):
        text = text[:-3].strip()

    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {"raw_text": raw_text}
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            return data if isinstance(data, dict) else {"raw_text": raw_text}
        except json.JSONDecodeError:
            pass

    return {
        "detected": False,
        "labels": [],
        "summary": text[:500],
        "confidence": 0.0,
        "observations": {},
        "recommended_action": None,
    }


def _as_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))
