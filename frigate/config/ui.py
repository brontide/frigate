from enum import Enum
from typing import Optional

from pydantic import Field

from .base import FrigateBaseModel

__all__ = [
    "TimeFormatEnum",
    "DateTimeStyleEnum",
    "UnitSystemEnum",
    "InferenceThresholdConfig",
    "UIConfig",
]


class TimeFormatEnum(str, Enum):
    browser = "browser"
    hours12 = "12hour"
    hours24 = "24hour"


class DateTimeStyleEnum(str, Enum):
    full = "full"
    long = "long"
    medium = "medium"
    short = "short"


class UnitSystemEnum(str, Enum):
    imperial = "imperial"
    metric = "metric"


class InferenceThresholdConfig(FrigateBaseModel):
    warning: int = Field(
        default=50,
        title="Warning threshold (ms)",
        description="Inference speed in ms above which a warning is shown in the UI.",
    )
    error: int = Field(
        default=100,
        title="Error threshold (ms)",
        description="Inference speed in ms above which an error is shown in the UI.",
    )


class UIConfig(FrigateBaseModel):
    timezone: Optional[str] = Field(default=None, title="Override UI timezone.")
    time_format: TimeFormatEnum = Field(
        default=TimeFormatEnum.browser, title="Override UI time format."
    )
    date_style: DateTimeStyleEnum = Field(
        default=DateTimeStyleEnum.short, title="Override UI dateStyle."
    )
    time_style: DateTimeStyleEnum = Field(
        default=DateTimeStyleEnum.medium, title="Override UI timeStyle."
    )
    unit_system: UnitSystemEnum = Field(
        default=UnitSystemEnum.metric, title="The unit system to use for measurements."
    )
    inference_threshold: InferenceThresholdConfig = Field(
        default_factory=InferenceThresholdConfig,
        title="Inference threshold",
        description="Thresholds for detector inference speed warnings in the UI.",
    )
