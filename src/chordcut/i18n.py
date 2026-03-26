"""Internationalization support for ChordCut.

All user-facing strings must be wrapped with _() or ngettext() from this module
and preceded by a ``# Translators:`` comment explaining the context.

To generate a .pot translation template::

    xgettext --add-comments=Translators -o locale/chordcut.pot --from-code=UTF-8 \\
        src/chordcut/*.py src/chordcut/**/*.py
"""

import gettext
import locale
import logging
import os
import sys

from chordcut.utils.paths import get_locale_dir

logger = logging.getLogger(__name__)


def _get_system_language() -> str | None:
    """Get the system language code for translation lookup.

    Returns a language code like 'ru' or 'en', or None if detection fails.
    """
    # Try Windows-specific approach first
    if sys.platform == 'win32':
        try:
            import ctypes
            # Get Windows UI language (returns LCID, we need to convert)
            # GetThreadLocale returns a locale identifier
            windll = ctypes.windll.kernel32
            # Try GetUserDefaultUILanguage first (available on Windows Vista+)
            if hasattr(windll, 'GetUserDefaultUILanguage'):
                lcid = windll.GetUserDefaultUILanguage()
                # Convert LCID to locale string
                # Common mappings
                lcid_map = {
                    0x0409: 'en',  # English (US)
                    0x0809: 'en',  # English (UK)
                    0x0419: 'ru',  # Russian
                    0x0425: 'et',  # Estonian
                    0x0419: 'ru',  # Russian (Russia)
                    0x0819: 'ru',  # Russian (Moldova)
                }
                if lcid in lcid_map:
                    logger.debug(f"Windows LCID {lcid:#x} -> {lcid_map[lcid]}")
                    return lcid_map[lcid]
                # Try to use locale to convert
                try:
                    locale_name = locale.windows_locale.get(lcid)
                    if locale_name:
                        lang = locale_name.split('_')[0].lower()
                        logger.debug(f"Windows LCID {lcid:#x} -> {lang}")
                        return lang
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Windows locale detection failed: {e}")

    # Try standard locale approach
    try:
        # Set locale to user's default to get correct values
        locale.setlocale(locale.LC_ALL, '')
        lang = locale.getlocale()[0]
        # Restore LC_NUMERIC to "C" — MPV requires it.
        locale.setlocale(locale.LC_NUMERIC, 'C')
        if lang:
            # Extract just the language part (e.g., 'ru' from 'ru_RU')
            result = lang.split('_')[0].lower()
            logger.debug(f"Locale detection: {lang} -> {result}")
            return result
    except Exception as e:
        logger.debug(f"Locale detection failed: {e}")

    # Fallback: try environment variable
    lang = os.environ.get('LANG', '')
    if lang:
        result = lang.split('_')[0].lower().split('.')[0]
        logger.debug(f"LANG env: {lang} -> {result}")
        return result

    return None


current_language: str = _get_system_language() or 'en'


def _init_translation():
    """Initialize the translation object based on system locale."""
    localedir = get_locale_dir()
    lang = current_language

    if lang:
        logger.debug(f"Detected system language: {lang}, locale dir: {localedir}")

    try:
        # Try to load translation for the detected language
        translation = gettext.translation(
            "chordcut",
            localedir=str(localedir),
            languages=[lang] if lang else None,
            fallback=True,
        )
        if lang and translation.info().get('language'):
            logger.info(f"Loaded {lang} translation")
        else:
            logger.debug("Using fallback (English) strings")
    except Exception as e:
        logger.warning(f"Failed to load translation: {e}, using fallback")
        translation = gettext.translation("chordcut", fallback=True)

    return translation


_translation = _init_translation()

_ = _translation.gettext
ngettext = _translation.ngettext
