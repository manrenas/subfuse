from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from legenda_app import ffmpeg
from legenda_app.ffmpeg import EncodeOptions, SubtitleTrack


@pytest.fixture
def media_files(tmp_path: Path) -> tuple[Path, Path]:
    video = tmp_path / "source video.mkv"
    subtitle = tmp_path / "subtitle [pt], ação.srt"
    video.touch()
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:00,500\nOlá, mundo!\n",
        encoding="utf-8",
    )
    return video, subtitle


def _options(
    video: Path,
    subtitle: Path,
    output: Path,
    *,
    mode: str = "softsub",
    container: str = "mkv",
    **kwargs: object,
) -> EncodeOptions:
    return EncodeOptions(
        video_path=str(video),
        subtitles=(SubtitleTrack(str(subtitle), "por", "Português"),),
        output_path=str(output),
        mode=mode,  # type: ignore[arg-type]
        container=container,  # type: ignore[arg-type]
        **kwargs,
    )


def test_softsub_maps_video_audio_and_tracks_with_metadata(
    monkeypatch: pytest.MonkeyPatch, media_files: tuple[Path, Path], tmp_path: Path
) -> None:
    monkeypatch.setattr(ffmpeg, "_require_executable", lambda _name: "/bin/ffmpeg")
    video, subtitle = media_files
    command = ffmpeg.build_ffmpeg_command(
        _options(video, subtitle, tmp_path / "output.mkv")
    )

    assert command[command.index("-map") :].count("0:v") == 1
    assert "0:a?" in command
    assert "1:0" in command
    assert "language=por" in command
    assert "title=Português" in command
    assert command[-3:] == ["-c:s", "srt", str(tmp_path / "output.mkv")]
    assert str(tmp_path / "output.mkv") in command


def test_softsub_mp4_uses_mov_text(
    monkeypatch: pytest.MonkeyPatch, media_files: tuple[Path, Path], tmp_path: Path
) -> None:
    monkeypatch.setattr(ffmpeg, "_require_executable", lambda _name: "ffmpeg")
    command = ffmpeg.build_ffmpeg_command(
        _options(
            *media_files,
            tmp_path / "output.mp4",
            container="mp4",
        )
    )

    assert command[-3:] == ["-c:s", "mov_text", str(tmp_path / "output.mp4")]


def test_hardsub_builds_filter_and_applies_style(
    monkeypatch: pytest.MonkeyPatch, media_files: tuple[Path, Path], tmp_path: Path
) -> None:
    monkeypatch.setattr(ffmpeg, "_require_executable", lambda _name: "ffmpeg")
    monkeypatch.setattr(ffmpeg, "_require_subtitles_filter", lambda _ffmpeg: None)
    command = ffmpeg.build_ffmpeg_command(
        _options(
            *media_files,
            tmp_path / "burned.mp4",
            mode="hardsub",
            font_size=32,
            font_color="#12ABEF",
            outline=4,
        )
    )

    subtitle_filter = command[command.index("-vf") + 1]
    assert "subtitles=filename=" in subtitle_filter
    assert "FontSize=32" in subtitle_filter
    assert "PrimaryColour=&H00EFAB12" in subtitle_filter
    assert "Outline=4" in subtitle_filter
    assert "libx264" in command


def test_hardsub_requires_subtitles_filter(
    monkeypatch: pytest.MonkeyPatch, media_files: tuple[Path, Path], tmp_path: Path
) -> None:
    monkeypatch.setattr(ffmpeg, "_require_executable", lambda _name: "ffmpeg")
    monkeypatch.setattr(
        ffmpeg,
        "_require_subtitles_filter",
        lambda _ffmpeg: (_ for _ in ()).throw(RuntimeError("sem filtro subtitles")),
    )

    with pytest.raises(RuntimeError, match="sem filtro subtitles"):
        ffmpeg.build_ffmpeg_command(
            _options(*media_files, tmp_path / "out.mp4", mode="hardsub")
        )


def test_missing_ffmpeg_is_explained(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda _name: None)

    with pytest.raises(RuntimeError, match="não foi encontrado"):
        ffmpeg._require_executable("ffmpeg")


def test_filter_values_escape_special_characters() -> None:
    escaped = ffmpeg._escape_filter_value(r"C:\legenda's, [PT].srt")

    assert escaped.startswith("'") and escaped.endswith("'")
    assert r"C\:\\legenda\'s, [PT].srt" in escaped


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("softsub", "film_softsub.mkv"),
        ("hardsub", "film_hardsub.mp4"),
    ],
)
def test_default_output_path(mode: str, expected: str) -> None:
    output = ffmpeg.default_output_path("/media/film.avi", mode, "mkv")  # type: ignore[arg-type]
    assert Path(output).name == expected


def test_probe_duration_reports_missing_ffprobe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_executable(_name: str) -> str:
        raise RuntimeError("ffprobe não encontrado")

    monkeypatch.setattr(ffmpeg, "_require_executable", missing_executable)

    with pytest.raises(RuntimeError, match="ffprobe não encontrado"):
        ffmpeg.probe_duration("video.mkv")


def test_probe_duration_reads_ffprobe_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Result:
        returncode = 0
        stdout = "12.5\n"
        stderr = ""

    monkeypatch.setattr(ffmpeg, "_require_executable", lambda _name: "ffprobe")
    monkeypatch.setattr(ffmpeg.subprocess, "run", lambda *_args, **_kwargs: Result())

    assert ffmpeg.probe_duration("video.mkv") == 12.5


@pytest.mark.integration
def test_softsub_ffmpeg_integration(tmp_path: Path) -> None:
    ffmpeg_bin, ffprobe_bin = _integration_tools()
    video, subtitle = _make_video_and_subtitle(tmp_path, ffmpeg_bin)
    output = tmp_path / "softsub result.mkv"
    command = ffmpeg.build_ffmpeg_command(_options(video, subtitle, output))
    subprocess.run(command, check=True, capture_output=True, text=True)
    probe = subprocess.run(
        [
            ffprobe_bin,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type:stream_tags=language,title",
            "-of",
            "json",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert output.is_file()
    assert '"codec_type": "subtitle"' in probe.stdout
    assert '"language": "por"' in probe.stdout
    assert '"title": "Português"' in probe.stdout


@pytest.mark.integration
def test_hardsub_ffmpeg_integration_with_special_paths(tmp_path: Path) -> None:
    ffmpeg_bin, _ffprobe_bin = _integration_tools(require_subtitles=True)
    video, subtitle = _make_video_and_subtitle(tmp_path, ffmpeg_bin)
    output = tmp_path / "hardsub result.mp4"
    options = _options(video, subtitle, output, mode="hardsub")

    command = ffmpeg.build_ffmpeg_command(options)
    subprocess.run(command, check=True, capture_output=True, text=True)

    assert output.is_file()
    assert output.stat().st_size > 0


def _integration_tools(*, require_subtitles: bool = False) -> tuple[str, str]:
    ffmpeg_bin = ffmpeg.shutil.which("ffmpeg")
    ffprobe_bin = ffmpeg.shutil.which("ffprobe")
    if not ffmpeg_bin or not ffprobe_bin:
        pytest.skip("Integração ignorada: ffmpeg e/ou ffprobe não estão no PATH.")
    if require_subtitles:
        try:
            ffmpeg._require_subtitles_filter(ffmpeg_bin)
        except RuntimeError as error:
            pytest.skip(f"Integração hardsub ignorada: {error}")
    return ffmpeg_bin, ffprobe_bin


def _make_video_and_subtitle(directory: Path, ffmpeg_bin: str) -> tuple[Path, Path]:
    video = directory / "vídeo de teste [x].mkv"
    subtitle = directory / "legenda [pt], ação.srt"
    subprocess.run(
        [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x64:r=5:d=1",
            "-c:v",
            "mpeg4",
            str(video),
        ],
        check=True,
        capture_output=True,
    )
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:00,800\nOlá, mundo!\n",
        encoding="utf-8",
    )
    return video, subtitle
