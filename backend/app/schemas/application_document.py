from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApplicationDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    original_filename: str
    created_at: datetime
