from importlib.metadata import PackageNotFoundError, version

try:
    VERSION = version("shelf-to-shop")
except PackageNotFoundError:  # running from a source tree without install
    VERSION = "0.0.0"
