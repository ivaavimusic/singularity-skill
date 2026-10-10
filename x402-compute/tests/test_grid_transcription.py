from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import io
import importlib.util
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "grid_transcription.py"
SPEC = importlib.util.spec_from_file_location("grid_transcription", SCRIPT)
assert SPEC and SPEC.loader
grid_transcription = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(grid_transcription)


class GridTranscriptionHelperTests(unittest.TestCase):
    def test_valid_pcm_metadata_uses_samples_for_duration_and_quote(self) -> None:
        raw = b"\x00\x00" * 80_001
        details = grid_transcription.metadata(raw, "auto")
        self.assertEqual(details["sample_count"], 80_001)
        self.assertAlmostEqual(details["duration_seconds"], 80_001 / 16_000)
        self.assertEqual(details["quote"]["price_usd"], 0.000501)
        self.assertNotIn("billable_seconds", details)
        self.assertEqual(details["quote"]["audio_seconds"], 80_001 / 16_000)
        self.assertEqual(details["quote"]["currency"], "USDC")

    def test_exact_sample_quote_uses_integer_micro_usdc(self) -> None:
        for samples, price in ((1, 0.0001), (16_000, 0.0001), (48_000, 0.0003),
                               (67_200, 0.000420), (80_001, 0.000501),
                               (960_000, 0.006)):
            with self.subTest(samples=samples):
                quote = grid_transcription.metadata(b"\x00\x00" * samples, "auto")["quote"]
                self.assertEqual(quote["price_usd"], price)
                self.assertEqual(quote["sample_count"], samples)
                self.assertEqual(quote["audio_seconds"], samples / 16_000)

    def test_file_validation_rejects_container_odd_and_oversized_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wav = root / "audio.wav"
            wav.write_bytes(b"RIFF")
            with self.assertRaisesRegex(grid_transcription.InputError, "raw PCM"):
                grid_transcription.read_pcm(str(wav))

            odd = root / "odd.pcm"
            odd.write_bytes(b"\x00")
            with self.assertRaisesRegex(grid_transcription.InputError, "even number"):
                grid_transcription.read_pcm(str(odd))

            large = root / "large.pcm"
            large.write_bytes(b"\x00\x00" * (grid_transcription.MAX_SAMPLES + 1))
            with self.assertRaisesRegex(grid_transcription.InputError, "60 seconds"):
                grid_transcription.read_pcm(str(large))

    def test_language_hint_is_auto_or_lowercase_two_letter_code(self) -> None:
        raw = b"\x00\x00"
        self.assertEqual(grid_transcription.metadata(raw, "en")["language"], "en")
        for invalid in ("EN", "eng", "e1", ""):
            with self.subTest(invalid=invalid):
                with self.assertRaises(grid_transcription.InputError):
                    grid_transcription.metadata(raw, invalid)

    def test_growing_file_read_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "growing.pcm"
            path.write_bytes(b"\x00\x00")
            stream = io.BytesIO(b"\x00" * (grid_transcription.MAX_PCM_BYTES + 2))
            with patch.object(Path, "open", return_value=stream):
                with self.assertRaisesRegex(grid_transcription.InputError, "grew beyond"):
                    grid_transcription.read_pcm(str(path))

    def test_dry_run_never_imports_sdk_or_calls_network(self) -> None:
        args = argparse.Namespace(path="clip.pcm", language="auto", dry_run=True)
        with patch.object(grid_transcription, "read_pcm", return_value=b"\x00\x00"), \
             patch.object(grid_transcription.requests, "get", side_effect=AssertionError("network called")), \
             patch.dict(sys.modules, {"singularity_grid": None}), redirect_stdout(io.StringIO()):
            self.assertEqual(grid_transcription.transcribe(args), 0)

    def test_submission_delegates_sealing_to_sdk_and_closes_client(self) -> None:
        client = MagicMock()
        client.transcribe_pcm.return_value = {"text": "synthetic test"}
        factory = MagicMock(return_value=client)
        args = argparse.Namespace(path="clip.pcm", language="en", dry_run=False,
            api_key="test-key", base_url="https://grid.example", node=None, max_price=0.006)
        with patch.object(grid_transcription, "read_pcm", return_value=b"\x00\x00"), \
             patch.dict(sys.modules, {"singularity_grid": SimpleNamespace(GridClient=factory)}), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(grid_transcription.transcribe(args), 0)
        client.transcribe_pcm.assert_called_once_with(b"\x00\x00", model="whisper-1", language="en",
            use_credits=True, node=None, max_price=0.006)
        client.close.assert_called_once()
        client.transcribe_pcm.side_effect = RuntimeError("sensitive server response")
        with patch.object(grid_transcription, "read_pcm", return_value=b"\x00\x00"), \
             patch.dict(sys.modules, {"singularity_grid": SimpleNamespace(GridClient=factory)}):
            with self.assertRaisesRegex(grid_transcription.InputError, "reconcile") as raised:
                grid_transcription.transcribe(args)
        self.assertNotIn("sensitive", str(raised.exception))

    def test_empty_or_odd_pcm_metadata_is_rejected(self) -> None:
        for value in (b"", b"\x00", b"\x00" * (grid_transcription.MAX_PCM_BYTES + 2)):
            with self.assertRaises(grid_transcription.InputError):
                grid_transcription.metadata(value, "auto")


if __name__ == "__main__":
    unittest.main()
