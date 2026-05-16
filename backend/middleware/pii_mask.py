"""PII masking utilities for logs and Sentry events."""

import re


# Russian FIO pattern: 2-3 capitalized Cyrillic words (at least 2 chars each)
_FIO_PATTERN = re.compile(
    r'\b([A-ZА-ЯЁ][а-яё]{1,})\s+([A-ZА-ЯЁ][а-яё]{1,})(?:\s+([A-ZА-ЯЁ][а-яё]{1,}))?\b'
)

# INN: 10 or 12 consecutive digits (not part of a longer number)
_INN_PATTERN = re.compile(r'(?<!\d)(\d{2})\d{6,8}(\d{2})(?!\d)')

# Phone: +7 or 8 followed by 10 digits (with optional separators)
_PHONE_PATTERN = re.compile(
    r'(\+7|8)[\s\-]?(\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d)[\s\-]?(\d[\s\-]?\d[\s\-]?\d)'
)


def mask_fio(text: str) -> str:
    """Mask Russian FIO patterns in text.

    'Иванова Анна Петровна' -> 'И***ва А.П.'
    'Петров Иван' -> 'П***ов И.'
    """
    def _replace_fio(match):
        surname = match.group(1)
        name = match.group(2)
        patronymic = match.group(3)

        # Mask surname: first char + *** + last 2 chars
        if len(surname) > 3:
            masked_surname = surname[0] + '***' + surname[-2:]
        else:
            masked_surname = surname[0] + '***'

        # Name initial
        result = masked_surname + ' ' + name[0] + '.'

        # Patronymic initial if present
        if patronymic:
            result += patronymic[0] + '.'

        return result

    return _FIO_PATTERN.sub(_replace_fio, text)


def mask_inn(text: str) -> str:
    """Mask INN (10 or 12 digits) in text.

    '7701234567' -> '77******67'
    """
    def _replace_inn(match):
        first2 = match.group(1)
        last2 = match.group(2)
        full = match.group(0)
        middle_len = len(full) - 4
        return first2 + '*' * middle_len + last2

    return _INN_PATTERN.sub(_replace_inn, text)


def mask_phone(text: str) -> str:
    """Mask phone numbers in text.

    '+79161234567' -> '+7******567'
    '89161234567' -> '8******567'
    """
    def _replace_phone(match):
        prefix = match.group(1)  # +7 or 8
        last3_raw = match.group(3)
        last3 = re.sub(r'[\s\-]', '', last3_raw)
        return prefix + '******' + last3

    return _PHONE_PATTERN.sub(_replace_phone, text)


def mask_all(text: str) -> str:
    """Apply all PII masks to text."""
    text = mask_phone(text)
    text = mask_inn(text)
    text = mask_fio(text)
    return text


def pii_processor(logger, method_name, event_dict):
    """Structlog processor that masks PII in log events."""
    # Mask the main event message
    if 'event' in event_dict and isinstance(event_dict['event'], str):
        event_dict['event'] = mask_all(event_dict['event'])

    # Mask all string values in event_dict
    for key, value in event_dict.items():
        if key == 'event':
            continue
        if isinstance(value, str):
            event_dict[key] = mask_all(value)

    return event_dict
