"""A crop window in fractions of the leaf — what every window of the scan tools is, whatever the book.

A fraction, not a pixel: the frames of one дело drift by a few pixels in size, and a window measured on one leaf
lands on the next only in fractions.
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["FULL_WIDTH", "Box"]

FULL_WIDTH = (0.0, 1.0)


@dataclass(frozen=True)
class Box:
    """A crop window in leaf fractions, x0 < x1 and y0 < y1, all within [0, 1]."""
    x0: float
    y0: float
    x1: float
    y1: float

    def pixels(self, width: int, height: int) -> tuple[int, int, int, int]:
        return (int(width * self.x0), int(height * self.y0),
                int(width * self.x1), int(height * self.y1))

    def __str__(self) -> str:
        return f"x {self.x0:g}–{self.x1:g}, y {self.y0:g}–{self.y1:g}"
