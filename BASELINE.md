# Phase B — Frozen Windows x64 reference baseline

Evidence reviewed on 2026-10-13.

This document records the Windows reference build and its provenance. The
regression results are documented in REGRESSION.md; instrumentation and timing
interpretation are documented in PROFILING.md.

AUDIT.md remains the historical Phase 0 assessment. Its statements about work
not yet performed describe that earlier phase.

## Frozen source and build infrastructure

| Item | Identity |
| --- | --- |
| Repository | Redcomet73/trdrop |
| Frozen production commit | a0b4563a076e336863f743ec92c1ee8221f5aba6 |
| Frozen production tree | 2759fa354d66adbc342c882d8f0faa390699bed4 |
| Successful infrastructure commit | ac7825873c8e6e7717cc815a099d1229db6e4cc9 |
| GitHub Actions run | 38310314708, run number 8, attempt 1 |

Run: https://github.com/Redcomet73/trdrop/actions/runs/38310314708

The application is compiled from the extracted original frozen source.
Reference drivers compile the generated observed copy of that same source.
Production analysis kernels are not replaced or optimized.

The reference driver is an offscreen synchronous harness. It does not reproduce
the complete interactive QML application lifecycle.

## Historical production toolchain

| Component | Recorded configuration |
| --- | --- |
| Qt | 5.15.2, win64_mingw81 |
| Compiler | MinGW-W64 GCC 8.1.0, x86_64-posix-seh-rev0 |
| Compiler target | x86_64-w64-mingw32 |
| Build system | qmake, win32-g++ |
| Reference-driver language mode | C++11 |
| Build mode | Release |
| Application parallelism | Original OpenMP implementation retained |
| OpenCV | Historical 4.5.1 binary dependency |
| Python helper | CPython 3.13.15 x64 |

The build record declares no fast-math or ISA overrides.

Python is part of build provenance, not TRDROP's production analysis algorithm.
The selected interpreter and locked helper virtual environment are recorded
separately.

## Build-provider pins

The workflow pins immutable action commits:

| Action | Commit |
| --- | --- |
| actions/checkout | de0fac2e4500dabe0009e67214ff5f5447ce83dd |
| actions/setup-python | 5fda3b95a4ea91299a34e894583c3862153e4b97 |
| jurplel/install-qt-action/action | 48d3ad6db93f3627c8ee7a0454bc6f3744f7e730 |
| actions/upload-artifact | 043fb46d1a93c77aae656e7c1c64a875d1fc6a0a |

The Qt executable sub-action is used directly. Its root composite wrapper is
not used.

setup-python selects exactly CPython 3.13.15 x64. Provisioning on the ephemeral
runner is an explicitly approved exception; a pre-existing runner tool-cache
entry is not required.

Python identity, effective PATH resolution, virtualenv membership and base
interpreter identity are checked before the Qt action. Hash-locked wheels are
installed, and the installed package inventory is checked after the action.

The independent artifact audit verified 26 package versions against the lock
and 26 installation-report archive hashes against its authorized hashes.
This included aqtinstall 3.3.0 and py7zr 1.1.3.

## OpenCV dependency provenance

Historical URL:

https://github.com/illusion0001/opencv-build/releases/download/4.5.1/opencv-4.5.1.7z

Canonical URL:

https://github.com/illusionyy/opencv-build/releases/download/4.5.1/opencv-4.5.1.7z

The build requires the historical URL to return HTTP 301 to that exact canonical
URL. The recorded archive identity is:

- Size: 167306384 bytes.
- SHA-256:
  0e92740a93f2575036c1b3e07da6e7ed4d81e84882deb406c435d482b5d621f6
- Release ID: 56244497.
- Asset ID: 52959360.

The Windows build verifies archive size and SHA-256 before extraction.
The static artifact audit verified consistency of these recorded values.

The original historical CI did not record a digest. Consequently, the approved
archive's identity is established, but historical immutability is not proven.
The original dependency was not replaced with a newer OpenCV release.

## Frozen-source enforcement

baseline/prepare.py:

1. Resolves the exact frozen commit and requires the expected tree.
2. Reads Git objects with replacement objects disabled.
3. Inventories all 80 frozen files, recording Git blob IDs, modes, sizes and
   SHA-256 values.
4. Generates a tar archive with command-scoped core.autocrlf=false.
5. Verifies the extracted original file inventory and bytes against Git blobs.
6. Copies the verified original tree to a separate observed tree.
7. Applies 31 uniquely anchored instrumentation edits and records their ledger.
8. Checks reversal of the edits against the original decoded source text.
9. Reconstructs the observed source from verified originals and the approved
   insertion recipe, checking the generated tree and recorded ledger.

The build script performs preparation verification before compilation and again
before declaring success. These are mandatory CI success gates.

Original extraction verification is byte-for-byte. Generated edited text uses
UTF-8 without BOM and LF; reversal checks source text under the preparation
script's decoding rules. Original extracted files are not normalized.

## Successful CI environment

Recorded for Run #8:

| Item | Value |
| --- | --- |
| Runner label | windows-2022 |
| Runner image | win22 |
| Runner image version | 20261004.326.1 |
| OS | Microsoft Windows Server 2022 Datacenter |
| OS version/build | 10.0.20348 / 20348 |
| CPU description | AMD EPYC 9V74 80-Core Processor |
| Runner-reported cores | 2 |
| Runner-reported logical processors | 4 |

The CPU description does not imply that the runner had 80 available cores.

The harness uses offscreen Qt and a controlled single-thread reference policy.
The script sets OMP_NUM_THREADS=1, OMP_DYNAMIC=FALSE, OMP_NESTED=FALSE and
OMP_MAX_ACTIVE_LEVELS=1. The driver defaults OpenCV to one thread.

The runner label is a moving image. Recording its version does not freeze future
runner images or prove bit-identical rebuilds.

## Artifact identity and independent inspection

| Item | Value |
| --- | --- |
| Artifact name | trdrop-reference-win64-a0b4563-38310314708-1 |
| Artifact ID | 11775006290 |
| ZIP size | 90031402 bytes |
| ZIP files | 33979 |
| Total uncompressed bytes | 286624186 |
| Verified member-hash records | 33978 |

Archive SHA-256:

735d5bf02af562bec646c490a38283ea1dab942bd36b02c5628030d2c467bf88

The independent static audit streamed the archive without extracting or executing
its contents. It verified the archive digest, ZIP path/type/size constraints,
all member hashes and exact manifest coverage. hashes.json deliberately excludes
itself.

No malformed hash records, missing listed files, unlisted files or member-hash
mismatches were found.

Principal artifact groups are:

- bin/: original application, reference drivers and deployed dependencies.
- fixtures/: fixture manifest and deterministic packed BGR data.
- reference/, repeat/, observed-profile/: captures and process results.
- hazards/: separately classified historical-defect observations.
- lean-profile/: tracing-disabled profiling capture.
- decode-smoke/: video metadata, decoded-frame evidence and trace.
- STATUS.json, source-manifest.json, toolchain.json, hashes.json.
- Python lock, selected-interpreter and installation-report records.

Member inventory verification establishes coverage against hashes.json. It is
not a clean-machine deployment test or a complete executable dependency analysis.

## Reproduction procedure

This procedure describes a future authorized run; documenting it does not
authorize CI execution or local execution of downloaded software.

Use the workflow and baseline implementation from the infrastructure revision
identified above in an approved disposable Windows environment:

1. Obtain the infrastructure checkout with the frozen Git objects available.
2. Use the pinned providers to select and verify Python, create a fresh helper
   virtualenv and install the hash-locked wheels.
3. Install Qt 5.15.2 win64_mingw81 and qt.tools.win64_mingw810.
4. Download and verify the historical OpenCV archive.
5. Prepare and verify fresh original and observed source directories.
6. Compile the original application and the three driver variants.
7. Deploy Qt and the required OpenCV/MinGW runtime dependencies.
8. Run helper tests, fixture captures, repeat and profiling comparisons,
   hazard observations, lean profiling and the ten-frame decode smoke test.
9. Reverify frozen/generated sources and preserve STATUS.json, provenance,
   hashes and the complete reference-artifact directory.

baseline/windows.ps1 expects the workflow's verified Python environment,
QT_ROOT_DIR, IQTA_TOOLS and RUNNER_TEMP. It is not a standalone setup script.
It refuses to reuse the build and artifact directories.

A new run produces a new artifact identity. Compare its configuration and
semantic outputs; do not expect the ZIP, executables or timings to be identical.

Workflow permissions remain contents: read. Checkout does not persist
credentials. The workflow does not publish releases.

## Deployment behavior and limitations

windeployqt uses the historical Qt 5.15.2 automatic MinGW deployment mode,
with --verbose 2 and --qmldir. The explicit --release selector was removed after
investigation of historical MinGW debug/release classification behavior.

The script reports expected and PATH-selected qmake, reports both plugin
directories, checks that qwindows.dll exists and is nonempty, and preserves
windeployqt failure handling. Plugins are not manually substituted.

Run #8's build/deployment step succeeded, and offscreen reference drivers ran.
This does not establish interactive GUI operation or deployment on a clean
Windows machine.

## Evidence boundaries

Direct independent artifact verification established:

- Artifact integrity and recorded member inventory.
- Reference/repeat and profiling-on/off semantic equivalence.
- Frozen Git tree identity reconstructed from manifest records.
- Eight original header identities and 31 applicable, reversible edits.
- Internal consistency of toolchain and dependency records.
- Profiling and decode-smoke records.

The artifact does not contain the complete original and observed source trees,
or a separately published observed-tree manifest. The independent audit therefore
did not verify byte-for-byte the entire compiled observed tree.

Ledger applicability and reversal do not alone establish equality to the
approved insertion recipe. CI enforces that recipe; independent artifact
inspection has a narrower provenance boundary.

Recorded toolchain probes and dependency hashes were checked as data. The
independent audit did not execute the tools or rehash dependency archives absent
from the artifact.

No interactive GUI validation, clean Windows deployment test or multithread
scalability benchmark was performed. No fixture combines CSV and image exports.

The successful Windows CI establishes a validated build and regression process
for the recorded environment. It does not guarantee byte-identical binaries or
artifacts in future runs.

Historical defects remain preserved. Phase B evidence does not authorize
correctness changes, performance refactoring or Phase C.
