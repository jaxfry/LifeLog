from typing import Optional
from fastapi import Query

class Pagination:
    def __init__(
        self,
        limit: int = Query(default=100, ge=1, le=1000, description="Number of items to return"),
        offset: int = Query(default=0, ge=0, description="Number of items to skip")
    ):
        self.limit = limit
        self.offset = offset
