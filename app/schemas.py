from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class TicketInput(StrictModel):
    subject: str = Field(min_length=4, max_length=160)
    body: str = Field(min_length=10, max_length=6000)
    customer_id: str = 'cus_ava'

    @field_validator('subject', 'body', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value


class DocumentInput(StrictModel):
    title: str = Field(min_length=3, max_length=120)
    text: str = Field(min_length=30, max_length=30000)

    @field_validator('title', 'text', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value


class Citation(StrictModel):
    source_id: str
    quote: str = Field(min_length=12, max_length=700)


class Resolution(StrictModel):
    reply: str = Field(min_length=20, max_length=4000)
    summary: str = Field(min_length=10, max_length=400)
    category: Literal['access', 'billing', 'technical', 'security', 'privacy', 'other']
    disposition: Literal['resolved', 'escalated']
    escalation_reason: str | None
    citations: list[Citation] = Field(max_length=6)


class RunInput(StrictModel):
    feedback: str = Field(default='', max_length=1500)
    retrieval_mode: Literal['hybrid', 'semantic', 'keyword'] = 'hybrid'


class ReviewInput(StrictModel):
    approve: bool
    note: str = Field(default='', max_length=1000)


class SearchInput(StrictModel):
    query: str = Field(min_length=3, max_length=1500)
    mode: Literal['hybrid', 'semantic', 'keyword'] = 'hybrid'


class AppError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = 'invalid_request'):
        self.message, self.status, self.code = message, status, code
        super().__init__(message)
