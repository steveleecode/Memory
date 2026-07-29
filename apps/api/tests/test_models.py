from app.db.base import Base


def test_foundation_tables_are_registered() -> None:
    assert {
        "users",
        "sources",
        "documents",
        "document_chunks",
        "document_relationships",
    }.issubset(Base.metadata.tables.keys())


def test_user_scoped_tables_include_user_id() -> None:
    for table_name in ["sources", "documents", "document_chunks", "document_relationships"]:
        assert "user_id" in Base.metadata.tables[table_name].columns
