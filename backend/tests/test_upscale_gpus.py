"""Tests for Vulkan device enumeration and the ``/api/upscale/gpus`` endpoint.

The device list is discovered by probing the CLI's startup banner, so the parser
is exercised against captured real output. A wrong parse here would offer the
operator a GPU index that does not exist, which fails minutes into a batch.
"""

import pytest

from services.upscale import gpus
from services.upscale.gpus import (
    KIND_DEDICATED,
    KIND_INTEGRATED,
    KIND_SOFTWARE,
    KIND_UNKNOWN,
    GpuDevice,
    classify,
)

#: Captured verbatim from ``upscayl-bin -v`` on the development machine: one
#: discrete card and three identical integrated adapters.
REAL_BANNER = """\
[0 NVIDIA GeForce GTX 1660 Ti]  queueC=2[8]  queueG=0[16]  queueT=1[2]
[0 NVIDIA GeForce GTX 1660 Ti]  bugsbn1=0  bugbilz=0  bugcopc=0  bugihfa=0
[0 NVIDIA GeForce GTX 1660 Ti]  fp16-p/s/a=1/1/1  int8-p/s/a=1/1/1
[0 NVIDIA GeForce GTX 1660 Ti]  subgroup=32  basic=1  vote=1  ballot=1  shuffle=1
[1 Intel(R) UHD Graphics]  queueC=0[1]  queueG=0[1]  queueT=0[1]
[1 Intel(R) UHD Graphics]  bugsbn1=0  bugbilz=0  bugcopc=0  bugihfa=0
[1 Intel(R) UHD Graphics]  fp16-p/s/a=1/1/1  int8-p/s/a=1/1/1
[2 Intel(R) UHD Graphics]  queueC=0[1]  queueG=0[1]  queueT=0[1]
[3 Intel(R) UHD Graphics]  queueC=0[1]  queueG=0[1]  queueT=0[1]
Error: Invalid GPU Device
"""


@pytest.fixture(autouse=True)
def _clear_gpu_cache():
    gpus.clear_cache()
    yield
    gpus.clear_cache()


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


def test_parser_finds_every_device_once():
    devices = gpus._parse_devices(REAL_BANNER)

    assert [device.id for device in devices] == [0, 1, 2, 3]
    assert devices[0].name == "NVIDIA GeForce GTX 1660 Ti"
    assert devices[1].name == "Intel(R) UHD Graphics"


def test_parser_keeps_repeated_adapters_as_separate_devices():
    # The three integrated adapters share a name; collapsing them would make a
    # multi-GPU setup impossible to configure.
    devices = gpus._parse_devices(REAL_BANNER)

    integrated = [device for device in devices if device.kind == KIND_INTEGRATED]
    assert len(integrated) == 3
    assert [device.id for device in integrated] == [1, 2, 3]


def test_parser_reports_the_lowest_index_as_the_default():
    devices = gpus._parse_devices(REAL_BANNER)

    recommended = [device for device in devices if device.recommended]
    assert len(recommended) == 1
    assert recommended[0].id == 0
    assert recommended[0].kind == KIND_DEDICATED


def test_parser_prefers_a_discrete_card_over_a_lower_index():
    # Device 0 integrated, device 1 discrete: the discrete card must win even
    # though it is not first.
    banner = "[0 Intel(R) UHD Graphics]  queueC=0[1]\n[1 NVIDIA GeForce RTX 4070]  queueC=2[8]\n"

    devices = gpus._parse_devices(banner)

    assert [device.recommended for device in devices] == [False, True]


def test_parser_prefers_any_real_device_over_a_software_rasterizer():
    banner = (
        "[0 llvmpipe (LLVM 15.0.7, 256 bits)]  queueC=0[1]\n"
        "[1 Intel(R) UHD Graphics]  queueC=0[1]\n"
    )

    devices = gpus._parse_devices(banner)

    assert devices[0].kind == KIND_SOFTWARE
    assert devices[1].recommended is True


def test_parser_returns_nothing_for_output_without_devices():
    assert gpus._parse_devices("Error: Invalid GPU Device\n") == []


def test_parser_ignores_bracketed_text_that_is_not_a_device():
    # A model or path printed in brackets must not be read as a device index.
    assert gpus._parse_devices("Loading model [some-model]\n") == []


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "name, expected",
    [
        ("NVIDIA GeForce GTX 1660 Ti", KIND_DEDICATED),
        ("NVIDIA GeForce RTX 4090", KIND_DEDICATED),
        ("AMD Radeon RX 7900 XTX", KIND_DEDICATED),
        ("Intel(R) Arc(TM) A770 Graphics", KIND_DEDICATED),
        ("Intel(R) UHD Graphics", KIND_INTEGRATED),
        ("Intel(R) Iris(R) Xe Graphics", KIND_INTEGRATED),
        ("AMD Radeon Graphics", KIND_INTEGRATED),
        ("Apple M2 Pro", KIND_INTEGRATED),
        ("llvmpipe (LLVM 15.0.7, 256 bits)", KIND_SOFTWARE),
        ("Microsoft Basic Render Driver", KIND_SOFTWARE),
        ("Some Unlabelled Adapter", KIND_UNKNOWN),
    ],
)
def test_classify_identifies_device_kinds(name, expected):
    assert classify(name) == expected


def test_radeon_rx_is_discrete_while_plain_radeon_is_integrated():
    # The two names differ only by a suffix, and "radeon" appears in both, so
    # ordering of the hint lists is what makes this correct.
    assert classify("AMD Radeon RX 6700 XT") == KIND_DEDICATED
    assert classify("AMD Radeon Graphics") == KIND_INTEGRATED


# --------------------------------------------------------------------------- #
# Device serialisation
# --------------------------------------------------------------------------- #


def test_device_payload_carries_what_the_picker_renders():
    device = GpuDevice(id=2, name="Intel(R) UHD Graphics", kind=KIND_INTEGRATED)
    payload = device.to_dict()

    assert payload["id"] == 2
    assert payload["name"] == "Intel(R) UHD Graphics"
    assert payload["kind"] == KIND_INTEGRATED
    assert payload["kind_label"] == "Integrated"
    assert payload["recommended"] is False


# --------------------------------------------------------------------------- #
# Probing and caching
# --------------------------------------------------------------------------- #


def test_list_gpus_returns_nothing_without_a_cli(monkeypatch):
    monkeypatch.setattr(gpus, "find_cli", lambda cfg=None: None)

    assert gpus.list_gpus() == []


def test_list_gpus_parses_the_real_binary(monkeypatch):
    monkeypatch.setattr(gpus, "find_cli", lambda cfg=None: "upscayl-bin")
    monkeypatch.setattr(gpus, "_probe", lambda cli, cfg=None: REAL_BANNER)

    devices = gpus.list_gpus(refresh=True)

    assert len(devices) == 4
    assert devices[0].name == "NVIDIA GeForce GTX 1660 Ti"


def test_list_gpus_caches_so_a_batch_does_not_respawn_the_cli(monkeypatch):
    calls = {"count": 0}

    def counting_probe(cli, cfg=None):
        calls["count"] += 1
        return REAL_BANNER

    monkeypatch.setattr(gpus, "find_cli", lambda cfg=None: "upscayl-bin")
    monkeypatch.setattr(gpus, "_probe", counting_probe)

    gpus.list_gpus(refresh=True)
    gpus.list_gpus()
    gpus.list_gpus()

    assert calls["count"] == 1


def test_refresh_bypasses_the_cache(monkeypatch):
    calls = {"count": 0}

    def counting_probe(cli, cfg=None):
        calls["count"] += 1
        return REAL_BANNER

    monkeypatch.setattr(gpus, "find_cli", lambda cfg=None: "upscayl-bin")
    monkeypatch.setattr(gpus, "_probe", counting_probe)

    gpus.list_gpus(refresh=True)
    gpus.list_gpus(refresh=True)

    assert calls["count"] == 2


def test_clear_cache_forces_a_reprobe(monkeypatch):
    calls = {"count": 0}

    def counting_probe(cli, cfg=None):
        calls["count"] += 1
        return REAL_BANNER

    monkeypatch.setattr(gpus, "find_cli", lambda cfg=None: "upscayl-bin")
    monkeypatch.setattr(gpus, "_probe", counting_probe)

    gpus.list_gpus(refresh=True)
    gpus.clear_cache()
    gpus.list_gpus()

    assert calls["count"] == 2


def test_probe_survives_a_cli_that_cannot_be_launched(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("not executable")

    monkeypatch.setattr(gpus.subprocess, "run", boom)

    assert gpus._probe("upscayl-bin") == ""


def test_probe_survives_a_hung_cli(monkeypatch):
    def hang(*args, **kwargs):
        raise gpus.subprocess.TimeoutExpired(cmd="upscayl-bin", timeout=1)

    monkeypatch.setattr(gpus.subprocess, "run", hang)

    assert gpus._probe("upscayl-bin") == ""


def test_probe_reads_stderr_because_the_banner_goes_there(monkeypatch):
    # The CLI writes the banner to stderr; a stdout-only probe would return
    # nothing and the picker would silently fall back to a hard-coded list.
    class _Completed:
        stdout = ""
        stderr = "[0 NVIDIA GeForce GTX 1660 Ti]  queueC=2[8]\n"
        returncode = 1

    monkeypatch.setattr(gpus.subprocess, "run", lambda *a, **k: _Completed())

    assert "GeForce GTX 1660 Ti" in gpus._probe("upscayl-bin")


def test_probe_merges_stdout_and_stderr(monkeypatch):
    class _Completed:
        stdout = "[0 NVIDIA GeForce GTX 1660 Ti]  queueC=2[8]\n"
        stderr = "[1 Intel(R) UHD Graphics]  queueC=0[1]\n"
        returncode = 1

    monkeypatch.setattr(gpus.subprocess, "run", lambda *a, **k: _Completed())

    devices = gpus._parse_devices(gpus._probe("upscayl-bin"))

    assert [device.id for device in devices] == [0, 1]


def test_probe_passes_a_real_model_directory(monkeypatch):
    # The CLI validates ``-m`` before it enumerates devices, so probing without
    # a real model folder returns an error and no banner at all.
    captured = {}

    class _Completed:
        stdout = ""
        stderr = ""
        returncode = 1

    def fake_run(command, **kwargs):
        captured["command"] = command
        return _Completed()

    monkeypatch.setattr(gpus.subprocess, "run", fake_run)
    monkeypatch.setattr(gpus, "_probe_model_dir", lambda cfg: "C:/models")

    gpus._probe("upscayl-bin")

    assert "-m" in captured["command"]
    assert captured["command"][captured["command"].index("-m") + 1] == "C:/models"


def test_probe_never_passes_an_empty_input_path(monkeypatch):
    # An empty ``-i`` makes the CLI print usage and exit before Vulkan starts.
    captured = {}

    class _Completed:
        stdout = ""
        stderr = ""
        returncode = 1

    monkeypatch.setattr(gpus.subprocess, "run", lambda command, **k: (captured.update(command=command), _Completed())[1])

    gpus._probe("upscayl-bin")

    command = captured["command"]
    assert command[command.index("-i") + 1] != ""
    assert command[command.index("-o") + 1] != ""


# --------------------------------------------------------------------------- #
# Defaults
# --------------------------------------------------------------------------- #


def test_default_gpu_id_picks_the_recommended_device(monkeypatch):
    monkeypatch.setattr(gpus, "list_gpus", lambda settings=None, refresh=False: [
        GpuDevice(id=0, name="Intel(R) UHD Graphics", kind=KIND_INTEGRATED),
        GpuDevice(id=1, name="NVIDIA GeForce RTX 4070", kind=KIND_DEDICATED, recommended=True),
    ])

    assert gpus.default_gpu_id() == 1


def test_default_gpu_id_falls_back_to_zero_without_devices(monkeypatch):
    monkeypatch.setattr(gpus, "list_gpus", lambda settings=None, refresh=False: [])

    assert gpus.default_gpu_id() == 0


# --------------------------------------------------------------------------- #
# Payload and endpoint
# --------------------------------------------------------------------------- #


def test_payload_reports_availability_and_default(monkeypatch):
    monkeypatch.setattr(gpus, "find_cli", lambda cfg=None: "upscayl-bin")
    monkeypatch.setattr(gpus, "_probe", lambda cli, cfg=None: REAL_BANNER)

    payload = gpus.gpus_payload(refresh=True)

    assert payload["available"] is True
    assert payload["default_gpu_id"] == 0
    assert len(payload["devices"]) == 4
    assert payload["devices"][0]["kind_label"] == "Dedicated"


def test_payload_is_marked_unavailable_when_enumeration_fails(monkeypatch):
    monkeypatch.setattr(gpus, "find_cli", lambda cfg=None: None)

    payload = gpus.gpus_payload(refresh=True)

    assert payload["available"] is False
    assert payload["devices"] == []
    assert payload["default_gpu_id"] == 0


def test_gpus_endpoint_returns_the_devices(client):
    response = client.get("/api/upscale/gpus")

    assert response.status_code == 200
    body = response.json()
    # The CLI ships with this checkout, so real hardware must be visible.
    assert body["available"] is True
    assert body["devices"], "the real Vulkan devices must be enumerated"
    assert body["default_gpu_id"] in {device["id"] for device in body["devices"]}


def test_gpus_endpoint_reports_the_discrete_card_first(client):
    body = client.get("/api/upscale/gpus").json()

    recommended = [device for device in body["devices"] if device["recommended"]]
    assert len(recommended) == 1
    assert recommended[0]["kind"] == KIND_DEDICATED


def test_gpus_endpoint_accepts_a_refresh(client):
    assert client.get("/api/upscale/gpus?refresh=true").status_code == 200


def test_gpus_endpoint_serialises_every_field_the_panel_needs(client):
    device = client.get("/api/upscale/gpus").json()["devices"][0]

    assert set(device) >= {"id", "name", "kind", "kind_label", "recommended"}
