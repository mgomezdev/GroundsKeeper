"""Unit tests for printer client connection_fields() classmethods."""

from backend.app.services.bambu_mqtt import BambuMQTTClient


class TestBambuConnectionFields:
    def test_returns_two_fields(self):
        fields = BambuMQTTClient.connection_fields()
        assert len(fields) == 2

    def test_first_field_is_serial_number(self):
        field = BambuMQTTClient.connection_fields()[0]
        assert field.name == "serial_number"
        assert field.label == "Serial Number"
        assert field.field_type == "text"
        assert field.required is True
        assert field.placeholder == "01P00A000000000"
        assert field.help_text == ""

    def test_second_field_is_access_code(self):
        field = BambuMQTTClient.connection_fields()[1]
        assert field.name == "access_code"
        assert field.label == "Access Code"
        assert field.field_type == "password"
        assert field.required is True
        assert field.placeholder == "From printer LAN settings"
        assert field.help_text == "8-character code shown in the printer's network settings"
