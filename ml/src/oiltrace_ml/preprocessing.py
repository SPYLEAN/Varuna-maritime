from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Sequence

import numpy as np


PreprocessingMethod = Literal["fixed_db", "robust_percentile"]
InvalidValuePolicy = Literal["error", "fill"]


@dataclass(frozen=True)
class SARPreprocessingConfig:
    """Explicit preprocessing settings for calibrated Sigma0 dB channels.

    ``db_min`` and ``db_max`` are ordered exactly like ``channel_order``.  The
    defaults are deliberately visible starter bounds for Sentinel-1 VV/VH; a
    production dataset should profile and version its chosen bounds.
    """

    method: PreprocessingMethod = "fixed_db"
    channel_order: tuple[str, ...] = ("VV", "VH")
    db_min: tuple[float, ...] = (-30.0, -35.0)
    db_max: tuple[float, ...] = (0.0, -5.0)
    lower_percentile: float = 1.0
    upper_percentile: float = 99.0
    invalid_value_policy: InvalidValuePolicy = "error"
    invalid_fill_db: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "channel_order", tuple(str(v).upper() for v in self.channel_order))
        object.__setattr__(self, "db_min", tuple(float(v) for v in self.db_min))
        object.__setattr__(self, "db_max", tuple(float(v) for v in self.db_max))

        if self.method not in ("fixed_db", "robust_percentile"):
            raise ValueError(f"Unsupported SAR preprocessing method: {self.method}")
        if not self.channel_order:
            raise ValueError("channel_order must contain at least one channel")
        if len(set(self.channel_order)) != len(self.channel_order):
            raise ValueError(f"channel_order contains duplicates: {self.channel_order}")
        if len(self.db_min) != len(self.channel_order) or len(self.db_max) != len(self.channel_order):
            raise ValueError("db_min/db_max must have one value per channel in channel_order")
        if any(hi <= lo for lo, hi in zip(self.db_min, self.db_max)):
            raise ValueError("Every db_max value must be greater than its matching db_min")
        if not 0.0 <= self.lower_percentile < self.upper_percentile <= 100.0:
            raise ValueError("Percentiles must satisfy 0 <= lower < upper <= 100")
        if self.invalid_value_policy not in ("error", "fill"):
            raise ValueError(f"Unsupported invalid value policy: {self.invalid_value_policy}")
        if self.invalid_value_policy == "fill" and self.invalid_fill_db is None:
            raise ValueError("invalid_fill_db is required when invalid_value_policy='fill'")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["channel_order"] = list(self.channel_order)
        result["db_min"] = list(self.db_min)
        result["db_max"] = list(self.db_max)
        result["input_scale"] = "sigma0_db"
        result["output_range"] = [0.0, 1.0]
        return result

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "SARPreprocessingConfig":
        if values.get("input_scale", "sigma0_db") != "sigma0_db":
            raise ValueError("SAR preprocessing metadata must declare input_scale='sigma0_db'")
        if values.get("output_range", [0.0, 1.0]) != [0.0, 1.0]:
            raise ValueError("SAR preprocessing metadata must declare output_range=[0.0, 1.0]")
        allowed = {
            "method",
            "channel_order",
            "db_min",
            "db_max",
            "lower_percentile",
            "upper_percentile",
            "invalid_value_policy",
            "invalid_fill_db",
        }
        return cls(**{key: value for key, value in values.items() if key in allowed})


def _replace_or_reject_invalid(channel: np.ndarray, config: SARPreprocessingConfig, name: str) -> np.ndarray:
    finite = np.isfinite(channel)
    if finite.all():
        return channel

    invalid_count = int(channel.size - finite.sum())
    if config.invalid_value_policy == "error":
        raise ValueError(f"Channel {name} contains {invalid_count} non-finite or nodata values")

    result = channel.copy()
    result[~finite] = float(config.invalid_fill_db)
    return result


def preprocess_sar(
    image: np.ndarray,
    config: SARPreprocessingConfig,
    *,
    return_stats: bool = False,
) -> np.ndarray | tuple[np.ndarray, list[dict[str, float | str]]]:
    """Normalize a ``[channels, height, width]`` Sigma0 dB array.

    Fixed mode clips each channel to its configured dB interval and linearly
    maps that interval to [0, 1]. Robust mode derives the clipping interval
    from the configured per-scene percentiles and records the realized bounds.
    """

    array = np.asarray(image, dtype=np.float32)
    if array.ndim != 3:
        raise ValueError(f"SAR image must have shape [channels, height, width], got {array.shape}")
    if array.shape[0] != len(config.channel_order):
        raise ValueError(
            f"SAR channel count {array.shape[0]} does not match configured order {config.channel_order}"
        )
    if array.shape[1] < 1 or array.shape[2] < 1:
        raise ValueError(f"SAR image has invalid spatial dimensions: {array.shape[1:]}")

    normalized = np.empty_like(array, dtype=np.float32)
    stats: list[dict[str, float | str]] = []
    for index, name in enumerate(config.channel_order):
        channel = _replace_or_reject_invalid(array[index], config, name)
        if config.method == "fixed_db":
            lower = config.db_min[index]
            upper = config.db_max[index]
        else:
            lower, upper = np.percentile(
                channel,
                [config.lower_percentile, config.upper_percentile],
            ).astype(float)
            if not np.isfinite(lower) or not np.isfinite(upper) or upper <= lower:
                raise ValueError(
                    f"Robust percentile bounds are invalid for channel {name}: {lower}, {upper}"
                )

        normalized[index] = np.clip((channel - lower) / (upper - lower), 0.0, 1.0)
        stats.append({"channel": name, "lower_db": float(lower), "upper_db": float(upper)})

    if not np.isfinite(normalized).all():
        raise ValueError("SAR preprocessing produced non-finite values")
    return (normalized, stats) if return_stats else normalized


def config_for_channels(
    channel_order: Sequence[str],
    *,
    method: PreprocessingMethod = "fixed_db",
    db_min: Sequence[float] | None = None,
    db_max: Sequence[float] | None = None,
    lower_percentile: float = 1.0,
    upper_percentile: float = 99.0,
    invalid_value_policy: InvalidValuePolicy = "error",
    invalid_fill_db: float | None = None,
) -> SARPreprocessingConfig:
    """Construct a config without silently assigning bounds to unknown bands."""

    order = tuple(str(value).upper() for value in channel_order)
    default_bounds = {"VV": (-30.0, 0.0), "VH": (-35.0, -5.0)}
    if db_min is None or db_max is None:
        unknown = [name for name in order if name not in default_bounds]
        if unknown:
            raise ValueError(f"Explicit dB bounds are required for channels: {unknown}")
        if db_min is None:
            db_min = tuple(default_bounds[name][0] for name in order)
        if db_max is None:
            db_max = tuple(default_bounds[name][1] for name in order)
    return SARPreprocessingConfig(
        method=method,
        channel_order=order,
        db_min=tuple(db_min),
        db_max=tuple(db_max),
        lower_percentile=lower_percentile,
        upper_percentile=upper_percentile,
        invalid_value_policy=invalid_value_policy,
        invalid_fill_db=invalid_fill_db,
    )
