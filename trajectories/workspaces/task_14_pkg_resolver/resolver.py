"""
Package dependency resolver with version constraint satisfaction.

Given a set of packages and their version constraints, resolve a consistent
set of versions satisfying all constraints, or report a conflict.

Based on pip's resolver logic (PubGrub-inspired but simplified).

Constraint syntax:
  "pkg>=1.0"   "pkg>2.0"   "pkg<=3.0"   "pkg<4.0"
  "pkg==1.2"   "pkg!=1.1"

Public API:
    resolver = Resolver()
    resolver.add_package("requests", "2.28.0",
        deps=["urllib3>=1.21,<2", "certifi>=2017.4"])
    result = resolver.resolve(["requests>=2.0"])
    # → {"requests": "2.28.0", "urllib3": "1.26.14", ...}
    # or raises ConflictError
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


class ConflictError(Exception):
    pass


class InvalidConstraint(Exception):
    pass


# ── version ────────────────────────────────────────────────────────────────────

@dataclass(order=True, frozen=True)
class Version:
    major: int
    minor: int
    patch: int

    @staticmethod
    def parse(s: str) -> "Version":
        parts = [int(x) for x in s.strip().split(".")]
        while len(parts) < 3:
            parts.append(0)
        return Version(*parts[:3])

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


# ── constraint ────────────────────────────────────────────────────────────────

_OP_RE = re.compile(r"^(!=|>=|<=|==|>|<)(.+)$")


@dataclass
class Constraint:
    op: str
    version: Version

    @staticmethod
    def parse(s: str) -> "Constraint":
        m = _OP_RE.match(s.strip())
        if not m:
            raise InvalidConstraint(f"Cannot parse constraint: {s!r}")
        return Constraint(m.group(1), Version.parse(m.group(2)))

    def satisfied_by(self, v: Version) -> bool:
        if self.op == "==":
            return v == self.version
        if self.op == "!=":
            return v != self.version
        if self.op == ">=":
            return v >= self.version
        if self.op == "<=":
            return v <= self.version
        if self.op == ">":
            return v > self.version
        if self.op == "<":
            return v < self.version
        raise InvalidConstraint(f"Unknown op: {self.op}")


def parse_requirement(req: str) -> Tuple[str, List[Constraint]]:
    """Parse 'pkg>=1.0,<2.0' → ('pkg', [Constraint(>=,1.0), Constraint(<,2.0)])"""
    # Split on first operator character
    m = re.match(r"^([A-Za-z0-9_\-]+)(.*)", req.strip())
    if not m:
        raise InvalidConstraint(f"Cannot parse requirement: {req!r}")
    name = m.group(1)
    rest = m.group(2).strip()
    if not rest:
        return name, []
    constraints = [Constraint.parse(c.strip()) for c in rest.split(",") if c.strip()]
    return name, constraints


# ── package database ──────────────────────────────────────────────────────────

@dataclass
class PackageInfo:
    name: str
    version: Version
    deps: List[str] = field(default_factory=list)   # raw requirement strings


class Resolver:
    def __init__(self):
        self._packages: Dict[str, List[PackageInfo]] = {}

    def add_package(self, name: str, version: str, deps: List[str] | None = None):
        """Register a package version with its dependencies."""
        info = PackageInfo(name, Version.parse(version), deps or [])
        self._packages.setdefault(name, []).append(info)
        # Keep versions sorted descending (prefer newest)
        self._packages[name].sort(key=lambda p: p.version, reverse=True)

    def resolve(self, requirements: List[str]) -> Dict[str, str]:
        """
        Resolve a list of top-level requirements.
        Returns {name: version_str} or raises ConflictError.
        """
        selected: Dict[str, PackageInfo] = {}
        active_constraints: Dict[str, List[Constraint]] = {}

        def add_constraints(name: str, constraints: List[Constraint]) -> None:
            active_constraints.setdefault(name, []).extend(constraints)

        def satisfies_all(pkg: PackageInfo, name: str) -> bool:
            for c in active_constraints.get(name, []):
                if not c.satisfied_by(pkg.version):
                    return False
            return True

        # Parse top-level requirements
        queue: List[Tuple[str, List[Constraint]]] = []
        for req in requirements:
            name, constraints = parse_requirement(req)
            add_constraints(name, constraints)
            queue.append((name, constraints))

        visited = set()
        while queue:
            name, _ = queue.pop()
            if name in visited:
                continue
            visited.add(name)

            if name not in self._packages:
                raise ConflictError(f"Package {name!r} not found")

            candidates = self._packages[name]
            chosen = next(
                (p for p in candidates if satisfies_all(p, name)), None
            )
            if chosen is None:
                raise ConflictError(
                    f"No version of {name!r} satisfies constraints: "
                    + ", ".join(str(c.op + str(c.version))
                                for c in active_constraints.get(name, []))
                )
            selected[name] = chosen

            for dep_req in chosen.deps:
                dep_name, dep_constraints = parse_requirement(dep_req)
                add_constraints(dep_name, dep_constraints)
                if dep_name in selected:
                    if not satisfies_all(selected[dep_name], dep_name):
                        raise ConflictError(
                            f"No version of {dep_name!r} satisfies constraints: "
                            + ", ".join(str(c.op + str(c.version))
                                        for c in active_constraints.get(dep_name, []))
                        )
                elif dep_name not in visited:
                    queue.append((dep_name, dep_constraints))

        return {name: str(pkg.version) for name, pkg in selected.items()}
