from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .ffmpeg import (
    EncodeOptions,
    build_ffmpeg_command,
    probe_duration,
)


class EncodeWorker(QThread):
    progress_changed = Signal(int)
    succeeded = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, options: EncodeOptions) -> None:
        super().__init__()
        self.options = options
        self._cancel_requested = threading.Event()
        self._process: subprocess.Popen[bytes] | None = None
        self._process_lock = threading.Lock()

    def cancel(self) -> None:
        self._cancel_requested.set()
        with self._process_lock:
            process = self._process
        if process and process.poll() is None:
            self._terminate_process(process)

    def run(self) -> None:
        temporary_output: str | None = None
        try:
            duration = probe_duration(self.options.video_path)
            if self._cancel_requested.is_set():
                self.cancelled.emit()
                return

            temporary_output = self._temporary_output_path(self.options.output_path)
            options = replace(self.options, output_path=temporary_output)
            with self._options_with_safe_subtitle(options) as options:
                command = build_ffmpeg_command(options)
                command[1:1] = [
                    "-progress",
                    "pipe:1",
                    "-nostats",
                    "-stats_period",
                    "0.25",
                ]
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=0,
                    creationflags=(
                        subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
                    ),
                    start_new_session=os.name != "nt",
                )
                with self._process_lock:
                    self._process = process
                output_tail: list[str] = []
                self._read_progress(process, duration, output_tail)
                try:
                    return_code = process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    return_code = process.wait()
                with self._process_lock:
                    self._process = None

            if self._cancel_requested.is_set():
                self.cancelled.emit()
            elif return_code:
                details = "\n".join(output_tail[-12:]).strip()
                self.failed.emit(
                    details or f"FFmpeg terminou com código {return_code}."
                )
            else:
                if not Path(temporary_output).is_file():
                    raise RuntimeError(
                        "O FFmpeg terminou sem criar o ficheiro de saída."
                    )
                os.replace(temporary_output, self.options.output_path)
                self.progress_changed.emit(100)
                self.succeeded.emit(self.options.output_path)
        except Exception as exc:
            with self._process_lock:
                process = self._process
                self._process = None
            if process and process.poll() is None:
                process.kill()
                process.wait()
            self.failed.emit(str(exc))
        finally:
            if temporary_output:
                Path(temporary_output).unlink(missing_ok=True)

    @contextmanager
    def _options_with_safe_subtitle(
        self, options: EncodeOptions
    ) -> Iterator[EncodeOptions]:
        index = options.hard_subtitle_index
        if (
            options.mode != "hardsub"
            or not 0 <= index < len(options.subtitles)
            or "'" not in options.subtitles[index].path
        ):
            yield options
            return

        with tempfile.TemporaryDirectory(prefix="legenda-") as directory:
            safe_path = str(Path(directory) / "subtitle.srt")
            shutil.copyfile(options.subtitles[index].path, safe_path)
            tracks = list(options.subtitles)
            tracks[index] = replace(tracks[index], path=safe_path)
            yield replace(options, subtitles=tuple(tracks))

    @staticmethod
    def _temporary_output_path(output_path: str) -> str:
        destination = Path(output_path)
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=f".subfuse-{destination.stem}-",
            suffix=destination.suffix,
            dir=destination.parent or Path.cwd(),
        )
        os.close(descriptor)
        Path(temporary_path).unlink()
        return temporary_path

    @staticmethod
    def _terminate_process(process: subprocess.Popen[bytes]) -> None:
        if os.name != "nt" and process.pid:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                return
            except ProcessLookupError:
                return
        process.terminate()

    def _read_progress(
        self,
        process: subprocess.Popen[bytes],
        duration: float,
        output_tail: list[str],
    ) -> None:
        if process.stdout is None:
            raise RuntimeError("Não foi possível ler o progresso do FFmpeg.")

        try:
            for raw_line in iter(process.stdout.readline, b""):
                line = raw_line.decode("utf-8", errors="replace").strip()
                self._handle_line(line, duration, output_tail)
        finally:
            process.stdout.close()

    def _handle_line(
        self,
        line: str,
        duration: float,
        output_tail: list[str],
    ) -> None:
        if not line:
            return
        if "=" not in line:
            output_tail.append(line)
            if len(output_tail) > 20:
                del output_tail[:-20]
            return

        key, value = line.split("=", 1)
        if key == "out_time_us":
            try:
                percentage = int(float(value) / (duration * 10_000))
            except (ValueError, ZeroDivisionError):
                return
            self.progress_changed.emit(max(0, min(99, percentage)))
        elif key not in {
            "frame",
            "fps",
            "stream_0_0_q",
            "bitrate",
            "total_size",
            "out_time",
            "out_time_ms",
            "dup_frames",
            "drop_frames",
            "speed",
            "progress",
        }:
            output_tail.append(line)
            if len(output_tail) > 20:
                del output_tail[:-20]
