"""Media cleanup with ffmpeg: loudness, matching versions, one combined file.

- Loudness: measured with ffmpeg's ``loudnorm`` (EBU R128). Normalizing runs
  it twice: the first pass measures, the second applies a linear gain with
  those measurements, which keeps the intro's dynamics instead of squashing it.
  The default target is -23 LUFS with true peaks at or under -1 dBTP, the EBU
  R128 programme level. Streaming services deliver TV and films at about the
  same level (-24 to -27 LUFS), so an intro at -23 sits next to the movie
  that follows it. The -16 LUFS often quoted for "streaming" is the level for
  phones and podcasts; at -16 an intro would still be 7 LU louder than the
  film after it, which is the jump people complain about.
- Matching versions: 1080p (or 720p/4K) SDR H.264 with AAC stereo at 48 kHz,
  the format every Plex, Jellyfin and Emby app plays without transcoding and
  without switching the TV into HDR mode for a 20-second intro.
- Combine: several intros made into one file with a common format, for apps
  that only play the first intro (the official Jellyfin Roku app).

Every output is written under a temporary name (starting with a dot, so the
library scanner skips it) in its final folder and renamed when complete.
Originals are never changed in place: replacing one moves it to the Trash.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from typing import Callable, List, Optional

from backend.dynamic_preroll import RENDER_QUALITY_PROFILES, RENDER_RESOLUTIONS
from backend.errors import AppError

logger = logging.getLogger("prerollsmax.media_tools")

DEFAULT_TARGET_LUFS = -23.0
TRUE_PEAK_LIMIT = -1.0
LOUDNESS_RANGE = 11.0

# name -> (width, height, H.264 level)
PROFILES = {
    "720p": (*RENDER_RESOLUTIONS["720"], "4.0"),
    "1080p": (*RENDER_RESOLUTIONS["1080"], "4.1"),
    "2160p": (*RENDER_RESOLUTIONS["2160"], "5.1"),
}
PROFILE_LABELS = {"720p": "720p SDR", "1080p": "1080p SDR", "2160p": "4K SDR"}
FRAME_RATES = {"23.976": "24000/1001", "24": "24", "25": "25", "29.97": "30000/1001", "30": "30", "50": "50",
               "59.94": "60000/1001", "60": "60"}
VIDEO_EXTS_KEEP = (".mp4", ".m4v", ".mov", ".mkv")

_tools = {"ffmpeg": None, "ffprobe": None}
_zscale: dict = {}
# One heavy ffmpeg job at a time; others wait their turn.
media_lock = threading.Lock()


def configure(ffmpeg: Optional[str] = None, ffprobe: Optional[str] = None) -> None:
    _tools["ffmpeg"] = ffmpeg
    _tools["ffprobe"] = ffprobe
    _zscale.clear()


def ffmpeg() -> str:
    return _tools["ffmpeg"] or shutil.which("ffmpeg") or "ffmpeg"


def ffprobe() -> str:
    return _tools["ffprobe"] or shutil.which("ffprobe") or "ffprobe"


def _run(cmd: list, **kwargs) -> subprocess.CompletedProcess:
    if sys.platform.startswith("win"):
        kwargs.setdefault("creationflags", getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return subprocess.run(cmd, **kwargs)


def ffmpeg_missing() -> AppError:
    return AppError("Prerolls Max can't find ffmpeg, which it needs to change videos.", status=503,
                    code="ffmpeg_missing",
                    hint="Install ffmpeg (the Docker image includes it) and restart Prerolls Max.")


def available() -> bool:
    try:
        return _run([ffmpeg(), "-hide_banner", "-version"], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def has_zscale() -> bool:
    """Whether this ffmpeg can tone-map HDR properly (needs libzimg)."""
    if "value" not in _zscale:
        try:
            out = _run([ffmpeg(), "-hide_banner", "-filters"], capture_output=True, text=True, timeout=10).stdout
            _zscale["value"] = " zscale " in out and " tonemap " in out
        except (OSError, subprocess.SubprocessError):
            _zscale["value"] = False
    return _zscale["value"]


# ---------------------------------------------------------------------------
# Shared encoder settings (also used by POST /prerolls/{id}/transcode)
# ---------------------------------------------------------------------------

def scale_pad_filter(width: int, height: int) -> str:
    """Fit inside width x height keeping the shape, with black bars to fill."""
    return (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black")


def h264_aac_args(*, preset: str = "slow", crf: int = 18, level: str = "4.1",
                  audio_bitrate: str = "192k", stereo_48k: bool = False) -> list:
    """H.264 High (4:2:0) and AAC: plays everywhere without transcoding."""
    args = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", preset, "-crf", str(crf),
            "-profile:v", "high", "-level", level, "-c:a", "aac", "-b:a", audio_bitrate]
    if stereo_48k:
        args += ["-ar", "48000", "-ac", "2"]
    return args + ["-movflags", "+faststart"]


def tonemap_filter() -> str:
    """HDR (PQ/HLG) to SDR BT.709, or a plain conversion when ffmpeg can't tone-map."""
    if has_zscale():
        return ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
                "zscale=t=bt709:m=bt709:r=tv,format=yuv420p")
    # Without zscale the colours can't be converted properly, but the output
    # must at least be labelled as normal (SDR) video, or TVs still switch to
    # HDR mode for it. Colours may look a little flat.
    return ("setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv,"
            "format=yuv420p")


# ---------------------------------------------------------------------------
# Probing and measuring
# ---------------------------------------------------------------------------

def probe(path: str) -> dict:
    """What's in a video file. Raises AppError when it can't be read."""
    try:
        result = _run([ffprobe(), "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                      capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        raise ffmpeg_missing()
    except subprocess.TimeoutExpired:
        raise AppError("Reading that video took too long.", status=422, code="probe_timeout")
    if result.returncode != 0:
        raise AppError(f"Prerolls Max couldn't read '{os.path.basename(path)}'. It may be damaged or not a video.",
                       status=422, code="unreadable_video")
    data = json.loads(result.stdout or "{}")
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and not (s.get("disposition") or {}).get("attached_pic")), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    try:
        duration = float((data.get("format") or {}).get("duration") or video.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    transfer = (video.get("color_transfer") or "").lower()
    pix_fmt = video.get("pix_fmt") or ""
    hdr = transfer in ("smpte2084", "arib-std-b67") or (
        "10" in pix_fmt and (video.get("color_primaries") or "").lower() == "bt2020")
    fps = _fps(video.get("avg_frame_rate") or video.get("r_frame_rate"))
    return {
        "duration": duration,
        "width": int(video.get("width") or 0), "height": int(video.get("height") or 0),
        "video_codec": video.get("codec_name"), "pix_fmt": pix_fmt, "profile": video.get("profile"),
        "hdr": bool(hdr), "transfer": transfer or None, "fps": fps,
        "has_video": bool(video), "has_audio": bool(audio),
        "audio_codec": audio.get("codec_name"), "channels": int(audio.get("channels") or 0),
        "sample_rate": int(audio.get("sample_rate") or 0),
        "size": int((data.get("format") or {}).get("size") or 0),
    }


def _fps(text) -> Optional[float]:
    try:
        num, _, den = str(text or "").partition("/")
        value = float(num) / float(den or 1)
        return round(value, 3) if value > 0 else None
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def matches_profile(info: dict, profile: str = "1080p") -> bool:
    """True when a file already plays like a ``profile`` version would."""
    width, height, _level = PROFILES[profile]
    return (info.get("video_codec") == "h264" and info.get("pix_fmt") == "yuv420p" and not info.get("hdr")
            and info.get("width") == width and info.get("height") == height
            and (not info.get("has_audio") or info.get("audio_codec") == "aac"))


def describe_format(info: dict) -> str:
    if not info.get("has_video"):
        return "No video picture"
    bits = [f"{info['width']}x{info['height']}", (info.get("video_codec") or "?").upper()]
    bits.append("HDR" if info.get("hdr") else "SDR")
    if info.get("fps"):
        bits.append(f"{info['fps']:g} fps")
    bits.append(f"{(info.get('audio_codec') or '').upper()} {info.get('channels')}ch" if info.get("has_audio")
                else "no sound")
    return ", ".join(bits)


_JSON_BLOCK = re.compile(r"\{[^{}]*\"input_i\"[^{}]*\}", re.S)


def measure_loudness(path: str, target: float = DEFAULT_TARGET_LUFS) -> Optional[dict]:
    """EBU R128 measurement, or None when the file has no sound.

    {"lufs", "peak", "lra", "threshold", "offset"}
    """
    cmd = [ffmpeg(), "-hide_banner", "-nostats", "-i", path, "-map", "0:a:0", "-vn",
           "-af", f"loudnorm=I={target}:TP={TRUE_PEAK_LIMIT}:LRA={LOUDNESS_RANGE}:print_format=json",
           "-f", "null", "-"]
    try:
        result = _run(cmd, capture_output=True, text=True, timeout=1800)
    except FileNotFoundError:
        raise ffmpeg_missing()
    except subprocess.TimeoutExpired:
        raise AppError("Measuring that video took too long.", status=422, code="measure_timeout")
    text = result.stderr or ""
    if result.returncode != 0:
        if "matches no streams" in text or "Stream map" in text:
            return None
        raise AppError(f"Prerolls Max couldn't measure '{os.path.basename(path)}'.", status=422,
                       code="measure_failed", hint="The file may be damaged. Try playing it, or upload it again.")
    found = _JSON_BLOCK.findall(text)
    if not found:
        return None
    data = json.loads(found[-1])

    def num(key):
        try:
            value = float(data.get(key))
        except (TypeError, ValueError):
            return None
        return None if value in (float("inf"), float("-inf")) else value

    lufs = num("input_i")
    if lufs is None or lufs < -70:
        return {"lufs": None, "peak": num("input_tp"), "lra": num("input_lra"), "threshold": num("input_thresh"),
                "offset": num("target_offset"), "silent": True}
    return {"lufs": lufs, "peak": num("input_tp"), "lra": num("input_lra"), "threshold": num("input_thresh"),
            "offset": num("target_offset"), "silent": False}


def loudness_status(lufs: Optional[float], peak: Optional[float], checked: bool, target: float,
                    tolerance: float) -> tuple:
    """(status, plain label) for the library list."""
    if not checked:
        return "unchecked", "Not checked yet"
    if lufs is None:
        return "silent", "No sound"
    if lufs > target + tolerance:
        return "loud", f"{lufs - target:.1f} LU louder than your target"
    if lufs < target - tolerance:
        return "quiet", f"{target - lufs:.1f} LU quieter than your target"
    if peak is not None and peak > TRUE_PEAK_LIMIT + 0.5:
        return "peaks", "Level is fine but its loudest moments clip"
    return "ok", "Matches your target"


# ---------------------------------------------------------------------------
# Running ffmpeg with progress
# ---------------------------------------------------------------------------

def temp_output(final_path: str) -> str:
    folder, name = os.path.split(final_path)
    stem, ext = os.path.splitext(name)
    return os.path.join(folder, f".{stem}.partial-{uuid.uuid4().hex[:6]}{ext}")


def run_ffmpeg(args: list, output: str, *, total_seconds: float = 0,
               on_progress: Optional[Callable[[float], None]] = None, timeout: float = 3600) -> None:
    """Run ffmpeg writing ``output`` atomically. Raises AppError on failure."""
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    partial = temp_output(output)
    cmd = [ffmpeg(), "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats", *args, partial]
    kwargs = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    errors: List[str] = []
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **kwargs)
    except FileNotFoundError:
        raise ffmpeg_missing()

    def drain():
        for line in proc.stderr:
            errors.append(line)
            if len(errors) > 200:
                del errors[:100]

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    try:
        for line in proc.stdout:
            if on_progress and total_seconds and line.startswith("out_time_us="):
                try:
                    done = int(line.split("=", 1)[1]) / 1_000_000
                except ValueError:
                    continue
                on_progress(max(0.0, min(1.0, done / total_seconds)))
        proc.wait(timeout=timeout)
        reader.join(timeout=5)
        if proc.returncode != 0 or not os.path.exists(partial) or os.path.getsize(partial) == 0:
            logger.error("ffmpeg failed (%s): %s", proc.returncode, "".join(errors[-20:]))
            raise AppError("ffmpeg couldn't convert that video.", status=500, code="ffmpeg_failed",
                           hint="Settings > Logs has ffmpeg's own message. The original is unchanged.")
        os.replace(partial, output)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise AppError("Converting that video took too long and was stopped.", status=500, code="ffmpeg_timeout")
    finally:
        if os.path.exists(partial):
            try:
                os.remove(partial)
            except OSError:
                pass


def output_extension(source: str) -> str:
    ext = os.path.splitext(source)[1].lower()
    return ext if ext in VIDEO_EXTS_KEEP else ".mkv"


def unique_path(folder: str, filename: str) -> str:
    stem, ext = os.path.splitext(filename)
    candidate = os.path.join(folder, filename)
    counter = 2
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{stem} ({counter}){ext}")
        counter += 1
    return candidate


# ---------------------------------------------------------------------------
# The three tools
# ---------------------------------------------------------------------------

def normalize_loudness(source: str, output: str, *, target: float = DEFAULT_TARGET_LUFS,
                       measured: Optional[dict] = None,
                       on_progress: Optional[Callable[[float], None]] = None) -> dict:
    """Two-pass loudnorm into ``output``; video is copied untouched. Returns the new measurement."""
    info = probe(source)
    if not info["has_audio"]:
        raise AppError(f"'{os.path.basename(source)}' has no sound, so there's nothing to even out.",
                       status=422, code="no_audio")
    first = measured or measure_loudness(source, target)
    if not first or first.get("lufs") is None:
        raise AppError(f"'{os.path.basename(source)}' is silent, so there's nothing to even out.",
                       status=422, code="silent")
    loudnorm = (f"loudnorm=I={target}:TP={TRUE_PEAK_LIMIT}:LRA={LOUDNESS_RANGE}"
                f":measured_I={first['lufs']}:measured_TP={first['peak']}:measured_LRA={first['lra']}"
                f":measured_thresh={first['threshold']}:offset={first.get('offset') or 0}:linear=true")

    def args(copy_video: bool) -> list:
        video = ["-c:v", "copy"] if copy_video else ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                                                     "-preset", "medium"]
        out = ["-i", source, "-map", "0:v:0?", "-map", "0:a:0", *video, "-af", loudnorm,
               "-ar", "48000", "-c:a", "aac", "-b:a", "192k"]
        if output.lower().endswith((".mp4", ".m4v", ".mov")):
            out += ["-movflags", "+faststart"]
        return out

    try:
        run_ffmpeg(args(True), output, total_seconds=info["duration"], on_progress=on_progress)
    except AppError as exc:
        if exc.code != "ffmpeg_failed":
            raise
        # Some video streams can't be copied into the new file; re-encode them.
        run_ffmpeg(args(False), output, total_seconds=info["duration"], on_progress=on_progress)
    return measure_loudness(output, target) or {}


def make_version(source: str, output: str, *, profile: str = "1080p", frame_rate: str = "source",
                 on_progress: Optional[Callable[[float], None]] = None) -> dict:
    """An SDR H.264/AAC copy at ``profile`` size. Returns the new file's probe."""
    if profile not in PROFILES:
        raise AppError("Pick 720p, 1080p or 4K.", status=422, code="invalid_input")
    info = probe(source)
    if not info["has_video"]:
        raise AppError(f"'{os.path.basename(source)}' has no picture.", status=422, code="no_video")
    width, height, level = PROFILES[profile]
    quality = RENDER_QUALITY_PROFILES["high"]
    chain = []
    if info["hdr"]:
        chain.append(tonemap_filter())
    chain.append(scale_pad_filter(width, height))
    chain.append("setsar=1")
    rate = FRAME_RATES.get(frame_rate)
    if rate is None and info.get("fps") and info["fps"] > 60:
        rate = "60"
    if rate:
        chain.append(f"fps={rate}")
    chain.append("format=yuv420p")
    args = ["-i", source, "-map", "0:v:0", "-map", "0:a:0?", "-vf", ",".join(chain),
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
            *h264_aac_args(preset=quality["preset"], crf=min(int(quality["crf"]), 18), level=level,
                           audio_bitrate="192k", stereo_48k=True)]
    run_ffmpeg(args, output, total_seconds=info["duration"], on_progress=on_progress)
    return probe(output)


def combine(sources: List[str], output: str, *, profile: str = "1080p", frame_rate: str = "source",
            match_loudness: bool = True, target: float = DEFAULT_TARGET_LUFS,
            on_progress: Optional[Callable[[float], None]] = None) -> dict:
    """One file with every source in order, all in one common format."""
    if len(sources) < 2:
        raise AppError("Choose at least two intro videos to combine.", status=422, code="invalid_input")
    width, height, level = PROFILES.get(profile, PROFILES["1080p"])
    infos = [probe(s) for s in sources]
    if any(not i["has_video"] for i in infos):
        raise AppError("One of those files has no picture, so it can't be combined.", status=422, code="no_video")
    rate = FRAME_RATES.get(frame_rate)
    if rate is None:
        first = infos[0].get("fps") or 24
        rate = next((r for k, r in FRAME_RATES.items() if abs(float(k) - first) < 0.02), None) or \
            str(min(60, round(first)))
    args: list = []
    for source in sources:
        args += ["-i", source]
    parts = []
    labels = []
    for index, info in enumerate(infos):
        duration = max(0.1, info["duration"] or 0.1)
        video = []
        if info["hdr"]:
            video.append(tonemap_filter())
        video += [scale_pad_filter(width, height), "setsar=1", f"fps={rate}", "format=yuv420p",
                  f"trim=duration={duration:.3f}", "setpts=PTS-STARTPTS"]
        parts.append(f"[{index}:v:0]{','.join(video)}[v{index}]")
        if info["has_audio"]:
            audio = ["aresample=48000", "aformat=sample_fmts=fltp:channel_layouts=stereo"]
            if match_loudness:
                audio.append(f"loudnorm=I={target}:TP={TRUE_PEAK_LIMIT}:LRA={LOUDNESS_RANGE}")
                audio.append("aresample=48000")
            audio += ["apad", f"atrim=duration={duration:.3f}", "asetpts=PTS-STARTPTS"]
            parts.append(f"[{index}:a:0]{','.join(audio)}[a{index}]")
        else:
            parts.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={duration:.3f}[a{index}]")
        labels.append(f"[v{index}][a{index}]")
    parts.append(f"{''.join(labels)}concat=n={len(infos)}:v=1:a=1[outv][outa]")
    quality = RENDER_QUALITY_PROFILES["high"]
    args += ["-filter_complex", ";".join(parts), "-map", "[outv]", "-map", "[outa]",
             "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
             *h264_aac_args(preset=quality["preset"], crf=min(int(quality["crf"]), 18), level=level,
                            audio_bitrate="192k", stereo_48k=True)]
    total = sum(max(0.1, i["duration"] or 0.1) for i in infos)
    run_ffmpeg(args, output, total_seconds=total, on_progress=on_progress)
    return probe(output)
