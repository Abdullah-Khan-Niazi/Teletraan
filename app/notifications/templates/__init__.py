"""Language-aware template lookup for TELETRAAN notifications.

Provides ``get_template(key, language)`` which resolves a template
string from the correct language module.  Default is ``roman_urdu``.

Usage::

    from app.notifications.templates import get_template

    text = get_template("GREETING_RETURNING_CUSTOMER", "roman_urdu").format(
        customer_name="Ahmed",
    )
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.notifications.templates import (
    english_templates,
    roman_urdu_templates,
    urdu_templates,
)

_LANGUAGE_MODULES: dict[str, Any] = {
    "roman_urdu": roman_urdu_templates,
    "english": english_templates,
    "urdu": urdu_templates,
}

_DEFAULT_LANGUAGE = "roman_urdu"


def get_template(key: str, language: str = _DEFAULT_LANGUAGE) -> str:
    """Retrieve a message template by key and language.

    Falls back to ``roman_urdu`` if the requested language module does
    not contain the template.  Falls back to the raw key if no module
    has it (with a warning log).

    Args:
        key: Template constant name (e.g. ``"GREETING_NEW_CUSTOMER"``).
        language: Language code — ``"roman_urdu"``, ``"english"``, or ``"urdu"``.

    Returns:
        Template string with ``.format()``-style placeholders.
    """
    module = _LANGUAGE_MODULES.get(language)
    if module is None:
        logger.warning(
            "templates.unknown_language",
            language=language,
            key=key,
        )
        module = _LANGUAGE_MODULES[_DEFAULT_LANGUAGE]

    template = getattr(module, key, None)
    if template is not None:
        return template

    # Fallback to default language
    if language != _DEFAULT_LANGUAGE:
        fallback = getattr(_LANGUAGE_MODULES[_DEFAULT_LANGUAGE], key, None)
        if fallback is not None:
            logger.debug(
                "templates.fallback_to_default",
                key=key,
                requested=language,
            )
            return fallback

    logger.error("templates.missing_key", key=key, language=language)
    return key


def list_template_keys() -> list[str]:
    """Return all template key names from the default language module.

    Returns:
        Sorted list of template constant names.
    """
    module = _LANGUAGE_MODULES[_DEFAULT_LANGUAGE]
    return sorted(
        name
        for name in dir(module)
        if name.isupper() and not name.startswith("_")
    )
