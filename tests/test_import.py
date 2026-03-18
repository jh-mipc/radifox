def test_import_radifox():
    import radifox  # noqa: F401
    assert "unknown" not in radifox.__version__
