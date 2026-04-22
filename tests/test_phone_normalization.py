"""Tests para _normalize_phone en conversation_hub.

Objetivo: asegurar que el normalizador maneja todos los formatos que WhatsApp
(Evolution API) y el usuario humano pueden enviar.
"""
import pytest

from app.services.conversation_hub import _normalize_phone


class TestNormalizePhoneBasic:
    def test_none_returns_none(self):
        assert _normalize_phone(None) is None

    def test_empty_string_returns_none(self):
        assert _normalize_phone("") is None

    def test_plain_digits_with_country_code(self):
        assert _normalize_phone("59171234567") == "59171234567"

    def test_already_normalized_stays_equal(self):
        assert _normalize_phone("59171234567") == "59171234567"


class TestNormalizePhoneFormats:
    def test_plus_prefix_stripped(self):
        assert _normalize_phone("+59171234567") == "59171234567"

    def test_spaces_stripped(self):
        assert _normalize_phone("591 712 34567") == "59171234567"

    def test_dashes_stripped(self):
        assert _normalize_phone("591-71234567") == "59171234567"

    def test_mixed_plus_spaces_dashes(self):
        assert _normalize_phone("+591 7123-4567") == "59171234567"

    def test_leading_trailing_whitespace(self):
        assert _normalize_phone("   59171234567   ") == "59171234567"


class TestNormalizePhoneWhatsAppJid:
    """WhatsApp Evolution API envía JIDs como '59171234567@s.whatsapp.net'."""

    def test_jid_suffix_stripped(self):
        assert _normalize_phone("59171234567@s.whatsapp.net") == "59171234567"

    def test_group_jid_suffix_stripped(self):
        # Groups come as xxx@g.us
        assert _normalize_phone("59171234567@g.us") == "59171234567"

    def test_jid_with_plus_and_at(self):
        assert _normalize_phone("+59171234567@s.whatsapp.net") == "59171234567"


class TestNormalizePhoneBoliviaDefault:
    """Si el número tiene 8 dígitos y no empieza con 591, el sistema asume Bolivia."""

    def test_8_digit_cell_gets_591_prefix(self):
        assert _normalize_phone("71234567") == "59171234567"

    def test_8_digit_with_spaces(self):
        assert _normalize_phone("7123 4567") == "59171234567"

    def test_9_digit_no_prefix_not_added(self):
        # Más de 8 dígitos sin 591 → se deja tal cual (puede ser otro país)
        assert _normalize_phone("712345678") == "712345678"


class TestNormalizePhoneEdgeCases:
    def test_only_spaces_returns_none(self):
        result = _normalize_phone("   ")
        assert result is None or result == ""

    def test_number_starting_591_different_length(self):
        # +591 + 9 dígitos (Bolivia solo usa 8, pero si llega así, preservar)
        assert _normalize_phone("591712345678") == "591712345678"
