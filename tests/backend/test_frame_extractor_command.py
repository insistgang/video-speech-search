from backend.services.frame_extractor import build_ffmpeg_command


def test_build_ffmpeg_command_preserves_paths_with_spaces_without_shell_quotes():
    video_path = r"E:\videos with space\input file.mp4"

    command = build_ffmpeg_command(video_path, "data/frames/demo", interval=3, max_width=1280, jpeg_quality=5)

    assert command[:4] == ["ffmpeg", "-y", "-i", video_path]
    assert command[3] == video_path
    assert not command[3].startswith("'")
    assert not command[3].endswith("'")
