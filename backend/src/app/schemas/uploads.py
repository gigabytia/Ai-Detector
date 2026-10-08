from pydantic import BaseModel


class UploadRead(BaseModel):
    file_ref: str
    source_url: str
    size_bytes: int
    original_name: str
