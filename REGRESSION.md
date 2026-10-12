# Phase B — Regression reference and results

Evidence reviewed on 2026-10-13.

The frozen implementation remains the behavioral oracle. These tests preserve
its observed behavior; they do not certify the correctness of the underlying
FPS, frametime or tearing interpretation.

See BASELINE.md for source/build provenance and PROFILING.md for measurement
boundaries.

## Harness architecture

baseline/reference.cpp calls the original frozen FrameProcessing implementation
through its original Qt pipeline adapters.

The original application is built separately. Reference drivers compile a
generated observed source tree with test instrumentation and narrowly scoped
BaselineProbe access. Production kernels are not replaced.

Each fixture runs in a separate process. The driver uses synchronous offscreen
stages rather than the application's interactive QML repaint-driven lifecycle.

Driver variants:

| Binary | Observation | Profiling |
| --- | --- | --- |
| oracle.exe | Enabled | Disabled |
| observed-profile.exe | Enabled | Enabled |
| profile.exe | Compiled out | Enabled |

reference/ and repeat/ are separate oracle captures.
observed-profile/ is the profiling-enabled semantic capture.
lean-profile/ runs pipeline_csv without tracing.

## Deterministic fixture format

baseline/fixtures.py generates packed row-major BGR24 bytes without a codec,
random generator or OpenCV dependency.

Each frame is addressed by its SHA-256. The manifest records case settings,
ordered streams, dimensions, input FPS, thresholds and applicable options.
The driver checks hashes and dimensions before submitting the pixels.

Non-contiguous cases copy the same packed logical bytes into a padded Mat ROI.
Padding is not included in captured logical-pixel bytes.

The static artifact audit verified every referenced fixture member's hash and
declared BGR byte count. Fixtures are input data; reference outputs come from
execution of the frozen implementation.

## Executed fixture inventory

The default inventory contains 82 regression cases and two hazard cases.

| Regression group | Cases | Coverage |
| --- | ---: | --- |
| Initial/basic inputs | 4 | Empty, single, identical and fully changed |
| Periodic-repeat rings | 8 | FPS 1, 24, 29.97, 30, 59.94, 60, 120 and 240 |
| Long hold | 1 | Duplicate hold extending beyond the ring |
| Threshold boundaries | 10 | Thresholds 0, 1, 5 and 255 with clipped adjacent differences |
| Equal-gray color change | 1 | Different color bytes with the small grayscale edge case |
| Row completeness | 6 | Top/bottom placement and 1/2/3 changed pixels across width 20 |
| Tear patterns/dismissal | 32 | Four row patterns and dismissal 0/9/10/11/49/50/51/100 |
| Geometry and stride | 10 | Five dimensions, contiguous and padded ROI layouts |
| Reset/options | 2 | Stale-tear reset and threshold change |
| Multiple inputs | 3 | Two/three videos and unequal stream lengths |
| Retained tears | 1 | Repeated tears with tear drawing disabled |
| Export/pipeline | 4 | CSV, JPEG, centering and redraw |
| Total | 82 | |

Geometry dimensions are 1×1, 9×1, 9×2, 17×11 and 33×3.
Most other fixtures use 20×10 input pixels.

The generator offers optional 720p, 1080p and 4K fixtures through --large.
The successful workflow did not request them; they are not part of these results.

## Captured semantics

Per-frame records include source index, comparison availability, ordered videos,
thresholds, FPS and frametime, input/grayscale/mask descriptors, changed-pixel
and per-row counts, row fractions, contribution, duplicate decision and branch.

Tear records preserve indices, video identity, order and multiplicity.
Retention and renderer image-queue observations are also captured.

The first frame has no pairwise comparison. Summary counters distinguish
submitted batches, compared pairs and duplicate/nonduplicate pairs.

These counters are not a count of globally distinct images. Fractional tear
contributions must not be silently interpreted as integer unique-frame totals.

## Equality rules

Semantic file inventories must match and be nonempty.

| Data | Rule |
| --- | --- |
| Discrete values, thresholds, counts and decisions | Exact |
| Tear indices, ordering and multiplicity | Exact |
| Input, grayscale and mask bytes | Exact |
| CSV and JPEG files on the frozen setup | Exact bytes |
| JSON object fields and list lengths/order | Exact |
| Named floating fields | Documented tolerance |

The only tolerant fields are:

fps, frametime_ms, contribution, row_fraction, max_tear_fraction

The rule is:

abs(reference - candidate) <= 1e-9 + 1e-12 * abs(reference)

It uses each field's own units and the reference magnitude. Unexpected NaN or
infinity is rejected for these numeric comparisons.

The repository comparator permits int/float interchange in tolerant fields.
The independent artifact audit added a stricter same-type requirement and still
passed. No repository comparator change was made.

All remaining values require exact type and value equality. Lists are not sorted
to hide ordering or multiplicity differences.

Runtime records, process logs and timing files are outside the semantic subtree.
They are preserved but are not included in semantic equality comparisons.

CSV uses the original QTextStream formatting. Exact CSV equality is verified;
rounded CSV values are not a replacement for the higher-precision JSON trace.
No CSV newline normalization was applied in this audit.

## Verified comparison results

Successful GitHub Actions Run #8 executed both mandatory comparisons.

Independent static inspection of its artifact established:

| Comparison | Cases | JSON files | Exact byte files | Result |
| --- | ---: | ---: | ---: | --- |
| reference versus repeat | 82 | 82 | 10741 | PASS |
| reference versus observed-profile | 82 | 82 | 10741 | PASS |

All three result lists covered the same 82 expected cases in the expected order,
with exit code zero. Their runtime source/version and driver-mode records were
consistent with the build configuration.

These results establish deterministic captured behavior and equivalence with
profiling enabled for the tested inputs and configuration. They do not prove
negligible profiling overhead or correctness on other thread configurations.

## Export inventory validation

Expected exports are derived from fixture scheduling and frozen exporter behavior,
rather than by treating one capture's inventory as sufficient truth.

For pipeline fixtures:

- Each exporting processImage call advances the image number and appends a CSV row.
- preview_first suppresses the first export call.
- redraw_at adds one exporting call for that frame.
- CSV contains one header plus the exporting calls, with two columns per video.
- JPEG names use exportsequence_ followed by ten decimal digits and .jpg.
- finishExporting closes CSV, resets the frame counter and clears stored names.

Required outputs must exist and be nonempty. Unexpected CSV/JPEG/TIFF exports
are rejected. CSV row counts, column counts and nonempty cells are checked.

Executed export expectations:

| Fixture | Required output |
| --- | --- |
| pipeline_csv | CSV: 4 rows including header, 2 columns |
| pipeline_images | Four JPEGs numbered 0000000000 through 0000000003 |
| pipeline_centered | CSV: 5 rows including header, 2 columns |
| pipeline_redraw | CSV: 6 rows including header, 2 columns |

The independent audit recalculated expectations from the fixture manifest and
verified all three captures, avoiding acceptance of two identically incomplete
captures.

There is no fixture combining CSV and image export. JPEG byte equality does not
independently validate decoded JPEG pixels or cross-platform rendering.

## Decode smoke test

The separate smoke test used the frozen VideoCaptureList and the historical
rendered demonstration video, not a labeled raw-motion truth dataset.

Verified artifact evidence:

- Backend: FFMPEG.
- Input: 960×540, recorded rate 30 FPS.
- Metadata-reported source frames: 119.
- Successfully decoded and submitted frames: 10.
- Configured limit: 10.
- Successful-read counter: [10].
- Counter after restart: [0].
- Ten frame records in the semantic trace.

The test fails if zero frames decode. It does not check the full 119-frame input,
EOF behavior, all codec formats or successful decoding after the restart.
Reset counters alone do not establish seek correctness.

## Historical hazard observations

| Case | Exit code | Interpretation |
| --- | --- | --- |
| zero_fps | 3221225477 / 0xC0000005 | Observed Windows access violation |
| reexport | 3221225477 / 0xC0000005 | Observed Windows access violation |

Both are classified as hazard observation and excluded from the successful
regression suite. Crashes or timeouts in this category are retained as evidence;
workflow success does not convert them into passing correctness tests.

Source analysis identifies relevant risks: an empty FPS ring can be indexed,
and finishExporting clears names while retaining the active-video count.
The artifact exit codes do not independently identify the precise faulting
instruction.

## Preserved defects and correctness boundaries

AUDIT.md identifies shared tear state, cross-video contamination, repeated tear
records, retained tear/image memory, last-row behavior, invalid FPS and reset/
re-export/EOF hazards.

Fixtures exercise several of these paths, but matching legacy output does not
make the behavior correct. Undefined behavior and races are not a portable
golden contract.

No fixes were included. Future correctness changes require separate approval,
explicit intentional-result changes and retention of this legacy reference.

## Untested functionality

The evidence does not include:

- Interactive GUI loading, playback, pause/resume or repaint/event-loop pacing.
- Clean Windows machine deployment.
- Multithread scalability or race characterization at 2/4/8 threads.
- Combined CSV and image export.
- Optional large-resolution fixtures.
- Full EOF/restart/re-export lifecycle through QML.
- Broad codec, malformed-input, Unicode-path or invalid-metadata coverage.
- A long-running memory benchmark.
- CUDA, OpenCL or DirectX compute backends.

Both compared drivers use the observed frozen implementation. The uninstrumented
GUI executable was built, but its interactive semantics were not independently
compared against the harness.

## Use as a future regression gate

Future approved candidates should consume identical decoded pixel fixtures and
preserve all applicable exact and tolerance checks. Do not regenerate goldens
automatically when a comparison fails.

Keep correctness changes separate from optimization equivalence. Report the first
differing case, file, frame or field. Passing this suite is necessary evidence for
future work, not a substitute for the untested deployment and application paths.
