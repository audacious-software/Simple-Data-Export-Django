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
