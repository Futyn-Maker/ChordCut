"""Internationalization support for Groove.

All user-facing strings must be wrapped with _() or ngettext() from this module
and preceded by a ``# Translators:`` comment explaining the context.

To generate a .pot translation template::

    xgettext -c Translators -o locale/groove.pot --from-code=UTF-8 \
        src/groove/*.py src/groove/**/*.py
"""

import gettext

_translation = gettext.translation("groove", fallback=True)

_ = _translation.gettext
ngettext = _translation.ngettext
