# Reverse-engineered RADAR 1 format notes

These are observations from one disk set, not an official specification. Integers are little-endian. Unknown fields should remain unknown until supported by evidence.

## Disk layout

- Volume boot sector at byte 16,384. OEM string `RADAR5.0`; filesystem label `FAT20`.
- Bytes/sector: 512; sectors/cluster: 64; reserved sectors: 58; two FAT copies; 512 root-directory entries; 323 sectors per FAT.
- FAT 1 at byte 46,080, length 165,376 bytes; FAT 2 immediately follows.
- Fixed root directory at byte 376,832, length 16,384 bytes.
- Data cluster 2 at byte 393,216; clusters are 32,768 bytes.
- Boot-sector byte 36 contains `0xF0`, `0xF1`, or `0xF2`, treated as disk indices 0, 1, 2. Output folders are HD00, HD10, HD20.

FAT entries are packed 20-bit values. For cluster `c`, read four bytes starting at `floor(c * 20 / 8)`, shift right by `(c % 2) * 4`, and mask with `0xFFFFF`. Values at or above `0xFFFF8` terminate a chain. The reader rejects loops, invalid terminators and out-of-range/truncated reads. The fixed cluster guard is inherited from the observed layout.

Directory entries use 32-byte DOS-style records, with an 8.3 name, attributes, uint16 starting cluster at offset 26, and uint32 file length at offset 28. Deleted entries (`0xE5`) and volume labels are ignored. Active files in AUDIO and PROJECTS are extracted. High cluster-word extensions and nested directory trees are not implemented.

## Audio

The observed `.SND` files contain headerless signed 16-bit little-endian mono PCM. Project sample-rate fields indicate 48,000 Hz. Long recordings can have interleaved cluster allocation across tracks; copying contiguous bytes from the first cluster is incorrect.

SoX invocation:

```sh
sox -D -t raw -e signed-integer -b 16 -L -r 48000 -c 1 input.SND output.wav
```

## Binary projects

- Fixed header: 317 bytes.
- uint32 sample rate at byte 21; accepted value 48,000.
- uint32 marker count at byte 301.
- Marker records begin at byte 317, each 20 bytes: uint32 sample position, uint32 marker ID, 12-byte label.
- After markers: 24 track lists. Each starts with uint32 clip count, followed by that many 32-byte records.

Each clip record is eight uint32 values:

| Dword index | Interpretation |
| --- | --- |
| 0–2 | Unknown; some values resemble in-memory references |
| 3 | Timeline position, in samples |
| 4 | Source SND ID (hexadecimal filename stem) |
| 5 | Source offset, in samples |
| 6 | Length, in samples |
| 7 | Unknown |

All eight values are retained in decoded JSON. In the original set, every project parsed exactly to EOF, every source reference existed, and every source range fit within the corresponding file. These invariants support the field interpretation. Unknown project/track settings are not inferred from apparent pointers or strings.

REAPER item POSITION, LENGTH and SOFFS use sample values divided by 48,000. Tracks are written in original list order. Markers receive sequential REAPER IDs; original IDs remain in decoded JSON. Short audio segments used for edits are included directly, without adding fades. No overlapping items were present in the supported source projects; the implementation currently rejects overlaps.
