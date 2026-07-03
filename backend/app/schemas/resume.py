from datetime import datetime
from pydantic import BaseModel

class ResumeResponse(BaseModel):
    id: int
    user_id: int
    file_name: str
    file_path: str
    file_type: str
    file_size: int
    uploaded_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
