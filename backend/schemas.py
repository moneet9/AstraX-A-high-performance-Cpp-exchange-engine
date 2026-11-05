from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=128)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class AppleToken(BaseModel):
    identity_token: str


class OrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(min_length=1, max_length=24)
    side: Literal["buy", "sell"]
    type: Literal["market", "limit", "stop", "stop_limit", "iceberg", "pegged"]
    quantity: StrictInt = Field(gt=0, le=1_000_000)
    price_ticks: StrictInt = Field(default=0, ge=0)
    stop_price_ticks: StrictInt = Field(default=0, ge=0)
    visible_quantity: StrictInt = Field(default=0, ge=0)
    peg_offset_ticks: StrictInt = 0
    tif: Literal["GTC", "IOC", "FOK"] = "GTC"

    @model_validator(mode="after")
    def validate_integer_price_fields(self):
        if self.type in {"limit", "stop_limit", "iceberg"} and self.price_ticks <= 0:
            raise ValueError("price_ticks must be positive for priced orders")
        if self.type in {"market", "stop", "pegged"} and self.price_ticks != 0:
            raise ValueError("this order type does not accept price_ticks")
        if self.type in {"stop", "stop_limit"} and self.stop_price_ticks <= 0:
            raise ValueError("stop_price_ticks is required for stop orders")
        if self.type not in {"stop", "stop_limit"} and self.stop_price_ticks:
            raise ValueError("stop_price_ticks is supported only by stop orders")
        if self.type == "iceberg" and not 0 < self.visible_quantity < self.quantity:
            raise ValueError("iceberg visible_quantity must be between zero and quantity")
        if self.type != "iceberg" and self.visible_quantity:
            raise ValueError("visible_quantity is supported only by iceberg orders")
        if self.type == "pegged" and self.price_ticks:
            raise ValueError("pegged orders use peg_offset_ticks, not price_ticks")
        if self.type != "pegged" and self.peg_offset_ticks:
            raise ValueError("peg_offset_ticks is supported only by pegged orders")
        return self


class RefreshRequest(BaseModel):
    refresh_token: str


class DeleteAccountRequest(BaseModel):
    confirmation: Literal["DELETE"]

