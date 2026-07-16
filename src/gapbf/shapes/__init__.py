"""Shape-based pattern candidate generation.

Turns human-drawn / library shapes into ranked, legal Android pattern
candidates for any N x N grid. See SHAPE_MODE_PLAN.md.
"""

from .geometry import Point, Polyline, render_to_nodes
from .library import LIBRARY, Shape
from .source import ShapeCandidateSource

__all__ = [
    "Point",
    "Polyline",
    "Shape",
    "LIBRARY",
    "ShapeCandidateSource",
    "render_to_nodes",
]
