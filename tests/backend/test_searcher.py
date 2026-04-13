from backend.db import initialize_database
from backend.models import FrameAnalysisRecord
from backend.repositories import Repository
from backend.services.indexer import build_search_content
from backend.services.searcher import SearchService


def test_search_returns_matching_frame(tmp_path):
    db_path = tmp_path / "search.db"
    initialize_database(str(db_path))
    repository = Repository(str(db_path))
    video = repository.create_video_asset(
        {
            "filename": "demo.mp4",
            "filepath": str((tmp_path / "demo.mp4").resolve()),
            "duration": 12.0,
            "format": "mp4",
            "resolution": "1920x1080",
            "status": "completed",
        }
    )
    frames = repository.create_frames(
        video["id"],
        [
            {
                "frame_index": 0,
                "timestamp": 0.0,
                "image_path": str((tmp_path / "frame_0001.jpg").resolve()),
            }
        ],
    )
    repository.save_frame_analysis(
        FrameAnalysisRecord(
            frame_id=frames[0]["id"],
            video_id=video["id"],
            raw_json={"summary": "ChatGPT open"},
            screen_text="ChatGPT conversation window",
            application="ChatGPT",
            url="https://chatgpt.com",
            operation="asking for code",
            ai_tool_detected=True,
            ai_tool_name="ChatGPT",
            code_visible=False,
            code_content_summary="",
            risk_indicators=["ai platform usage"],
            summary="ChatGPT is visible",
            timestamp=0.0,
        )
    )
    repository.upsert_fts(
        frame_id=frames[0]["id"],
        video_id=video["id"],
        timestamp=0.0,
        content="ChatGPT conversation asking for code",
    )
    service = SearchService(repository)

    results = service.search("ChatGPT")

    assert len(results) == 1
    assert results[0]["video_name"] == "demo.mp4"
    assert results[0]["matched_source"] == "ocr"


def test_search_handles_punctuation_in_query_without_fts_error(tmp_path):
    db_path = tmp_path / "search.db"
    initialize_database(str(db_path))
    repository = Repository(str(db_path))
    video = repository.create_video_asset(
        {
            "filename": "demo.mp4",
            "filepath": str((tmp_path / "demo.mp4").resolve()),
            "duration": 12.0,
            "format": "mp4",
            "resolution": "1920x1080",
            "status": "completed",
        }
    )
    frames = repository.create_frames(
        video["id"],
        [
            {
                "frame_index": 0,
                "timestamp": 0.0,
                "image_path": str((tmp_path / "frame_0001.jpg").resolve()),
            }
        ],
    )
    repository.save_frame_analysis(
        FrameAnalysisRecord(
            frame_id=frames[0]["id"],
            video_id=video["id"],
            raw_json={"summary": "GitHub Copilot visible"},
            screen_text="GitHub Copilot visible",
            application="Visual Studio Code",
            url="",
            operation="asking copilot for code",
            ai_tool_detected=True,
            ai_tool_name="GitHub Copilot",
            code_visible=True,
            code_content_summary="lambda code",
            risk_indicators=["ai platform usage"],
            summary="GitHub Copilot is visible",
            timestamp=0.0,
        )
    )
    repository.upsert_fts(
        frame_id=frames[0]["id"],
        video_id=video["id"],
        timestamp=0.0,
        content="GitHub Copilot visible",
    )
    service = SearchService(repository)

    results = service.search("GitHub.Copilot")

    assert len(results) == 1
    assert results[0]["video_name"] == "demo.mp4"


def test_search_falls_back_to_video_metadata_when_index_has_no_match(tmp_path):
    db_path = tmp_path / "search.db"
    initialize_database(str(db_path))
    repository = Repository(str(db_path))
    video = repository.create_video_asset(
        {
            "filename": "使用AI平台.mp4",
            "filepath": str((tmp_path / "作弊视频" / "使用AI平台.mp4").resolve()),
            "duration": 12.0,
            "format": "mp4",
            "resolution": "1920x1080",
            "status": "completed",
        }
    )
    frames = repository.create_frames(
        video["id"],
        [
            {
                "frame_index": 0,
                "timestamp": 0.0,
                "image_path": str((tmp_path / "frame_0001.jpg").resolve()),
            }
        ],
    )
    repository.save_frame_analysis(
        FrameAnalysisRecord(
            frame_id=frames[0]["id"],
            video_id=video["id"],
            raw_json={"summary": "mock"},
            screen_text="frame 0001 的模拟 OCR 内容",
            application="模拟审查界面",
            url="",
            operation="mock",
            ai_tool_detected=False,
            ai_tool_name="",
            code_visible=False,
            code_content_summary="",
            risk_indicators=["模拟分析结果"],
            summary="frame 0001 的模拟分析结果",
            timestamp=0.0,
        )
    )
    repository.upsert_fts(
        frame_id=frames[0]["id"],
        video_id=video["id"],
        timestamp=0.0,
        content="frame 0001 的模拟 OCR 内容",
    )
    service = SearchService(repository)

    results = service.search("作弊")

    assert len(results) == 1
    assert results[0]["video_name"] == "使用AI平台.mp4"
    assert results[0]["matched_source"] == "metadata"
    assert "作弊视频" in results[0]["matched_text"]


def test_search_segments_chinese_text_for_fts(tmp_path):
    db_path = tmp_path / "search.db"
    initialize_database(str(db_path))
    repository = Repository(str(db_path))
    video = repository.create_video_asset(
        {
            "filename": "demo.mp4",
            "filepath": str((tmp_path / "demo.mp4").resolve()),
            "duration": 12.0,
            "format": "mp4",
            "resolution": "1920x1080",
            "status": "completed",
        }
    )
    frames = repository.create_frames(
        video["id"],
        [
            {
                "frame_index": 0,
                "timestamp": 0.0,
                "image_path": str((tmp_path / "frame_0001.jpg").resolve()),
            }
        ],
    )
    record = FrameAnalysisRecord(
        frame_id=frames[0]["id"],
        video_id=video["id"],
        raw_json={"summary": "正在使用AI平台生成代码"},
        screen_text="正在使用AI平台生成代码",
        application="",
        url="",
        operation="正在使用AI平台生成代码",
        ai_tool_detected=True,
        ai_tool_name="AI平台",
        code_visible=True,
        code_content_summary="生成代码",
        risk_indicators=[],
        summary="正在使用AI平台生成代码",
        timestamp=0.0,
    )
    repository.save_frame_analysis(record)
    repository.upsert_fts(
        frame_id=frames[0]["id"],
        video_id=video["id"],
        timestamp=0.0,
        content=build_search_content(record.model_dump()),
    )
    service = SearchService(repository)

    ai_platform_results = service.search("AI平台")
    generate_code_results = service.search("生成代码")

    assert len(ai_platform_results) == 1
    assert ai_platform_results[0]["frame_id"] == frames[0]["id"]
    assert len(generate_code_results) == 1
    assert generate_code_results[0]["frame_id"] == frames[0]["id"]


def test_search_requires_all_terms_for_multi_term_query(tmp_path):
    db_path = tmp_path / "search.db"
    initialize_database(str(db_path))
    repository = Repository(str(db_path))
    video = repository.create_video_asset(
        {
            "filename": "demo.mp4",
            "filepath": str((tmp_path / "demo.mp4").resolve()),
            "duration": 12.0,
            "format": "mp4",
            "resolution": "1920x1080",
            "status": "completed",
        }
    )
    frames = repository.create_frames(
        video["id"],
        [
            {
                "frame_index": 0,
                "timestamp": 0.0,
                "image_path": str((tmp_path / "frame_0001.jpg").resolve()),
            },
            {
                "frame_index": 1,
                "timestamp": 3.0,
                "image_path": str((tmp_path / "frame_0002.jpg").resolve()),
            },
            {
                "frame_index": 2,
                "timestamp": 6.0,
                "image_path": str((tmp_path / "frame_0003.jpg").resolve()),
            },
        ],
    )
    records = [
        FrameAnalysisRecord(
            frame_id=frames[0]["id"],
            video_id=video["id"],
            raw_json={"summary": "AWS credential exposed"},
            screen_text="AWS credential exposed",
            application="Terminal",
            url="",
            operation="printed AWS credential",
            ai_tool_detected=False,
            ai_tool_name="",
            code_visible=False,
            code_content_summary="",
            risk_indicators=[],
            summary="AWS credential exposed",
            timestamp=0.0,
        ),
        FrameAnalysisRecord(
            frame_id=frames[1]["id"],
            video_id=video["id"],
            raw_json={"summary": "AWS console open"},
            screen_text="AWS console open",
            application="Browser",
            url="",
            operation="opened AWS console",
            ai_tool_detected=False,
            ai_tool_name="",
            code_visible=False,
            code_content_summary="",
            risk_indicators=[],
            summary="AWS console open",
            timestamp=3.0,
        ),
        FrameAnalysisRecord(
            frame_id=frames[2]["id"],
            video_id=video["id"],
            raw_json={"summary": "credential placeholder visible"},
            screen_text="credential placeholder visible",
            application="Editor",
            url="",
            operation="edited credential placeholder",
            ai_tool_detected=False,
            ai_tool_name="",
            code_visible=False,
            code_content_summary="",
            risk_indicators=[],
            summary="credential placeholder visible",
            timestamp=6.0,
        ),
    ]
    for record in records:
        repository.save_frame_analysis(record)
        repository.upsert_fts(
            frame_id=record.frame_id,
            video_id=record.video_id,
            timestamp=record.timestamp,
            content=build_search_content(record.model_dump()),
        )
    service = SearchService(repository)

    results = service.search("AWS credential")

    assert len(results) == 1
    assert results[0]["frame_id"] == frames[0]["id"]


def test_search_marks_summary_hits_as_non_ocr(tmp_path):
    db_path = tmp_path / "search.db"
    initialize_database(str(db_path))
    repository = Repository(str(db_path))
    video = repository.create_video_asset(
        {
            "filename": "demo.mp4",
            "filepath": str((tmp_path / "demo.mp4").resolve()),
            "duration": 12.0,
            "format": "mp4",
            "resolution": "1920x1080",
            "status": "completed",
        }
    )
    frames = repository.create_frames(
        video["id"],
        [
            {
                "frame_index": 0,
                "timestamp": 0.0,
                "image_path": str((tmp_path / "frame_0001.jpg").resolve()),
            }
        ],
    )
    record = FrameAnalysisRecord(
        frame_id=frames[0]["id"],
        video_id=video["id"],
        raw_json={"summary": "suspicious automation flow"},
        screen_text="terminal output only",
        application="Terminal",
        url="",
        operation="reviewed logs",
        ai_tool_detected=False,
        ai_tool_name="",
        code_visible=False,
        code_content_summary="",
        risk_indicators=[],
        summary="suspicious automation flow",
        timestamp=0.0,
    )
    repository.save_frame_analysis(record)
    repository.upsert_fts(
        frame_id=frames[0]["id"],
        video_id=video["id"],
        timestamp=0.0,
        content=build_search_content(record.model_dump()),
    )
    service = SearchService(repository)

    results = service.search("automation flow")

    assert len(results) == 1
    assert results[0]["matched_source"] == "summary"
    assert results[0]["matched_text"] == "suspicious automation flow reviewed logs"


def test_build_segments_groups_adjacent_hits_into_time_ranges():
    results = [
        {
            "frame_id": 11,
            "video_id": 1,
            "video_name": "demo-a.mp4",
            "video_path": "E:/demo-a.mp4",
            "timestamp": 0.0,
            "matched_text": "AI tool open",
            "analysis_summary": "AI tool open",
            "frame_image_path": "E:/frame_001.jpg",
            "application": "Browser",
            "ai_tool_detected": True,
            "ai_tool_name": "ChatGPT",
            "risk_indicators": ["ai usage"],
        },
        {
            "frame_id": 12,
            "video_id": 1,
            "video_name": "demo-a.mp4",
            "video_path": "E:/demo-a.mp4",
            "timestamp": 3.0,
            "matched_text": "AI answer visible",
            "analysis_summary": "AI answer visible",
            "frame_image_path": "E:/frame_002.jpg",
            "application": "Browser",
            "ai_tool_detected": True,
            "ai_tool_name": "ChatGPT",
            "risk_indicators": ["ai usage"],
        },
        {
            "frame_id": 13,
            "video_id": 1,
            "video_name": "demo-a.mp4",
            "video_path": "E:/demo-a.mp4",
            "timestamp": 12.0,
            "matched_text": "new segment",
            "analysis_summary": "new segment",
            "frame_image_path": "E:/frame_003.jpg",
            "application": "Browser",
            "ai_tool_detected": False,
            "ai_tool_name": "",
            "risk_indicators": [],
        },
        {
            "frame_id": 21,
            "video_id": 2,
            "video_name": "demo-b.mp4",
            "video_path": "E:/demo-b.mp4",
            "timestamp": 1.0,
            "matched_text": "other video",
            "analysis_summary": "other video",
            "frame_image_path": "E:/frame_101.jpg",
            "application": "Editor",
            "ai_tool_detected": False,
            "ai_tool_name": "",
            "risk_indicators": ["tutorial_following_behavior"],
        },
    ]

    segments = SearchService.build_segments(results, max_gap_seconds=3.0)

    assert len(segments) == 3
    assert segments[0]["video_id"] == 1
    assert segments[0]["start_timestamp"] == 0.0
    assert segments[0]["end_timestamp"] == 3.0
    assert segments[0]["duration_seconds"] == 3.0
    assert segments[0]["hit_count"] == 2
    assert segments[0]["frame_ids"] == [11, 12]
    assert segments[0]["ai_tool_names"] == ["ChatGPT"]
    assert segments[1]["first_frame_id"] == 13
    assert segments[2]["video_id"] == 2
