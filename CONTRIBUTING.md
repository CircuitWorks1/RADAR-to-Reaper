# Contributing

Run `python -m unittest discover -s tests -v` before proposing changes. Include SoX on PATH (or set `SOX_EXE`) to exercise the full pipeline.

Keep image access read-only. Do not weaken chain, bounds, EOF or PCM verification checks to accommodate an unknown layout. Document new layouts and sample formats separately, with synthetic fixtures and an explanation of the evidence.

Do not submit copyrighted or private recordings, full drive images, phone numbers, local manifests, or project metadata from a real session. Provide synthetic reproductions or a description of the failing format instead. Report which Python/SoX versions were used and include the error text after removing local identifying paths.

The current implementation deliberately retains the code path validated on the original disk set. Refactoring should retain decoded fields and sample-exact output, not just produce sessions that open.
