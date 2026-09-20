from __future__ import annotations

import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Register(StrictModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=256)
    name: str = Field(min_length=1, max_length=100)

    @field_validator("email")
    @classmethod
    def email_valid(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("E-mail inválido")
        return value

    @field_validator("name")
    @classmethod
    def name_valid(cls, value):
        if not value.strip():
            raise ValueError("Informe seu nome")
        return value.strip()


class Login(StrictModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class Weights(StrictModel):
    price: float = Field(default=40, ge=0, le=100)
    location: float = Field(default=35, ge=0, le=100)
    quality: float = Field(default=25, ge=0, le=100)

    @model_validator(mode="after")
    def nonzero(self):
        if self.price + self.location + self.quality <= 0:
            raise ValueError("Ao menos uma prioridade precisa ter peso maior que zero")
        return self


class Profile(StrictModel):
    name: str = Field(default="Minha primeira casa", min_length=1, max_length=100)
    budget_max: float | None = Field(default=330000, gt=0, le=1e9)
    area_min: float | None = Field(default=35, gt=0, le=100000)
    area_max: float | None = Field(default=70, gt=0, le=100000)
    bedrooms_min: int = Field(default=2, ge=0, le=100)
    parking_min: int = Field(default=0, ge=0, le=100)
    metro_max: float | None = Field(default=15, gt=0, le=300)
    monthly_max: float | None = Field(default=580, gt=0, le=1e7)
    cities: list[str] = Field(default_factory=lambda: ["São Paulo"], max_length=50)
    neighborhoods: list[str] = Field(default_factory=list, max_length=100)
    require_elevator: bool = False
    weights: Weights = Field(default_factory=Weights)
    alert_drop_percent: float = Field(default=5, ge=0, le=100)
    exclude_unknown_required: bool = False

    @field_validator("cities", "neighborhoods")
    @classmethod
    def valid_locations(cls, values):
        if any(len(v) > 150 for v in values):
            raise ValueError("Localidade muito longa")
        return list(dict.fromkeys(v.strip() for v in values if v.strip()))

    @model_validator(mode="after")
    def valid_range(self):
        if self.area_min is not None and self.area_max is not None and self.area_min > self.area_max:
            raise ValueError("Área mínima não pode exceder a máxima")
        return self


class Assessments(StrictModel):
    condition: Literal["good", "needs_work", "unknown"] = "unknown"
    sunlight: Literal["good", "poor", "unknown"] = "unknown"
    ventilation: Literal["good", "poor", "unknown"] = "unknown"
    documentation: Literal["verified", "pending", "unknown"] = "unknown"


class Tracking(StrictModel):
    saved: bool | None = None
    stage: Literal["saved", "contacted", "visit", "visited", "offer", "rejected", "bought"] | None = None
    notes: str | None = Field(default=None, max_length=20000)
    visit_at: str | None = Field(default=None, max_length=40)
    checklist: dict[str, bool] | None = None
    assessments: Assessments | None = None

    @field_validator("checklist")
    @classmethod
    def checks(cls, value):
        if value is not None and (len(value) > 50 or any(len(k) > 150 for k in value)):
            raise ValueError("Checklist excede o limite")
        return value

    @field_validator("visit_at")
    @classmethod
    def visit(cls, value):
        if value:
            from datetime import datetime
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                raise ValueError("Data de visita inválida")
        return value or None


class SourceCreate(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=10, max_length=2048)
    authorized: Literal[True]


class SourceUpdate(StrictModel):
    enabled: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)


class CommitPreview(StrictModel):
    preview_id: str = Field(min_length=10, max_length=100)


class AlertUpdate(StrictModel):
    read: bool


class Budget(StrictModel):
    price: float = Field(gt=0, le=1e9)
    down_payment: float = Field(ge=0, le=1e9)
    annual_rate: float = Field(ge=0, le=100)
    months: int = Field(ge=1, le=600)
    monthly_costs: float = Field(default=0, ge=0, le=1e7)
    acquisition_costs: float = Field(default=0, ge=0, le=1e9)
    reserve: float = Field(default=0, ge=0, le=1e9)
    model: Literal["price", "sac"] = "price"
