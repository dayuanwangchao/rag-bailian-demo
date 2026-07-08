from app.splitter import split_text


def test_split_text_respects_overlap():
    chunks = split_text("abcdefghijklmnopqrstuvwxyz", chunk_size=10, chunk_overlap=3)

    assert chunks == ["abcdefghij", "hijklmnopq", "opqrstuvwx", "vwxyz"]


def test_split_text_ignores_blank_content():
    assert split_text("\n\n  \n", chunk_size=10, chunk_overlap=2) == []
