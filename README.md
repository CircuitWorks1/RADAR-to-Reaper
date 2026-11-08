# RADAR Image to REAPER

Recover audio and editable REAPER sessions from a supported Otari RADAR 1 disk-image set.

One command extracts `.SND` recordings, converts them to WAV using SoX, verifies the audio, and reconstructs the original project timelines as `.rpp` files.

**Experimental, reverse-engineered format support:** tested on one three-disk RADAR 1 set using `RADAR5.0` / `FAT20`. This is not a general importer for every RADAR generation or software version.

## Requirements

- Python 3.7 or newer, run without `-O` or `-OO`.
- [SoX](https://sourceforge.net/projects/sox/) installed separately; no Python packages are needed.
- Images of all disks used by the projects, including the primary disk (ID 0).
- Free output space of approximately twice the extracted audio size. The original validation set needed about 8 GB.
- [REAPER](https://www.reaper.fm/) to open the resulting sessions.

SoX and REAPER are separate products and are not included in this repository.

## Quick start

With `sox` available on PATH:

```sh
python radar_image_to_reaper.py --images HD00_imaged.hda HD10_imaged.hda HD20_imaged.hda --output recovered
```

Windows PowerShell, with an explicit SoX path:

```powershell
python .\radar_image_to_reaper.py --images "D:\HD00_imaged.hda" "D:\HD10_imaged.hda" "D:\HD20_imaged.hda" --sox "C:\Tools\sox\sox.exe" --output "D:\RADAR_export"
```

The destination must be new or empty. Input order and filenames do not matter: disk identities come from their headers. Images are opened read-only. Keep a separate copy of the originals.

The script checks an optional `sox/sox-14.4.2/sox.exe` directory beside itself before searching PATH. Alternatively, pass `--sox`.

## Output

```text
recovered/
  HD00/                 # primary disk
    snd/                # original extracted PCM files
    wav/                # SoX conversions
    projects/           # original active project metadata
  HD10/                 # additional disk, same structure
  HD20/                 # additional disk, same structure
  REAPER/
    PROJ01.rpp          # one session per active project file, including empty projects
    PROJ01_decoded.json # source metadata and decoded clip records
    clips.csv
    summary.json
  manifest.csv          # source image, paths, samples, duration, PCM SHA-256
  summary.json          # extraction totals
```

Open the `.rpp` files in `REAPER/`. Keep that folder beside the `HD*` folders when moving the recovery; audio links use relative paths. Manifest source-image paths may contain local identifying information: review generated reports before sharing them.

## What is preserved

- Original 24-track assignments, timeline positions, source offsets and lengths.
- Sample-based timing, gaps, and marker labels/positions.
- Short rendered edit segments, without applying extra REAPER fades.
- Original `.SND` data and project metadata alongside the converted files.

Audio is interpreted as **48 kHz, signed 16-bit little-endian mono PCM**. No normalization, resampling or audio effects are requested. SoX dithering is disabled. Project names, original track names, mix/mute/solo settings, tempo and timecode preferences are not decoded. Tracks use generic names, unity gain and centered pan. The 120 BPM tempo is a placeholder; item timing is sample-derived. Special marker IDs are labeled without assuming their purpose.

## Validation and limitations

The converter checks known filesystem geometry, distinct disk IDs, matching FAT copies, cluster-chain termination and file lengths. WAV format and sample count are checked, and the SHA-256 of its decoded PCM must equal the extracted SND hash. Project files must parse exactly to EOF; all referenced audio IDs and source ranges must resolve. Written RPP timings must round back to the original sample counts.

The original real-world run recovered 1,812 recordings (3,880,123,328 PCM bytes), four projects, and 450 clip references. A full rerun matched the earlier extraction and sessions. One reconstructed session was visually checked in REAPER 7.82. There has been no playback comparison against the original hardware. No original recordings, metadata, image files or generated sessions are distributed here.

Only active directory entries are extracted. Deleted files/projects, unsupported layouts, repaired filesystems and arbitrary sample rates are outside the current scope. Failed runs retain partial output for inspection; there is no resume or overwrite mode. Retry into a new empty directory. Do not use optimized Python execution: integrity checks use assertions, and the CLI rejects `-O`/`-OO`.

See [format notes](docs/FORMAT.md) and [troubleshooting](docs/TROUBLESHOOTING.md).

## Tests

```sh
python -m unittest discover -s tests -v
```

Tests create synthetic disk images and audio in temporary directories. The end-to-end CLI test requires SoX; set `SOX_EXE` to its executable path if it is not on PATH. Otherwise that test is skipped. No user recordings are required. CI runs the synthetic suite with SoX on Linux.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Please submit synthetic reproductions rather than private recordings. This project is not affiliated with Otari, iZ Technology, Cockos or SoX.

## License

The converter and documentation are provided under the [MIT License](LICENSE). SoX and REAPER retain their own licenses.
