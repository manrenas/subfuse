from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

OperationMode = Literal["softsub", "hardsub"]


@dataclass(frozen=True)
class SubtitleTrack:
    path: str
    language: str
    title: str


@dataclass(frozen=True)
class EncodeOptions:
    video_path: str
    subtitles: tuple[SubtitleTrack, ...]
    output_path: str
    mode: OperationMode
    container: Literal["mkv", "mp4"] = "mkv"
    hard_subtitle_index: int = 0
    font_size: int = 24
    font_color: str = "#FFFFFF"
    outline: int = 2


def _require_executable(name: str) -> str:
    executable_names = (name, f"{name}.exe") if os.name == "nt" else (name,)
    bundle_roots: list[Path] = []
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        bundle_roots.append(Path(bundled_root))
    if getattr(sys, "frozen", False):
        bundle_roots.append(Path(sys.executable).resolve().parent)
    bundle_roots.append(Path(__file__).resolve().parent)

    for root in bundle_roots:
        for executable_name in executable_names:
            candidate = root / "tools" / executable_name
            if candidate.is_file() and (
                os.name == "nt" or os.access(candidate, os.X_OK)
            ):
                return str(candidate)

    executable = None
    for candidate in executable_names:
        executable = shutil.which(candidate)
        if executable:
            break
    if not executable:
        raise RuntimeError(
            f"'{name}' não foi encontrado. Instale o FFmpeg e confirme que "
            "ffmpeg e ffprobe estão no PATH. Esta aplicação não os descarrega."
        )
    return executable


def probe_duration(video_path: str) -> float:
    ffprobe = _require_executable("ffprobe")
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            video_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        details = result.stderr.strip() or "não foi possível ler o ficheiro."
        raise RuntimeError(f"Falha ao analisar o vídeo: {details}")
    try:
        duration = float(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError("O ffprobe não devolveu a duração do vídeo.") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError("A duração do vídeo é inválida.")
    return duration


def _escape_filter_value(value: str) -> str:
    """Escapa um valor para a sintaxe de opções do filtro subtitles do FFmpeg."""
    escaped = value.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
    return f"'{escaped}'"


def _require_subtitles_filter(ffmpeg: str) -> None:
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-filters"],
        capture_output=True,
        text=True,
        check=False,
    )
    filters = f"{result.stdout}\n{result.stderr}"
    if result.returncode or not re.search(
        r"^\s*[.A-Z]{2,3}\s+subtitles\s", filters, flags=re.MULTILINE
    ):
        raise RuntimeError(
            "Este FFmpeg não tem suporte ao filtro 'subtitles' (libass). "
            "Instale uma compilação do FFmpeg com libass para usar hardsub."
        )


def _ass_color(hex_color: str) -> str:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", hex_color):
        raise ValueError("A cor deve estar no formato hexadecimal #RRGGBB.")
    red, green, blue = (int(hex_color[index : index + 2], 16) for index in (1, 3, 5))
    return f"&H00{blue:02X}{green:02X}{red:02X}"


def build_ffmpeg_command(options: EncodeOptions) -> list[str]:
    ffmpeg = _require_executable("ffmpeg")
    if not Path(options.video_path).is_file():
        raise ValueError("O ficheiro de vídeo selecionado não existe.")
    if not options.subtitles:
        raise ValueError("Adicione pelo menos uma legenda SRT.")

    command = [ffmpeg, "-hide_banner", "-y", "-i", options.video_path]
    if options.mode == "softsub":
        if options.container == "mp4":
            output_codec = "mov_text"
        else:
            output_codec = "srt"

        for track in options.subtitles:
            if not Path(track.path).is_file():
                raise ValueError(f"A legenda não existe: {track.path}")
            command.extend(["-i", track.path])

        command.extend(["-map", "0:v", "-map", "0:a?"])
        for index, track in enumerate(options.subtitles):
            command.extend(
                [
                    "-map",
                    f"{index + 1}:0",
                    f"-metadata:s:s:{index}",
                    f"language={track.language}",
                    f"-metadata:s:s:{index}",
                    f"title={track.title}",
                ]
            )
        command.extend(["-c", "copy", "-c:s", output_codec, options.output_path])
        return command

    if options.mode != "hardsub":
        raise ValueError(f"Modo de operação desconhecido: {options.mode}")
    if not 0 <= options.hard_subtitle_index < len(options.subtitles):
        raise ValueError("Selecione uma legenda válida para queimar no vídeo.")
    if not 8 <= options.font_size <= 96:
        raise ValueError("O tamanho da fonte deve estar entre 8 e 96.")
    if not 0 <= options.outline <= 10:
        raise ValueError("O contorno deve estar entre 0 e 10.")

    _require_subtitles_filter(ffmpeg)
    subtitle_path = options.subtitles[options.hard_subtitle_index].path
    if not Path(subtitle_path).is_file():
        raise ValueError(f"A legenda não existe: {subtitle_path}")
    style = (
        f"FontSize={options.font_size},"
        f"PrimaryColour={_ass_color(options.font_color)},"
        f"Outline={options.outline},BorderStyle=1"
    )
    subtitle_filter = (
        f"subtitles=filename={_escape_filter_value(subtitle_path)}:"
        f"force_style={_escape_filter_value(style)}"
    )
    command.extend(
        [
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-vf",
            subtitle_filter,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            options.output_path,
        ]
    )
    return command


def default_output_path(video_path: str, mode: OperationMode, container: str) -> str:
    video = Path(video_path)
    if mode == "hardsub":
        return str(video.with_name(f"{video.stem}_hardsub.mp4"))
    return str(video.with_name(f"{video.stem}_softsub.{container}"))
