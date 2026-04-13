import subprocess

from backend.services.frame_extractor import build_ffmpeg_command, extract_frames


def test_build_ffmpeg_command_uses_interval_and_jpegs():
    command = build_ffmpeg_command("input.mp4", "data/frames/demo", interval=3, max_width=1280, jpeg_quality=5)
    assert command[:4] == ["ffmpeg", "-y", "-i", "input.mp4"]
    assert "fps=1/3,scale=1280:-2:flags=lanczos:force_original_aspect_ratio=decrease" in command
    assert "5" in command
    assert command[-1].endswith("frame_%04d.jpg")


def test_build_ffmpeg_command_supports_custom_executable():
    command = build_ffmpeg_command(
        "input.mp4",
        "data/frames/demo",
        ffmpeg_command=r"D:\tools\ffmpeg\bin\ffmpeg.exe",
        interval=3,
    )
    assert command[0] == r"D:\tools\ffmpeg\bin\ffmpeg.exe"


def test_extract_frames_uses_utf8_subprocess(tmp_path, monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        output_dir = tmp_path / "frames"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "frame_0001.jpg").write_bytes(b"jpg")
        return None

    monkeypatch.setattr("backend.services.frame_extractor.subprocess.run", fake_run)

    frames = extract_frames("input.mp4", str(tmp_path / "frames"), interval=3, max_width=1280, jpeg_quality=5)

    assert frames[0]["timestamp"] == 0.0
    assert captured["kwargs"]["encoding"] == "utf-8"
    assert captured["kwargs"]["errors"] == "replace"


def test_extract_frames_raises_friendly_error_when_ffmpeg_missing(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        raise FileNotFoundError("missing ffmpeg")

    monkeypatch.setattr("backend.services.frame_extractor.subprocess.run", fake_run)

    try:
        extract_frames("input.mp4", str(tmp_path / "frames"), ffmpeg_command="ffmpeg.exe")
    except ValueError as exc:
        assert "FFmpeg executable not found" in str(exc)
        assert "ffmpeg.exe" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("extract_frames should raise ValueError when ffmpeg is missing")


def test_extract_frames_surfaces_ffmpeg_failure_output(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=command,
            stderr="decoder error",
        )

    monkeypatch.setattr("backend.services.frame_extractor.subprocess.run", fake_run)

    try:
        extract_frames("input.mp4", str(tmp_path / "frames"))
    except ValueError as exc:
        assert "FFmpeg failed while extracting frames from input.mp4" in str(exc)
        assert "decoder error" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("extract_frames should raise ValueError when ffmpeg exits with error")
