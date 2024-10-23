import locale
from contextlib import contextmanager


class Locale(str):
    def __new__(cls, locale_string):
        return str.__new__(cls, locale_string)


class Collator:
    def __init__(self, locale_string):
        self.locale_string = locale_string

    @classmethod
    def createInstance(cls, locale_string):
        return cls(locale_string)

    @contextmanager
    def _set_locale(self):
        old_locale = locale.getlocale(locale.LC_COLLATE)
        try:
            locale.setlocale(locale.LC_COLLATE, self.locale_string)
            yield locale.strxfrm  # Return transformation function
        finally:
            locale.setlocale(locale.LC_COLLATE, old_locale)

    def getSortKey(self, string):
        with self._set_locale() as transform:
            return transform(string)
