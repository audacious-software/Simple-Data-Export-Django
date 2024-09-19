import importlib

import unicodecsv

from django.conf import settings

CACHED_IDENTIFIERS = {}

def fetch_export_identifier(original_identifier):
    if original_identifier in CACHED_IDENTIFIERS:
        return CACHED_IDENTIFIERS[original_identifier]

    for app in settings.INSTALLED_APPS:
        try:
            export_api = importlib.import_module(app + '.simple_data_export_api')

            new_identifier = export_api.obfuscate_identifier(original_identifier)

            if new_identifier is not None:
                CACHED_IDENTIFIERS[original_identifier] = new_identifier

                return new_identifier
        except ImportError:
            pass
        except AttributeError:
            pass

    CACHED_IDENTIFIERS[original_identifier] = original_identifier

    return original_identifier

class UnicodeWriter: # pylint: disable=old-style-class
    def __init__(self, file_stream, dialect=unicodecsv.excel, encoding='utf-8-sig', **kwds):
        self.writer = unicodecsv.writer(file_stream, dialect=dialect, encoding=encoding, **kwds)

    def writerow(self, row):
        self.writer.writerow(row)

    def writerows(self, rows):
        self.writer.writerows(rows)
