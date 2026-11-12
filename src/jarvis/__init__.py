"""J.A.R.V.I.S. - an original local-first Windows AI desktop assistant."""

__version__ = "0.1.0"
APP_NAME = "JARVIS"


def _prime_stdlib_lazy_imports() -> None:
    """Force Python 3.15's lazy stdlib imports to resolve before Qt loads.

    Python 3.15 declares ``ThreadPoolExecutor`` with ``lazy from .thread``.
    Importing PySide6 first leaves the attribute as an unresolved
    ``lazy_import`` object, which makes ``asyncio.to_thread`` raise
    ``TypeError: 'lazy_import' object is not callable`` on every synchronous
    tool call. Accessing the attribute once here caches the real class.
    """
    try:
        import concurrent.futures

        _ = concurrent.futures.ThreadPoolExecutor
        _ = concurrent.futures.ProcessPoolExecutor
    except Exception:  # pragma: no cover - defensive only
        pass


_prime_stdlib_lazy_imports()