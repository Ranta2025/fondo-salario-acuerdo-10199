"""Tests for band/scale mapping (scales.py)."""

from fondo_salario.domain.scales import (
    default_responsibility_bands,
    default_seniority_bands,
    map_band,
)


def test_responsibility_band_edge_values():
    bands = default_responsibility_bands()
    # Each boundary value (both ends of every band).
    assert map_band(bands, 1) == 1
    assert map_band(bands, 5) == 1
    assert map_band(bands, 6) == 2
    assert map_band(bands, 10) == 2
    assert map_band(bands, 11) == 3
    assert map_band(bands, 15) == 3
    assert map_band(bands, 16) == 4
    assert map_band(bands, 20) == 4
    assert map_band(bands, 21) == 5
    assert map_band(bands, 25) == 5


def test_responsibility_band_out_of_range_returns_none():
    bands = default_responsibility_bands()
    assert map_band(bands, 0) is None
    assert map_band(bands, 26) is None
    assert map_band(bands, -1) is None


def test_seniority_band_edge_values():
    bands = default_seniority_bands()
    assert map_band(bands, 0) == 1
    assert map_band(bands, 7) == 1
    assert map_band(bands, 8) == 2
    assert map_band(bands, 14) == 2
    assert map_band(bands, 15) == 3
    assert map_band(bands, 21) == 3
    assert map_band(bands, 22) == 4
    assert map_band(bands, 28) == 4
    assert map_band(bands, 29) == 5


def test_seniority_band_open_upper_bound():
    bands = default_seniority_bands()
    # 29+ maps to 5 for the whole valid seniority range and beyond.
    assert map_band(bands, 60) == 5
    assert map_band(bands, 100) == 5
    assert map_band(bands, -1) is None
