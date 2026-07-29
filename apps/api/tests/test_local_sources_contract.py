from app.api.local_sources import _local_external_id


def test_local_external_id_prefers_platform_file_id() -> None:
    assert _local_external_id("renamed/notes.md", "dev:inode") == "platform:dev:inode"


def test_local_external_id_falls_back_to_relative_path() -> None:
    assert _local_external_id("notes.md", None) == "path:notes.md"
