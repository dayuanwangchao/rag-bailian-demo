import re


def split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    cleaned = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not cleaned:
        return []
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    paragraphs = re.split(r"(\n\n+)", cleaned)
    chunks: list[str] = []
    current = ""

    for part in paragraphs:
        if not part.strip():
            continue
        if len(current) + len(part) <= chunk_size:
            current = f"{current}\n\n{part}".strip() if current else part.strip()
            continue
        if current:
            chunks.extend(_hard_split(current, chunk_size, chunk_overlap))
        current = part.strip()

    if current:
        chunks.extend(_hard_split(current, chunk_size, chunk_overlap))

    return [chunk.strip() for chunk in chunks if chunk.strip()]


def _hard_split(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    step = chunk_size - chunk_overlap

    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += step

    return chunks
