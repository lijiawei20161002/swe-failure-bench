"""Tests for package dependency resolver. Run: pytest tests/ -x"""
import pytest
from resolver import Resolver, ConflictError, Constraint, Version, parse_requirement


# ── version parsing ───────────────────────────────────────────────────────────

class TestVersion:
    def test_parse_full(self):
        v = Version.parse("1.2.3")
        assert v == Version(1, 2, 3)

    def test_parse_short(self):
        assert Version.parse("2.0") == Version(2, 0, 0)

    def test_ordering(self):
        assert Version.parse("1.0.0") < Version.parse("2.0.0")
        assert Version.parse("1.2.0") < Version.parse("1.3.0")
        assert Version.parse("1.0.1") > Version.parse("1.0.0")


# ── constraint satisfaction ───────────────────────────────────────────────────

class TestConstraint:
    def test_equal(self):
        c = Constraint.parse("==1.2.3")
        assert c.satisfied_by(Version(1, 2, 3)) is True
        assert c.satisfied_by(Version(1, 2, 4)) is False

    def test_not_equal(self):
        c = Constraint.parse("!=1.0.0")
        assert c.satisfied_by(Version(1, 0, 0)) is False
        assert c.satisfied_by(Version(1, 0, 1)) is True

    def test_greater_than_or_equal_includes_boundary(self):
        """>=1.0.0 must accept version 1.0.0 itself."""
        c = Constraint.parse(">=1.0.0")
        assert c.satisfied_by(Version(1, 0, 0)) is True, (
            ">=1.0.0 must be satisfied by 1.0.0 (boundary is inclusive)"
        )
        assert c.satisfied_by(Version(1, 0, 1)) is True
        assert c.satisfied_by(Version(0, 9, 9)) is False

    def test_less_than_or_equal_includes_boundary(self):
        """<=2.0.0 must accept version 2.0.0 itself."""
        c = Constraint.parse("<=2.0.0")
        assert c.satisfied_by(Version(2, 0, 0)) is True, (
            "<=2.0.0 must be satisfied by 2.0.0 (boundary is inclusive)"
        )
        assert c.satisfied_by(Version(1, 9, 9)) is True
        assert c.satisfied_by(Version(2, 0, 1)) is False

    def test_strict_greater(self):
        c = Constraint.parse(">1.0.0")
        assert c.satisfied_by(Version(1, 0, 0)) is False
        assert c.satisfied_by(Version(1, 0, 1)) is True

    def test_strict_less(self):
        c = Constraint.parse("<2.0.0")
        assert c.satisfied_by(Version(2, 0, 0)) is False
        assert c.satisfied_by(Version(1, 9, 9)) is True

    def test_range_inclusive_exclusive(self):
        """>=1.0,<2.0 includes 1.0 and excludes 2.0."""
        lo = Constraint.parse(">=1.0.0")
        hi = Constraint.parse("<2.0.0")
        assert lo.satisfied_by(Version(1, 0, 0)) is True
        assert hi.satisfied_by(Version(2, 0, 0)) is False
        assert lo.satisfied_by(Version(1, 5, 0)) and hi.satisfied_by(Version(1, 5, 0))


# ── requirement parsing ───────────────────────────────────────────────────────

class TestParseRequirement:
    def test_bare_name(self):
        name, cs = parse_requirement("requests")
        assert name == "requests"
        assert cs == []

    def test_single_constraint(self):
        name, cs = parse_requirement("requests>=2.0.0")
        assert name == "requests"
        assert len(cs) == 1
        assert cs[0].op == ">="

    def test_multi_constraint(self):
        name, cs = parse_requirement("urllib3>=1.21,<2.0")
        assert name == "urllib3"
        assert len(cs) == 2


# ── resolver: simple cases ────────────────────────────────────────────────────

class TestResolverBasic:
    def test_single_package_no_deps(self):
        r = Resolver()
        r.add_package("requests", "2.28.0")
        result = r.resolve(["requests"])
        assert result == {"requests": "2.28.0"}

    def test_picks_newest_satisfying_version(self):
        r = Resolver()
        r.add_package("pkg", "1.0.0")
        r.add_package("pkg", "2.0.0")
        r.add_package("pkg", "3.0.0")
        result = r.resolve(["pkg<3.0.0"])
        assert result["pkg"] == "2.0.0"

    def test_exact_version_constraint(self):
        r = Resolver()
        r.add_package("pkg", "1.0.0")
        r.add_package("pkg", "2.0.0")
        result = r.resolve(["pkg==1.0.0"])
        assert result["pkg"] == "1.0.0"

    def test_exact_boundary_gte(self):
        """Requesting pkg>=2.0.0 must select 2.0.0 when that's the only match."""
        r = Resolver()
        r.add_package("pkg", "2.0.0")
        result = r.resolve(["pkg>=2.0.0"])
        assert result["pkg"] == "2.0.0", (
            ">=2.0.0 must accept 2.0.0 as a valid version"
        )

    def test_exact_boundary_lte(self):
        r = Resolver()
        r.add_package("pkg", "1.0.0")
        result = r.resolve(["pkg<=1.0.0"])
        assert result["pkg"] == "1.0.0", (
            "<=1.0.0 must accept 1.0.0 as a valid version"
        )

    def test_conflict_raises(self):
        r = Resolver()
        r.add_package("pkg", "1.0.0")
        with pytest.raises(ConflictError):
            r.resolve(["pkg>=2.0.0"])

    def test_package_not_found_raises(self):
        r = Resolver()
        with pytest.raises(ConflictError):
            r.resolve(["missing"])


# ── resolver: dependency chains ───────────────────────────────────────────────

class TestResolverDeps:
    def test_direct_dep_resolved(self):
        r = Resolver()
        r.add_package("app", "1.0.0", deps=["lib>=1.0.0"])
        r.add_package("lib", "1.2.0")
        result = r.resolve(["app"])
        assert result["app"] == "1.0.0"
        assert result["lib"] == "1.2.0"

    def test_transitive_dep_resolved(self):
        r = Resolver()
        r.add_package("app", "1.0.0", deps=["mid>=1.0.0"])
        r.add_package("mid", "1.0.0", deps=["base>=2.0.0"])
        r.add_package("base", "2.1.0")
        result = r.resolve(["app"])
        assert result["base"] == "2.1.0", (
            "Transitive dependency 'base' must be resolved"
        )

    def test_transitive_conflict_detected(self):
        """
        app requires libA>=2.0, but libA 2.x requires libB>=3.0.
        Only libB 2.x is available → transitive conflict must be detected.
        """
        r = Resolver()
        r.add_package("app",  "1.0.0", deps=["libA>=2.0.0"])
        r.add_package("libA", "2.0.0", deps=["libB>=3.0.0"])
        r.add_package("libB", "2.9.0")   # only 2.x available, 3.x needed
        with pytest.raises(ConflictError):
            r.resolve(["app"])

    def test_dep_range_respected(self):
        """Dependency version range must be enforced."""
        r = Resolver()
        r.add_package("app", "1.0.0", deps=["lib>=1.0.0,<2.0.0"])
        r.add_package("lib", "2.5.0")   # too new
        r.add_package("lib", "1.8.0")   # in range
        result = r.resolve(["app"])
        assert result["lib"] == "1.8.0"

    def test_conflicting_direct_and_transitive_requirements(self):
        """
        top-level: libX>=2.0.0
        app dep:   libX<2.0.0
        These conflict — resolver must raise.
        """
        r = Resolver()
        r.add_package("app",  "1.0.0", deps=["libX<2.0.0"])
        r.add_package("libX", "1.9.0")
        r.add_package("libX", "2.0.0")
        with pytest.raises(ConflictError):
            r.resolve(["app", "libX>=2.0.0"])
