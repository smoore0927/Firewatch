"""Bounded reads for multipart uploads."""

from fastapi import HTTPException, UploadFile, status


def read_upload_capped(upload: UploadFile, max_bytes: int, *, detail: str) -> bytes:
    """Read an UploadFile in 1 MB chunks, raising 413 once it exceeds max_bytes."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = upload.file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=detail)
        chunks.append(chunk)
    return b"".join(chunks)
