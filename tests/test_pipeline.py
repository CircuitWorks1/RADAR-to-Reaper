"""Synthetic fixtures only: no original images, metadata or recordings."""
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "radar_image_to_reaper.py"
SOX = os.environ.get("SOX_EXE") or shutil.which("sox")
spec = importlib.util.spec_from_file_location("converter", str(SCRIPT))
converter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(converter)


def project_bytes(source_id=2):
    header = bytearray(317)
    struct.pack_into("<I", header, 21, 48000)
    struct.pack_into("<I", header, 301, 1)
    marker = struct.pack("<II12s", 240, 7, b"Test marker")
    clip = struct.pack("<8I", 0, 0, 0, 240, source_id, 10, 80, 0)
    return bytes(header) + marker + struct.pack("<I", 1) + clip + bytes(23 * 4)


def directory_entry(name, extension, attr, cluster, size):
    entry = bytearray(32)
    entry[:11] = name.encode().ljust(8, b" ") + extension.encode().ljust(3, b" ")
    entry[11] = attr
    struct.pack_into("<HI", entry, 26, cluster, size)
    return entry


def make_image(path, corrupt_fat=False, loop=False):
    # Tiny sparse image with the same geometry, one synthetic recording and project.
    bpb = bytearray(512)
    bpb[3:11] = b"RADAR5.0"
    struct.pack_into("<H", bpb, 11, 512)
    bpb[13] = 64
    struct.pack_into("<H", bpb, 14, 58)
    bpb[16] = 2
    struct.pack_into("<H", bpb, 17, 512)
    struct.pack_into("<H", bpb, 22, 323)
    bpb[36] = 0xF0
    bpb[54:59] = b"FAT20"
    fat = bytearray(323 * 512)
    for c in range(6):
        value = 4 if loop and c == 4 else 0xFFFFF
        off = c * 20 // 8
        shift = (c % 2) * 4
        packed = int.from_bytes(fat[off:off+4], "little")
        packed = (packed & ~(0xFFFFF << shift)) | (value << shift)
        fat[off:off+4] = packed.to_bytes(4, "little")
    pcm = struct.pack("<200h", *range(-100, 100))
    project = project_bytes()
    with path.open("wb") as f:
        f.seek(16384); f.write(bpb)
        f.seek(46080); f.write(fat)
        second = bytearray(fat)
        if corrupt_fat:
            second[0] ^= 1
        f.write(second)
        f.seek(376832)
        f.write(directory_entry("AUDIO", "", 16, 2, 0))
        f.write(directory_entry("PROJECTS", "", 16, 3, 0))
        for c, data in [
            (2, directory_entry("00000002", "SND", 0, 4, len(pcm))),
            (3, directory_entry("PROJ01", "BIN", 0, 5, len(project))),
            (4, pcm), (5, project),
        ]:
            f.seek(393216 + (c - 2) * 32768)
            f.write(data.ljust(32768, b"\0"))
    return pcm


class PipelineTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT)] + list(args),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_help_and_optimization_guard(self):
        self.assertEqual(self.run_cli("--help").returncode, 0)
        result = subprocess.run([sys.executable, "-O", str(SCRIPT), "--help"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"Run without -O", result.stderr)

    def test_duplicate_images_rejected_before_output_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); image = base / "disk.hda"; output = base / "output"
            make_image(image)
            result = self.run_cli("--images", str(image), str(image), "--output", str(output))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"Duplicate image path", result.stderr)
            self.assertFalse(output.exists())

    def test_bad_fat_and_loop_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            for name, options, exception in [
                ("bad_fat", {"corrupt_fat": True}, AssertionError),
                ("loop", {"loop": True}, ValueError),
            ]:
                image = base / (name + ".hda"); make_image(image, **options)
                output = base / name; output.mkdir()
                with self.assertRaises(exception):
                    converter.extract_images([image], output, "not-invoked")

    def test_missing_project_source_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); projects = base / "HD00" / "projects"
            projects.mkdir(parents=True)
            (projects / "PROJ01.BIN").write_bytes(project_bytes(source_id=99))
            (base / "manifest.csv").write_text("wav,samples\nHD00/wav/00000002.wav,200\n")
            with self.assertRaises(AssertionError):
                converter.build_projects(base)

    @unittest.skipUnless(SOX, "Install SoX or set SOX_EXE for end-to-end coverage")
    def test_full_cli_audio_integrity_timing_and_read_only_input(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); image = base / "arbitrary_filename.hda"; output = base / "export"
            pcm = make_image(image)
            before = hashlib.sha256(image.read_bytes()).hexdigest()
            result = self.run_cli("--images", str(image), "--output", str(output), "--sox", str(SOX))
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            self.assertEqual(before, hashlib.sha256(image.read_bytes()).hexdigest())
            self.assertEqual((output / "HD00/snd/00000002.SND").read_bytes(), pcm)
            with wave.open(str(output / "HD00/wav/00000002.wav"), "rb") as w:
                self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()),
                                 (1, 2, 48000, 200))
                self.assertEqual(w.readframes(200), pcm)
            with (output / "manifest.csv").open(newline="") as f:
                row = next(csv.DictReader(f))
            self.assertEqual(row["pcm_sha256"], hashlib.sha256(pcm).hexdigest())
            summary = json.loads((output / "summary.json").read_text())
            self.assertEqual(summary["by_image"]["00"], 1)
            rpp = (output / "REAPER/PROJ01.rpp").read_text()
            self.assertIn("POSITION 0.005000000000", rpp)
            self.assertIn("LENGTH 0.001666666667", rpp)
            self.assertIn("SOFFS 0.000208333333", rpp)
            self.assertIn('FILE "../HD00/wav/00000002.wav"', rpp)
            self.assertIn('MARKER 1 0.005000000000 "Test marker" 0', rpp)
            self.assertEqual(rpp.count("<TRACK"), 24)
            retry = self.run_cli("--images", str(image), "--output", str(output), "--sox", str(SOX))
            self.assertNotEqual(retry.returncode, 0)
            self.assertIn(b"Output must be a new or empty folder", retry.stderr)


if __name__ == "__main__":
    unittest.main()
