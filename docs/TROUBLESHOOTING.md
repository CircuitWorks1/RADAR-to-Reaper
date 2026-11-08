# Troubleshooting

- **SoX not found:** run `sox --version` or pass `--sox` with the full executable path. On Windows, retain the DLLs shipped alongside `sox.exe`.
- **Output must be new or empty:** choose another destination. The converter will not overwrite previous work.
- **Unsupported header/geometry/disk ID:** the image layout does not match the tested format, or the image is not a raw full-disk image. Do not bypass the checks.
- **Missing source ID / bounds assertion:** include every disk from the same project set. This can also indicate a different project format or damaged metadata.
- **FAT copies differ / chain failure:** the source may be damaged or unsupported. The converter does not repair images. Preserve the originals.
- **Assertion or other failure:** partial output remains for inspection. Correct the cause and rerun into a new empty destination. There is no resume mode.
- **REAPER cannot find media:** restore the original relative arrangement of REAPER and HD* folders, or relink the WAVs manually. Extraction images are not needed after a successful recovery.
- **Timing looks wrong on the musical grid:** 120 BPM is a placeholder. Positions are derived from samples; set the musical tempo separately without moving items.
- **Unexpected levels/panning:** original mixer settings were not decoded. Every track starts at unity and centered pan.

The WAV hash checks establish preservation of extracted PCM, not agreement with original hardware playback or proof that every RADAR variant uses this audio encoding.
