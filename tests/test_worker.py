from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

from legenda_app.ffmpeg import EncodeOptions, SubtitleTrack
from legenda_app.worker import EncodeWorker


def _worker(output: Path) -> EncodeWorker:
    return EncodeWorker(
        EncodeOptions(
            video_path="input.mkv",
            subtitles=(SubtitleTrack("subtitle.srt", "por", "Português"),),
            output_path=str(output),
            mode="softsub",
        )
    )


def test_progress_updates_are_parsed() -> None:
    worker = _worker(Path("output.mkv"))
    updates: list[int] = []
    worker.progress_changed.connect(updates.append)

    worker._handle_line("out_time_us=500000", 2.0, [])

    assert updates == [25]


def test_progress_is_bounded_below_completion() -> None:
    worker = _worker(Path("output.mkv"))
    updates: list[int] = []
    worker.progress_changed.connect(updates.append)

    worker._handle_line("out_time_us=999999999", 1.0, [])

    assert updates == [99]


def test_cancel_terminates_running_windows_process() -> None:
    worker = _worker(Path("output.mkv"))
    process = Mock()
    process.poll.return_value = None
    worker._process = process

    with patch.object(os, "name", "nt"):
        worker.cancel()

    process.terminate.assert_called_once_with()
    assert worker._cancel_requested.is_set()


def test_read_progress_handles_pipe_lines_on_all_platforms() -> None:
    worker = _worker(Path("output.mkv"))
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "print('out_time_us=500000'); print('progress=continue')",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
    )
    updates: list[int] = []
    worker.progress_changed.connect(updates.append)

    worker._read_progress(process, 2.0, [])
    assert process.wait() == 0
    assert updates == [25]


def test_temporary_output_path_keeps_extension_and_is_clean(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output with spaces.mkv"

    temporary = Path(EncodeWorker._temporary_output_path(str(output)))

    assert temporary.parent == tmp_path
    assert temporary.suffix == ".mkv"
    assert not temporary.exists()
