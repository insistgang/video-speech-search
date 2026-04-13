from __future__ import annotations

from pathlib import Path

from backend.services.video_clipper import _build_clip_command, cleanup_clip, clip_video_segment


def test_build_clip_command_uses_configured_ffmpeg_command():
    command = _build_clip_command(
        video_path=r"E:\videos\demo.mp4",
        output_path=r"E:\tmp\clip.mp4",
        start_time=3.0,
        duration=6.0,
        ffmpeg_command=r"D:\tools\ffmpeg\bin\ffmpeg.exe",
    )

    assert command[0] == r"D:\tools\ffmpeg\bin\ffmpeg.exe"


def test_clip_video_segment_invokes_configured_ffmpeg_command(tmp_path, monkeypatch):
    video_path = tmp_path / "input.mp4"
    video_path.write_bytes(b"fake-video")
    captured: dict[str, list[str]] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        output_path = Path(command[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-clip-data")
        return None

    monkeypatch.setattr("backend.services.video_clipper.subprocess.run", fake_run)

    clip_path = clip_video_segment(
        video_path=str(video_path.resolve()),
        start_time=0.0,
        duration=3.0,
        ffmpeg_command=r"D:\tools\ffmpeg\bin\ffmpeg.exe",
    )

    try:
        assert Path(clip_path).exists()
        assert captured["command"][0] == r"D:\tools\ffmpeg\bin\ffmpeg.exe"
    finally:
        cleanup_clip(clip_path)
