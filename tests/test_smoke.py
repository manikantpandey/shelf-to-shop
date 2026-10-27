import importlib


def test_top_level_packages_import() -> None:
    for name in ("engine", "shelf", "integrations"):
        assert importlib.import_module(name) is not None
