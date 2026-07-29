from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import UserDefinedType


class Vector(UserDefinedType[tuple[float, ...]]):
    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **_: object) -> str:
        return f"vector({self.dimensions})"

    def bind_processor(self, dialect: Dialect) -> Callable[[Sequence[float] | None], str | None]:
        def process(value: Sequence[float] | None) -> str | None:
            if value is None:
                return None
            if len(value) != self.dimensions:
                raise ValueError(f"Expected vector with {self.dimensions} dimensions")
            return "[" + ",".join(str(float(item)) for item in value) + "]"

        return process

    def result_processor(
        self,
        dialect: Dialect,
        coltype: object,
    ) -> Callable[[Any], tuple[float, ...] | None]:
        def process(value: Any) -> tuple[float, ...] | None:
            if value is None:
                return None
            if isinstance(value, str):
                raw = value.strip("[]")
                if not raw:
                    return ()
                return tuple(float(item) for item in raw.split(","))
            if isinstance(value, Sequence):
                return tuple(float(item) for item in value)
            return None

        return process
