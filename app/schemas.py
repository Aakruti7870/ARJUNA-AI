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


class PreviewAnalyzeRequest(BaseModel):
    content: str = Field(min_length=1, max_length=300000)
    hint: Literal["auto", "html", "markdown", "json", "text"] = "auto"


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


class GrowthConnectorUpsertRequest(BaseModel):
    account_label: str = Field(default="", max_length=200)
    account_id: str = Field(default="", max_length=300)
    credentials: dict[str, str] | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class LeadCreateRequest(BaseModel):
    source: str = Field(default="manual", max_length=100)
    name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=80)
    company: str | None = Field(default=None, max_length=200)
    message: str | None = Field(default=None, max_length=20000)
    tags: list[str] = Field(default_factory=list, max_length=50)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LeadUpdateRequest(BaseModel):
    status: str | None = Field(default=None, max_length=50)
    owner: str | None = Field(default=None, max_length=200)
    tags: list[str] | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=20000)


class CampaignCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    platform: str = Field(min_length=2, max_length=60)
    objective: str = Field(default="lead_generation", max_length=100)
    status: str = Field(default="draft", max_length=50)
    budget_daily: float | None = Field(default=None, ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=8)
    audience: dict[str, Any] = Field(default_factory=dict)
    creative: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProposalCreateRequest(BaseModel):
    lead_id: str | None = Field(default=None, max_length=36)
    title: str = Field(min_length=2, max_length=250)
    body: str = Field(min_length=1, max_length=100000)
    amount: float | None = Field(default=None, ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=8)
    expires_in_days: int = Field(default=14, ge=1, le=365)


class AutomationCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    trigger_event: str = Field(min_length=2, max_length=100)
    condition: dict[str, Any] = Field(default_factory=dict)
    actions: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    enabled: bool = True


class GrowthBrainRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=10000)
    context: str | None = Field(default=None, max_length=20000)
    provider: str | None = Field(default=None, max_length=50)
    model: str = Field(default="auto", max_length=200)
    free_only: bool = True
