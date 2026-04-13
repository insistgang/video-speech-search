from backend.db import get_connection, initialize_database


def test_initialize_database_creates_tables(tmp_path):
    db_path = tmp_path / "search.db"
    initialize_database(str(db_path))
    conn = get_connection(str(db_path))
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
    assert "video_assets" in names
    assert "frame_analysis_fts" in names
