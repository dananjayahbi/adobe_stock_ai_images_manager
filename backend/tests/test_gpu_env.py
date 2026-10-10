"""Tests for GPU provider selection and the rembg session cache.

Everything here is hardware-independent: the assertions that depend on a CUDA
box are written as *invariants* (a fallback list is always safe, CUDA is
optional) so the suite stays green on a machine without a GPU, while the
plumbing that decides CPU-vs-GPU is pinned exactly.
"""

from __future__ import annotations

from collections import OrderedDict

import numpy as np
import pytest

from services import bg_remover, gpu_env


# --------------------------------------------------------------------------- #
# Provider selection
# --------------------------------------------------------------------------- #

class TestProviderSelection:
    def test_gpu_disabled_is_always_the_cpu(self):
        assert gpu_env.execution_providers(gpu=False) == ["CPUExecutionProvider"]

    def test_the_gpu_list_always_falls_back_to_cpu(self):
        providers = gpu_env.execution_providers(gpu=True)
        # Whatever the host reports, onnxruntime must be allowed to spill onto
        # the CPU rather than failing the session outright.
        names = [p[0] if isinstance(p, tuple) else p for p in providers]
        assert names[-1] == "CPUExecutionProvider"
        assert set(names) <= {"CUDAExecutionProvider", "CPUExecutionProvider"}

    def test_cuda_spec_carries_the_fallback_conv_algo(self):
        specs = gpu_env.cuda_providers()
        name, options = specs[0]
        assert name == "CUDAExecutionProvider"
        # Heuristic mode FALLBACK: the mode that still works when the cuDNN
        # heuristics database has no engine configs for this architecture.
        assert options == {"cudnn_conv_algo_search": "DEFAULT"}

    def test_conv_algo_can_be_overridden_from_the_environment(self, monkeypatch):
        monkeypatch.setenv(gpu_env.CONV_ALGO_ENV, "exhaustive")
        assert gpu_env.conv_algo() == "EXHAUSTIVE"
        assert gpu_env.cuda_providers()[0][1]["cudnn_conv_algo_search"] == "EXHAUSTIVE"
        # Garbage falls back to the safe value instead of erroring.
        monkeypatch.setenv(gpu_env.CONV_ALGO_ENV, "nonsense")
        assert gpu_env.conv_algo() == "DEFAULT"
        monkeypatch.delenv(gpu_env.CONV_ALGO_ENV)
        assert gpu_env.conv_algo() == "DEFAULT"

    def test_provider_cache_key_hashable_with_option_dicts(self):
        specs = gpu_env.cuda_providers()
        key = gpu_env.provider_cache_key(specs)
        assert hash(key)  # must be usable as a dict key
        assert "CUDAExecutionProvider" in key[0]
        assert key[-1] == "CPUExecutionProvider"
        # Same options, different order -> same key.
        other = gpu_env.provider_cache_key(list(reversed(specs)))
        assert set(key) == set(other)

    def test_cpu_and_cuda_specs_do_not_collide(self):
        cpu = gpu_env.provider_cache_key(["CPUExecutionProvider"])
        gpu = gpu_env.provider_cache_key(gpu_env.cuda_providers())
        assert cpu != gpu

    def test_cuda_usable_is_a_plain_bool(self):
        # True on a CUDA box, False elsewhere — never raises either way.
        assert isinstance(gpu_env.cuda_usable(), bool)

    def test_ensure_cuda_dlls_is_idempotent_and_prepends(self, monkeypatch):
        # Reset the module-level memo so this test exercises the real work
        # regardless of what ran before it in the session.
        monkeypatch.setattr(gpu_env, "_applied", False)
        monkeypatch.setattr(gpu_env, "_dirs", [])
        monkeypatch.setenv("PATH", "C:\\original")
        first = gpu_env.ensure_cuda_dlls()
        second = gpu_env.ensure_cuda_dlls()
        assert first == second

        import os

        entries = os.environ["PATH"].split(os.pathsep)
        # Everything we found leads, and the original PATH survives behind it.
        for d in first:
            assert d in entries[: len(first)]
        assert entries[-1] == "C:\\original"

    def test_discovered_dll_dirs_exist_and_hold_dlls(self):
        from pathlib import Path

        for d in gpu_env.nvidia_dll_dirs():
            assert Path(d).is_dir()
            assert list(Path(d).glob("*.dll")), f"{d} has no DLLs"


# --------------------------------------------------------------------------- #
# Session cache
# --------------------------------------------------------------------------- #

class _FakeSession:
    """Stands in for a rembg session so no ONNX weights are touched."""

    def __init__(self, model: str, providers: list[str]):
        self.model = model
        self.providers = providers

    def get_providers(self) -> list[str]:
        return list(self.providers)


@pytest.fixture()
def fake_sessions(monkeypatch):
    """Replace rembg's session factory and start from an empty cache."""
    import rembg

    created: list[tuple[str, list[str]]] = []

    def factory(model: str, **kwargs):
        providers = list(kwargs.get("providers") or [])
        created.append((model, providers))
        return _FakeSession(model, providers)

    cache: OrderedDict = OrderedDict()
    monkeypatch.setattr(rembg, "new_session", factory)
    monkeypatch.setattr(bg_remover, "_sessions", cache)
    return cache, created


class TestSessionCache:
    def test_only_one_model_is_ever_resident_by_default(self, fake_sessions):
        # The box runs other projects: a BiRefNet-class model is ~1 GB, so the
        # shipped default must never hold two.
        assert bg_remover.MAX_SESSIONS == 1
        cache, _ = fake_sessions
        for model in ("m1", "m2", "m3", "m4"):
            bg_remover._get_session(model, ["CPUExecutionProvider"])
        assert len(cache) == 1
        assert [k[0] for k in cache] == ["m4"]

    def test_cache_is_bounded_so_models_cannot_pile_up(self, fake_sessions, monkeypatch):
        monkeypatch.setattr(bg_remover, "MAX_SESSIONS", 2)
        cache, created = fake_sessions
        for model in ("m1", "m2", "m3", "m4"):
            bg_remover._get_session(model, ["CPUExecutionProvider"])
        assert len(cache) <= 2
        assert len(created) == 4  # each model really was built once

    def test_least_recently_used_entry_is_evicted(self, fake_sessions, monkeypatch):
        monkeypatch.setattr(bg_remover, "MAX_SESSIONS", 2)
        cache, _ = fake_sessions
        bg_remover._get_session("old", ["CPUExecutionProvider"])
        bg_remover._get_session("new", ["CPUExecutionProvider"])
        # Touching "old" makes "new" the eviction candidate.
        bg_remover._get_session("old", ["CPUExecutionProvider"])
        bg_remover._get_session("extra", ["CPUExecutionProvider"])
        keys = [k[0] for k in cache]
        assert "old" in keys
        assert "extra" in keys
        assert "new" not in keys

    def test_a_hit_does_not_rebuild_the_session(self, fake_sessions):
        _, created = fake_sessions
        bg_remover._get_session("same", ["CPUExecutionProvider"])
        bg_remover._get_session("same", ["CPUExecutionProvider"])
        assert created == [("same", ["CPUExecutionProvider"])]

    def test_providers_are_part_of_the_cache_key(self, fake_sessions, monkeypatch):
        # Two slots so both entries survive long enough to be compared.
        monkeypatch.setattr(bg_remover, "MAX_SESSIONS", 2)
        cache, created = fake_sessions
        cpu = bg_remover._get_session("m", ["CPUExecutionProvider"])
        gpu = bg_remover._get_session(
            "m", ["CUDAExecutionProvider", "CPUExecutionProvider"]
        )
        assert cpu is not gpu
        assert {k[1] for k in cache} == {
            ("CPUExecutionProvider",),
            ("CUDAExecutionProvider", "CPUExecutionProvider"),
        }
        assert created[0][1] == ["CPUExecutionProvider"]
        assert created[1][1] == ["CUDAExecutionProvider", "CPUExecutionProvider"]

    def test_requests_are_forwarded_to_rembg(self, fake_sessions):
        _, created = fake_sessions
        bg_remover._get_session("m", ["CUDAExecutionProvider", "CPUExecutionProvider"])
        assert created[-1][1] == ["CUDAExecutionProvider", "CPUExecutionProvider"]

    def test_release_sessions_frees_everything(self, fake_sessions):
        cache, _ = fake_sessions
        bg_remover._get_session("m", ["CPUExecutionProvider"])
        assert len(cache) == 1

        assert bg_remover.release_sessions() == 1
        assert len(cache) == 0
        # Idempotent: a second call is a no-op, not an error.
        assert bg_remover.release_sessions() == 0


# --------------------------------------------------------------------------- #
# remove_background plumbing
# --------------------------------------------------------------------------- #

class TestDeviceReporting:
    @staticmethod
    def _rgba() -> np.ndarray:
        rgba = np.zeros((32, 32, 4), np.uint8)
        rgba[8:24, 8:24] = (40, 90, 160, 255)
        return rgba

    @staticmethod
    def _settings(tmp_path):
        """Just enough Settings for remove_background (it reads one field)."""
        from types import SimpleNamespace

        return SimpleNamespace(REMOVED_DIR=str(tmp_path / "removed"))

    @staticmethod
    def _source(tmp_path):
        from PIL import Image

        path = tmp_path / "in.png"
        Image.fromarray(TestDeviceReporting._rgba(), "RGBA").save(path)
        return path

    def test_device_is_recorded_on_the_cut_out(self, monkeypatch, tmp_path):
        rgba = self._rgba()

        def fake_segment(source, model, providers):
            return rgba, _FakeSession(model, providers)

        monkeypatch.setattr(bg_remover, "_segment", fake_segment)

        result = bg_remover.remove_background(
            self._source(tmp_path),
            "rec1",
            cfg=self._settings(tmp_path),
            options={"gpu": False, "matting": "off"},
        )
        assert result.success, result.reason
        device = result.stages["device"]
        assert device["requested"] == "cpu"
        assert device["providers"] == ["CPUExecutionProvider"]
        assert isinstance(device["cuda_usable"], bool)

    def test_gpu_false_never_reaches_the_cuda_provider(self, monkeypatch, tmp_path):
        seen: dict = {}

        def fake_segment(source, model, providers):
            seen["providers"] = providers
            return self._rgba(), _FakeSession(model, providers)

        monkeypatch.setattr(bg_remover, "_segment", fake_segment)

        bg_remover.remove_background(
            self._source(tmp_path),
            "rec2",
            cfg=self._settings(tmp_path),
            options={"gpu": False},
        )
        assert seen["providers"] == ["CPUExecutionProvider"]
