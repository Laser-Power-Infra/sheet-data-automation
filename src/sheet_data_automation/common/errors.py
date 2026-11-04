class ConfigError(RuntimeError):
    """Raised when required configuration is missing."""


class ScrapeError(RuntimeError):
    """Raised when a source page or PDF could not be scraped."""


class ParseError(RuntimeError):
    """Raised when an expected value is missing from a page or PDF."""


class SheetError(RuntimeError):
    """Raised when Google Sheets cannot be opened, read, or written."""
