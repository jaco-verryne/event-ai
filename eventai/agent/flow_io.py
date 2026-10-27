"""Plain conversions for flow components. Langflow passes tables (pandas DataFrames) and Data objects;
the eventai modules take dicts and Pydantic models."""

import math
from typing import Any


def _clean(value: Any) -> Any:
    # A table turns a missing value into NaN; the models expect None.
    return None if isinstance(value, float) and math.isnan(value) else value


def records(value: Any) -> list[dict]:
    """Rows from a table, a list of Data objects, one Data object, a dict or a list of dicts."""
    if value is None:
        return []
    if hasattr(value, "to_dict") and hasattr(value, "columns"):
        rows = value.to_dict(orient="records")
    elif isinstance(value, list):
        rows = [getattr(v, "data", v) for v in value]
    else:
        data = getattr(value, "data", value)
        rows = data.get("results", [data]) if isinstance(data, dict) else []
    return [{k: _clean(v) for k, v in row.items()} for row in rows if isinstance(row, dict)]
