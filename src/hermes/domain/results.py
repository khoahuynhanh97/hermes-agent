from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Result(Generic[T]):
    value: T | None = None
    error_code: str | None = None
    message: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_code is None

    @staticmethod
    def success(value: T) -> "Result[T]":
        return Result(value=value)

    @staticmethod
    def failure(error_code: str, message: str | None = None) -> "Result[T]":
        if not error_code:
            raise ValueError("error_code cannot be empty for a failure result")
        return Result(error_code=error_code, message=message)

