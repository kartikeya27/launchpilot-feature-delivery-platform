from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

Environment = Literal["production", "staging", "development"]

class FlagCreate(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{2,71}$", max_length=72)
    name: str = Field(min_length=3, max_length=120)
    description: str = Field(default="", max_length=500)
    environment: Environment = "production"
    owner: str = Field(default="Platform team", min_length=2, max_length=80)
    enabled: bool = False
    rollout: int = Field(default=0, ge=0, le=100)

class FlagUpdate(BaseModel):
    version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=3, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    owner: str | None = Field(default=None, min_length=2, max_length=80)
    enabled: bool | None = None
    rollout: int | None = Field(default=None, ge=0, le=100)

class FlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    key: str
    name: str
    description: str
    environment: str
    owner: str
    enabled: bool
    rollout: int
    version: int
    created_at: datetime
    updated_at: datetime

class TargetingRules(BaseModel):
    countries: list[str] = Field(default_factory=list, max_length=20)
    plans: list[str] = Field(default_factory=list, max_length=20)
    match: Literal["all", "any"] = "all"

    @field_validator("countries")
    @classmethod
    def validate_countries(cls, values: list[str]) -> list[str]:
        if any(len(x) != 2 or not x.isalpha() or not x.isascii() for x in values):
            raise ValueError("Countries must be ISO-3166 two-letter codes")
        return sorted(set(x.upper() for x in values))

    @__import__("pydantic").field_validator("plans")
    @classmethod
    def validate_plans(cls, values: list[str]) -> list[str]:
        if any(not (1 <= len(x) <= 32) or not x.isascii() or not x.replace("_", "").isalnum() for x in values):
            raise ValueError("Plans must be alphanumeric identifiers")
        return sorted(set(x.lower() for x in values))


class EvalRequest(BaseModel):
    key: str = Field(min_length=1, max_length=72)
    environment: Environment = "production"
    user_id: str = Field(min_length=1, max_length=128)
    track: bool = True
    country: str | None = Field(default=None, min_length=2, max_length=2, pattern=r'^[A-Za-z]{2}

class EvalResponse(BaseModel):
    key: str
    environment: str
    enabled: bool
    reason: str
    bucket: float
    rollout: int
    flag_version: int

class ConversionRequest(BaseModel):
    key: str = Field(min_length=1, max_length=72)
    environment: Environment = "production"
    user_id: str = Field(min_length=1, max_length=128)
)
    plan: str | None = Field(default=None, min_length=1, max_length=32, pattern=r'^[A-Za-z0-9_]+

class EvalResponse(BaseModel):
    key: str
    environment: str
    enabled: bool
    reason: str
    bucket: float
    rollout: int
    flag_version: int

class ConversionRequest(BaseModel):
    key: str = Field(min_length=1, max_length=72)
    environment: Environment = "production"
    user_id: str = Field(min_length=1, max_length=128)
)

class EvalResponse(BaseModel):
    key: str
    environment: str
    enabled: bool
    reason: str
    bucket: float
    rollout: int
    flag_version: int

class ConversionRequest(BaseModel):
    key: str = Field(min_length=1, max_length=72)
    environment: Environment = "production"
    user_id: str = Field(min_length=1, max_length=128)
