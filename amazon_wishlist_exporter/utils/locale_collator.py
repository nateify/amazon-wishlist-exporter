import locale
from contextlib import contextmanager

from .logger_config import logger


class Locale(str):
    def __new__(cls, locale_string):
        return str.__new__(cls, locale_string)


class Collator:
    warning_logged = False

    def __init__(self, locale_string):
        self.locale_string = locale_string

    @classmethod
    def createInstance(cls, locale_string):
        return cls(locale_string)

    @contextmanager
    def _set_locale(self):
        old_locale = locale.getlocale(locale.LC_COLLATE)
        try:
            try:
                locale.setlocale(locale.LC_COLLATE, self.locale_string)
                yield locale.strxfrm  # Return transformation function
            except locale.Error:
                if not Collator.warning_logged:
                    logger.warning(
                        f"PyICU not found, and locale '{self.locale_string}' not available; falling back to C locale for collation."
                    )
                    Collator.warning_logged = True  # Set the flag to True after logging
                    locale.setlocale(locale.LC_COLLATE, "C")
                yield locale.strxfrm  # Return transformation function with fallback
        finally:
            locale.setlocale(locale.LC_COLLATE, old_locale)

    def getSortKey(self, string):
        with self._set_locale() as transform:
            return transform(string)
