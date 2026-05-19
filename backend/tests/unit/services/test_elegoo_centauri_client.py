"""Unit tests for ElegooCentauriClient.

Mock seam: ``client._ws`` — a MagicMock whose ``.send()`` side_effect
immediately resolves the pending ACK so ``_send(wait_ack=True)`` returns
without hitting the 10-second network timeout.

How the ACK responder works:
  1. ``_send`` registers ``_pending_acks[request_id] = event`` BEFORE calling ``ws.send()``.
  2. The side_effect reads the RequestID from the serialized JSON, sets
     ``_ack_results[request_id]`` to the desired ACK code, then fires the event.
  3. ``_send`` sees the event, reads the result, and returns.
"""

import json

import pytest

from backend.app.services.elegoo_centauri_client import ElegooCentauriClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ack_responder(client: ElegooCentauriClient, ack: int = 0):
    """Return a ws.send side_effect that immediately fulfils the pending ACK."""
    def _respond(raw: str) -> None:
        data = json.loads(raw)
        rid = data["Data"]["RequestID"]
        client._ack_results[rid] = ack
        event = client._pending_acks.get(rid)
        if event:
            event.set()
    return _respond


def _make_response_responder(client: ElegooCentauriClient, ack: int = 0, response_data: dict | None = None):
    """Return a ws.send side_effect that fulfils ACK and stores response data."""
    def _respond(raw: str) -> None:
        data = json.loads(raw)
        rid = data["Data"]["RequestID"]
        client._ack_results[rid] = ack
        if response_data is not None:
            client._response_data[rid] = response_data
        event = client._pending_acks.get(rid)
        if event:
            event.set()
    return _respond


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """ElegooCentauriClient with a mocked WebSocket (no actual connection)."""
    from unittest.mock import MagicMock

    c = ElegooCentauriClient(ip_address="192.168.1.200")
    c._ws = MagicMock()
    return c


@pytest.fixture
def connected_client(client):
    """Client with state.connected = True."""
    client.state.connected = True
    return client


# ---------------------------------------------------------------------------
# Print control
# ---------------------------------------------------------------------------


class TestPrintControl:

    def test_stop_print_no_ws_returns_false(self):
        c = ElegooCentauriClient(ip_address="192.168.1.200")
        assert c.stop_print() is False

    def test_stop_print_sends_cmd_130(self, connected_client):
        connected_client._ws.send.side_effect = _make_ack_responder(connected_client)

        result = connected_client.stop_print()

        assert result is True
        msg = json.loads(connected_client._ws.send.call_args[0][0])
        assert msg["Data"]["Cmd"] == 130

    def test_stop_print_returns_false_on_nzero_ack(self, connected_client):
        connected_client._ws.send.side_effect = _make_ack_responder(connected_client, ack=1)

        assert connected_client.stop_print() is False

    def test_pause_print_sends_cmd_129(self, connected_client):
        connected_client._ws.send.side_effect = _make_ack_responder(connected_client)

        result = connected_client.pause_print()

        assert result is True
        msg = json.loads(connected_client._ws.send.call_args[0][0])
        assert msg["Data"]["Cmd"] == 129

    def test_pause_print_no_ws_returns_false(self):
        c = ElegooCentauriClient(ip_address="192.168.1.200")
        assert c.pause_print() is False

    def test_resume_print_sends_cmd_131(self, connected_client):
        connected_client._ws.send.side_effect = _make_ack_responder(connected_client)

        result = connected_client.resume_print()

        assert result is True
        msg = json.loads(connected_client._ws.send.call_args[0][0])
        assert msg["Data"]["Cmd"] == 131

    def test_resume_print_no_ws_returns_false(self):
        c = ElegooCentauriClient(ip_address="192.168.1.200")
        assert c.resume_print() is False

    def test_start_print_sends_cmd_128_with_filename(self, connected_client):
        connected_client._ws.send.side_effect = _make_ack_responder(connected_client)

        result = connected_client.start_print("/local/cube.gcode")

        assert result is True
        msg = json.loads(connected_client._ws.send.call_args[0][0])
        assert msg["Data"]["Cmd"] == 128
        assert msg["Data"]["Data"]["Filename"] == "/local/cube.gcode"

    def test_start_print_no_ws_returns_false(self):
        c = ElegooCentauriClient(ip_address="192.168.1.200")
        assert c.start_print("/local/cube.gcode") is False


# ---------------------------------------------------------------------------
# Axis control
# ---------------------------------------------------------------------------


class TestAxisControl:

    def test_home_sends_cmd_402_xyz(self, connected_client):
        connected_client._ws.send.side_effect = _make_ack_responder(connected_client)

        result = connected_client.home()

        assert result is True
        msg = json.loads(connected_client._ws.send.call_args[0][0])
        assert msg["Data"]["Cmd"] == 402
        assert msg["Data"]["Data"]["Axis"] == "XYZ"

    def test_home_no_ws_returns_false(self):
        c = ElegooCentauriClient(ip_address="192.168.1.200")
        assert c.home() is False

    def test_jog_z_sends_cmd_401_with_step(self, connected_client):
        connected_client._ws.send.side_effect = _make_ack_responder(connected_client)

        result = connected_client.jog_z(2.5)

        assert result is True
        msg = json.loads(connected_client._ws.send.call_args[0][0])
        assert msg["Data"]["Cmd"] == 401
        assert msg["Data"]["Data"]["Axis"] == "Z"
        assert msg["Data"]["Data"]["Step"] == 2.5

    def test_jog_z_negative_distance(self, connected_client):
        connected_client._ws.send.side_effect = _make_ack_responder(connected_client)

        connected_client.jog_z(-1.0)

        msg = json.loads(connected_client._ws.send.call_args[0][0])
        assert msg["Data"]["Data"]["Step"] == -1.0

    def test_jog_z_no_ws_returns_false(self):
        c = ElegooCentauriClient(ip_address="192.168.1.200")
        assert c.jog_z(1.0) is False


# ---------------------------------------------------------------------------
# Chamber light
# ---------------------------------------------------------------------------


class TestChamberLight:

    def test_light_on_sends_cmd_403_second_light_true(self, connected_client):
        connected_client._ws.send.side_effect = _make_ack_responder(connected_client)

        result = connected_client.set_chamber_light(True)

        assert result is True
        msg = json.loads(connected_client._ws.send.call_args[0][0])
        assert msg["Data"]["Cmd"] == 403
        assert msg["Data"]["Data"]["LightStatus"]["SecondLight"] is True

    def test_light_off_sends_second_light_false(self, connected_client):
        connected_client._ws.send.side_effect = _make_ack_responder(connected_client)

        connected_client.set_chamber_light(False)

        msg = json.loads(connected_client._ws.send.call_args[0][0])
        assert msg["Data"]["Data"]["LightStatus"]["SecondLight"] is False

    def test_light_preserves_existing_rgb(self, connected_client):
        connected_client.state.rgb_light = [255, 128, 0]
        connected_client._ws.send.side_effect = _make_ack_responder(connected_client)

        connected_client.set_chamber_light(True)

        msg = json.loads(connected_client._ws.send.call_args[0][0])
        assert msg["Data"]["Data"]["LightStatus"]["RgbLight"] == [255, 128, 0]

    def test_light_default_rgb_is_zeros(self, connected_client):
        connected_client._ws.send.side_effect = _make_ack_responder(connected_client)

        connected_client.set_chamber_light(True)

        msg = json.loads(connected_client._ws.send.call_args[0][0])
        assert msg["Data"]["Data"]["LightStatus"]["RgbLight"] == [0, 0, 0]

    def test_state_updated_on_ack_success(self, connected_client):
        connected_client.state.chamber_light = False
        connected_client._ws.send.side_effect = _make_ack_responder(connected_client)

        connected_client.set_chamber_light(True)

        assert connected_client.state.chamber_light is True

    def test_state_unchanged_on_ack_error(self, connected_client):
        connected_client.state.chamber_light = False
        connected_client._ws.send.side_effect = _make_ack_responder(connected_client, ack=1)

        connected_client.set_chamber_light(True)

        assert connected_client.state.chamber_light is False

    def test_no_ws_returns_false(self):
        c = ElegooCentauriClient(ip_address="192.168.1.200")
        assert c.set_chamber_light(True) is False


# ---------------------------------------------------------------------------
# GCode (unsupported)
# ---------------------------------------------------------------------------


class TestGCode:

    def test_send_gcode_always_returns_false(self, connected_client):
        assert connected_client.send_gcode("G28") is False

    def test_send_gcode_never_calls_ws_send(self, connected_client):
        connected_client.send_gcode("G28")
        connected_client._ws.send.assert_not_called()


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


class TestCapabilities:

    @pytest.fixture
    def caps(self):
        return ElegooCentauriClient(ip_address="192.168.1.200").get_capabilities()

    def test_chamber_light_true(self, caps):
        assert caps.chamber_light is True

    def test_file_upload_true(self, caps):
        assert caps.file_upload is True

    def test_bed_levelling_true(self, caps):
        assert caps.bed_levelling is True

    def test_pause_resume_true(self, caps):
        assert caps.pause_resume is True

    def test_ams_false(self, caps):
        assert caps.ams is False

    def test_gcode_false(self, caps):
        assert caps.gcode is False

    def test_timelapse_false(self, caps):
        assert caps.timelapse is False

    def test_flow_calibration_false(self, caps):
        assert caps.flow_calibration is False

    def test_vibration_cali_false(self, caps):
        assert caps.vibration_cali is False

    def test_layer_inspect_false(self, caps):
        assert caps.layer_inspect is False

    def test_skip_objects_false(self, caps):
        assert caps.skip_objects is False

    def test_multi_nozzle_false(self, caps):
        assert caps.multi_nozzle is False


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------


class TestFileOperations:

    def test_list_files_no_ws_returns_empty(self):
        c = ElegooCentauriClient(ip_address="192.168.1.200")
        assert c.list_files() == []

    def test_list_files_parses_file_list(self, connected_client):
        resp = {
            "FileList": [
                {"FileName": "cube.gcode", "FileSize": 12345},
                {"FileName": "vase.gcode", "FileSize": 6789},
            ]
        }
        connected_client._ws.send.side_effect = _make_response_responder(connected_client, ack=0, response_data=resp)

        files = connected_client.list_files("/local/")

        assert len(files) == 2
        assert files[0]["name"] == "cube.gcode"
        assert files[0]["path"] == "/local/cube.gcode"
        assert files[0]["size"] == 12345
        assert files[0]["is_directory"] is False

    def test_list_files_ack_error_returns_empty(self, connected_client):
        connected_client._ws.send.side_effect = _make_response_responder(connected_client, ack=1)

        assert connected_client.list_files() == []

    def test_delete_file_sends_cmd_259(self, connected_client):
        connected_client._ws.send.side_effect = _make_ack_responder(connected_client)

        result = connected_client.delete_file("/local/cube.gcode")

        assert result is True
        msg = json.loads(connected_client._ws.send.call_args[0][0])
        assert msg["Data"]["Cmd"] == 259
        assert "/local/cube.gcode" in msg["Data"]["Data"]["FileList"]
        assert msg["Data"]["Data"]["FolderList"] == []

    def test_delete_file_no_ws_returns_false(self):
        c = ElegooCentauriClient(ip_address="192.168.1.200")
        assert c.delete_file("/local/cube.gcode") is False


# ---------------------------------------------------------------------------
# Loaded filaments
# ---------------------------------------------------------------------------


class TestLoadedFilaments:

    def test_returns_one_external_spool(self):
        c = ElegooCentauriClient(ip_address="192.168.1.200")
        filaments = c.get_loaded_filaments()
        assert len(filaments) == 1
        assert filaments[0]["is_external"] is True

    def test_unknown_type(self):
        c = ElegooCentauriClient(ip_address="192.168.1.200")
        assert c.get_loaded_filaments()[0]["type"] == ""

    def test_default_gray_color(self):
        c = ElegooCentauriClient(ip_address="192.168.1.200")
        assert c.get_loaded_filaments()[0]["color"] == "#808080"


# ---------------------------------------------------------------------------
# Status update
# ---------------------------------------------------------------------------


class TestStatusUpdate:

    def test_request_status_update_sends_cmd_0(self, connected_client):
        result = connected_client.request_status_update()

        assert result is True
        msg = json.loads(connected_client._ws.send.call_args[0][0])
        assert msg["Data"]["Cmd"] == 0

    def test_request_status_update_no_ws_returns_false(self):
        c = ElegooCentauriClient(ip_address="192.168.1.200")
        assert c.request_status_update() is False


# ---------------------------------------------------------------------------
# Status parsing
# ---------------------------------------------------------------------------


class TestStatusParsing:

    def test_print_state_printing(self, client):
        msg = {
            "Topic": "sdcp/status/MB001",
            "Status": {
                "CurrentStatus": [1],
                "PrintInfo": {"Status": 13, "Progress": 42.0, "CurrentLayer": 5, "TotalLayer": 100,
                              "CurrentTicks": 600, "TotalTicks": 7200},
                "LightStatus": {},
                "CurrentFanSpeed": {},
            },
        }
        state = client._parse_status_msg(msg)
        assert state.print_state == "printing"
        assert state.progress == 42.0
        assert state.layer_num == 5

    def test_print_state_complete_from_current_status(self, client):
        """CurrentStatus=[8] → complete regardless of PrintInfo.Status."""
        msg = {
            "Topic": "sdcp/status/MB001",
            "Status": {
                "CurrentStatus": [8],
                "PrintInfo": {"Status": 0},
                "LightStatus": {},
                "CurrentFanSpeed": {},
            },
        }
        state = client._parse_status_msg(msg)
        assert state.print_state == "complete"

    def test_print_state_paused(self, client):
        msg = {
            "Topic": "sdcp/status/MB001",
            "Status": {
                "CurrentStatus": [1],
                "PrintInfo": {"Status": 6},
                "LightStatus": {},
                "CurrentFanSpeed": {},
            },
        }
        state = client._parse_status_msg(msg)
        assert state.print_state == "paused"

    def test_print_state_leveling(self, client):
        msg = {
            "Topic": "sdcp/status/MB001",
            "Status": {
                "CurrentStatus": [1],
                "PrintInfo": {"Status": 20},
                "LightStatus": {},
                "CurrentFanSpeed": {},
            },
        }
        state = client._parse_status_msg(msg)
        assert state.print_state == "leveling"

    def test_rgb_light_parsed(self, client):
        msg = {
            "Topic": "sdcp/status/MB001",
            "Status": {
                "CurrentStatus": [],
                "PrintInfo": {"Status": 0},
                "LightStatus": {"SecondLight": 1, "RgbLight": [100, 200, 50]},
                "CurrentFanSpeed": {},
            },
        }
        state = client._parse_status_msg(msg)
        assert state.chamber_light is True
        assert state.rgb_light == [100, 200, 50]

    def test_rgb_light_absent_does_not_reset(self, client):
        """If RgbLight is absent from the message, rgb_light keeps its default."""
        msg = {
            "Topic": "sdcp/status/MB001",
            "Status": {
                "CurrentStatus": [],
                "PrintInfo": {"Status": 0},
                "LightStatus": {"SecondLight": 0},
                "CurrentFanSpeed": {},
            },
        }
        state = client._parse_status_msg(msg)
        assert state.rgb_light == [0, 0, 0]

    def test_temperatures_parsed(self, client):
        msg = {
            "Topic": "sdcp/status/MB001",
            "Status": {
                "CurrentStatus": [],
                "PrintInfo": {"Status": 0},
                "LightStatus": {},
                "CurrentFanSpeed": {},
                "TempOfNozzle": 215.5,
                "TempTargetNozzle": 220.0,
                "TempOfHotbed": 60.0,
                "TempTargetHotbed": 65.0,
            },
        }
        state = client._parse_status_msg(msg)
        assert state.temperatures["nozzle"] == 215.5
        assert state.temperatures["nozzle_target"] == 220.0
        assert state.temperatures["bed"] == 60.0

    def test_connected_true_after_parse(self, client):
        """_parse_status_msg always sets connected=True on the returned state."""
        msg = {
            "Topic": "sdcp/status/MB001",
            "Status": {"CurrentStatus": [], "PrintInfo": {"Status": 0}, "LightStatus": {}, "CurrentFanSpeed": {}},
        }
        state = client._parse_status_msg(msg)
        assert state.connected is True
