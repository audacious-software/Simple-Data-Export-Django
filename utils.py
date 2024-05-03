import codecs
import csv
import cStringIO
import importlib

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

class UnicodeWriter:
    def __init__(self, f, dialect=csv.excel, encoding='utf-8-sig', **kwds):
        self.queue = cStringIO.StringIO()
        self.writer = csv.writer(self.queue, dialect=dialect, **kwds)
        self.stream = f
        self.encoder = codecs.getincrementalencoder(encoding)()

    def writerow(self, row):
        self.writer.writerow([s.encode('utf-8') for s in row])
        data = self.queue.getvalue()
        data = data.decode('utf-8')
        data = self.encoder.encode(data)
        self.stream.write(data)
        self.queue.truncate(0)

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)
