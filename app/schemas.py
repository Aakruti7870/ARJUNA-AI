from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: Any


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str = "auto"
    messages: list[Message]
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0, le=131072)
    stream: bool = False
    provider: str | None = None
    free_only: bool = True


class PlaygroundRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=100000)
    system_prompt: str | None = Field(default=None, max_length=20000)
    model: str = Field(default="auto", max_length=200)
    provider: str | None = Field(default=None, max_length=50)
    free_only: bool = True
    temperature: float | None = Field(default=0.2, ge=0, le=2)
    max_tokens: int | None = Field(default=4096, gt=0, le=131072)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=512)


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class ProviderUpsertRequest(BaseModel):
    base_url: str = Field(min_length=8, max_length=1000)
    api_key: str | None = Field(default=None, max_length=10000)
    default_model: str = Field(min_length=1, max_length=300)
    priority: int = Field(default=100, ge=0, le=10000)
    free_eligible: bool = True
    enabled: bool = True
    allowed_models: list[str] = Field(default_factory=list, max_length=100)
    free_models: list[str] = Field(default_factory=list, max_length=100)
