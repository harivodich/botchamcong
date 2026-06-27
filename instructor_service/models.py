from pydantic import BaseModel

class Instructor(BaseModel):
    id: str
    name: str
    department: str
    group_name: str
    title: str
    base_rate: int