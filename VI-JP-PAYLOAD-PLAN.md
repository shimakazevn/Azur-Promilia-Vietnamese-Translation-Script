# Vietnamese payload for the JP server — work plan

Target: translate the **JP PC client** (`AzurPromiliaJP`, resource version
`3219598`, builtin `3075915`) to Vietnamese. The TW plan is parked — the
user plays JP.

Status (26/11/2026): **not built yet**. The fork only has language
scaffolding (`tools/*-deployment-vi.json`, status `placeholder-no-payload`).
This file records what is needed so the build can start as soon as the
inputs exist.

## What a JP payload is

11 files, ~295 MB, listed in `tools/jp-deployment.json`:

| File | Size |
| --- | --- |
| `.res/raw_base_package/BundleFiles/z5xzl3cg6ao0ilpbzykexg.r` | 127 MB |
| `.res/raw_streaming_package/BundleFiles/fcl0wxz2z6hoffogv4xgzw.r` | 27 MB |
| `resources.assets` | 46 MB |
| `StreamingAssets/.res/static_package/6pq4a7hlp7zidu91dvvww.r` | 55 MB |
| 7 smaller `.r` bundles (`default_package`) | ~4–11 MB each |

Each file must be replaced by a file of **exactly the same size, with the
same whole-file CRC32 and the same per-segment CRC32** as the original
(equal-length replacement + CRC balancing). One byte longer = rejected.

## Inputs needed (none of these are in this repo)

1. **JP PC game install** — `AzurPromiliaJP_Data` from a working JP PC
   install, resource version `3219598`. The build scripts in
   `CRC工具/jp_crc/` expect the live install at
   `E:\YostarGames\AZUPRO_JP` (see `baseline.py`: `LIVE`, `BACK`).
   At minimum: the 11 files above + the `.bytes`/`.hash` manifest files
   next to them (18 readonly guards in `jp-deployment.json`).
2. **Translated bundles (`game_candidate`)** — the JP Unity bundles with
   their text replaced by Vietnamese, same object structure. This is the
   actual translation work and does not exist yet. How the ZH version did
   it: extract strings from the JP bundles, translate, rebuild the
   bundles with UnityPy, then fit them into the original slots with
   `CRC工具/jp_crc/bundles.py` (`F.repack` + `patch_crc`).
3. **A font that contains Vietnamese glyphs.** The JP fonts are subset
   with `CRC工具/jp_crc/corpus_codepoints.json` (GB2312 + JIS only).
   **Every Vietnamese diacritic is missing from that corpus** — 893
   codepoints, e.g. à á ả ã ạ ă â ê ô ơ ư đ. Use
   `CRC工具/jp_crc/corpus_codepoints_vi.json` (6027 codepoints) as
   `corpus_codepoints.json` when building the VI payload, and check first
   whether the game's fonts actually contain Vietnamese outlines — if a
   font has no Vietnamese glyphs, subsetting keeps nothing and the text
   shows as boxes.

## Build steps (on the Windows PC with the game installed)

1. Verify the install: `tools/jp-deployment.json` — every file's
   `source_sha256` must match the installed files; resource version must
   be `3219598`.
2. Extract JP strings from the 11 files, translate JP → VI. Keep
   translations short: each UnityFS segment must fit in its original
   slot after LZ4 recompression. If a segment overflows, `bundles.py`
   raises `Localized non-font segment exceeds original slot` — that
   string must be shortened, not the slot enlarged.
3. Rebuild the translated bundles (`game_candidate/`), then run
   `CRC工具/jp_crc/bundles.py` to fit them into the original slots
   (produces `fixed_candidates/` + `bundle_report.json`, status
   `complete`).
4. Run `CRC工具/jp_crc/build_release.py` to verify size/CRC/segments
   and write the release payload.
5. In the fork, fill in `tools/jp-deployment-vi.json`:
   `target_sha256` per file, `status` → `ready`; regenerate
   `tools/package-files-vi.json` with
   `build_release.py --language vi`. Only then can
   `Manage-Localization.ps1 -Language vi` actually apply anything.
6. Test on Windows: apply, launch the JP client, check login works and
   Vietnamese renders (especially diacritics). Restore first if login
   fails — the project has no anti-cheat test.

## What this VM can and cannot do

- Can: parse Unity bundles (UnityPy 1.25.4 installed in a venv here),
  run the CRC/fit checks, build the VI font corpus (done).
- Cannot: run the JP game, install the 120 GB JP PC client, or extract
  JP text — no game files exist on this VM. The build needs the game
  files copied here, or to run on the Windows PC where JP is installed.
