# Phase B — Profiling instrumentation and recorded measurements

Evidence reviewed on 2026-10-13.

These are measurements recorded by the Windows reference drivers in Run #8.
The local artifact audit inspected them as data and did not execute binaries.

See BASELINE.md for provenance and REGRESSION.md for semantic equivalence.

## Instrumentation architecture

baseline/prepare.py inserts timers into a generated observed copy of the frozen
source. baseline/telemetry.h supplies RAII Scope timers based on steady_clock.

Elapsed nanoseconds and call counts accumulate in atomic counters. Explicit stop
calls prevent downstream signal-connected stages from being charged to conversion,
composition and rendering timers.

BASELINE_PROFILE controls timer compilation. With profiling disabled, timer
macros compile to no-ops. BASELINE_OBSERVE separately controls observation code.

The observer clones grayscale data and performs an additional mask scan for
per-row counts. The traced driver also writes raw frame data and JSON records.
These operations can materially affect execution time.

| Driver | Timers | Observation/tracing |
| --- | --- | --- |
| oracle.exe | Compiled out | Enabled |
| observed-profile.exe | Enabled | Enabled |
| profile.exe | Enabled | Compiled out; requires --no-trace |

Independent semantic comparisons passed with profiling disabled/enabled across
82 regression cases. This establishes captured semantic equivalence, not zero
overhead or equivalence under every configuration.

## Exact timer boundaries

| Stage | Start and end | Important exclusions |
| --- | --- | --- |
| Decode | populate_next_frames entry through return, including container preparation, serial read calls and counters | Video opening, metadata probes and later stages |
| Grayscale | Before grayscale Mat declarations through completion of both cvtColor calls | Observer grayscale clones |
| Mask | After grayscale observation through the end of _are_equal_with_draw; includes input clone and pixel loop | Additional clone in check_for_difference, row reduction and tear analysis |
| Rows | Before row-vector allocation through completion of row reduction | Observer's additional row-count scan |
| Tear | After _get_row_differences returns through _get_frame_difference return | Row reduction and its observer scan |
| FPS/frametime | Whole get_framerates and get_frametimes calls accumulated together | QML model publication outside those methods |
| Image conversion | Preparation of image list and each conversion, stopping before imagesReady | Downstream signal handlers |
| Image composition | Resolution lookup, scaling, cropping and composition, stopping before imageReady | updateComposition and downstream signal handlers |
| Rendering | processImage body, stopping before imageReady; includes image queue/copies and QPainter overlays | Window presentation, GPU/vsync and downstream handlers |
| CSV export | Scope around _append_framerates; includes first open/header and appended values | Final file close, exporter counter and signal |
| Image export | Image path, QImageWriter setup and write within the image-export block | Exporter counter and signal |
| Total frame | One driver loop iteration, including acquisition/fixture loading, analysis, trace work and requested pipeline/export/redraw | Initial setup and final finishExporting |
| End-to-end | Processing loop plus finishExporting | Process startup, metadata/configuration, final trace/timing JSON and reexport hazard operation |

The mask timer ends inside _are_equal_with_draw. It does not include Rows or Tear.
An earlier review described it as inclusive of those stages; source inspection
corrected that interpretation.

Total frame and end-to-end include work outside the individual stage timers.
Stage totals therefore do not cover every allocation, copy, observation or I/O
operation performed by the driver.

A decode timer can include an unsuccessful read attempt when EOF is reached.
The ten-frame smoke test stops at its limit and is compiled without profiling.

## Recorded lean capture

Capture: lean-profile/pipeline_csv.
Tracing: false.
Clock: steady_clock.
Units: nanoseconds.

The case submits four 20×10 fixture frames. The first frame initializes the
comparison state, leaving three pair comparisons. preview_first suppresses the
first export, leaving three CSV append calls.

These are accumulated durations for one recorded execution:

| Stage | Calls | Nanoseconds |
| --- | ---: | ---: |
| Decode | 0 | 0 |
| Grayscale | 3 | 14500 |
| Mask | 3 | 4000 |
| Rows | 3 | 87100 |
| Tear | 3 | 300 |
| FPS/frametime | 8 | 3100 |
| Image conversion | 4 | 51300 |
| Image composition | 4 | 5987300 |
| Rendering | 4 | 6667200 |
| CSV export | 3 | 215900 |
| Image export | 0 | 0 |
| Total frame | 4 | 13516400 |
| End-to-end | 1 | 13549700 |

Recorded end-to-end duration: 13.5497 ms.

These are not per-call averages, repeated benchmark statistics or complete
process-lifetime measurements. Composition/rendering operate on the configured
output image, so small analysis inputs do not imply equally small render work.

## Recorded tracing-enabled suite

The artifact contains timing records for all 82 observed-profile regression cases.
The independent audit checked stage coverage and finite, nonnegative integer
call/time values.

Totals across those separate case processes:

| Stage | Calls | Nanoseconds |
| --- | ---: | ---: |
| Decode | 0 | 0 |
| Grayscale | 2662 | 6594100 |
| Mask | 2662 | 2289100 |
| Rows | 2662 | 69446400 |
| Tear | 2662 | 538600 |
| FPS/frametime | 5480 | 1902000 |
| Image conversion | 86 | 604600 |
| Image composition | 86 | 119226300 |
| Rendering | 87 | 134662300 |
| CSV export | 12 | 878000 |
| Image export | 4 | 23035700 |
| Total frame | 2740 | 1396279300 |
| End-to-end | 82 | 1407310600 |

The extra rendering call relative to conversion/composition is consistent with
the redraw fixture.

The aggregate is not a single end-to-end application run and excludes process
startup between cases. Cases have different lengths and enabled stages.
The suite includes tracing overhead and must not be used as a performance
benchmark or compared directly with the single lean case.

## Decode zero versus decode smoke evidence

Deterministic fixture cases read packed BGR bytes directly. They do not call
VideoCaptureList, so Decode has zero calls in both fixture profiling groups.

The separate smoke test uses VideoCaptureList and recorded ten successful decoded
frames through FFMPEG. It runs oracle.exe, where profiling is compiled out.
Consequently, there is decode evidence but no measured decoder duration.

Zero calls means the stage was not exercised by that profiling capture; it does
not mean video decoding has zero cost.

## Measurement interpretation and limitations

Timers use steady_clock, whose actual resolution and scheduling effects matter
for small measurements. The tear total of 300 ns in the lean case should not be
treated as a stable estimate from repeated trials.

Timer bookkeeping adds clock reads and atomic accumulation. Its overhead was not
measured independently. Profiling-on/off semantic equality does not quantify it.

Scoped durations include some setup/destruction within their lexical scope.
Explicit stop locations exclude particular later operations. Allocation and copy
costs outside those scopes are not automatically attributed to a stage.

Stage sums are not additive end-to-end wall time:

- Total frame includes timed stages and untimed driver work.
- End-to-end contains frame processing and final export cleanup.
- Parallel calls can accumulate overlapping durations.
- Nested timers can charge the same interval more than once.

Rendering here is CPU image preparation and overlay painting. There is no
interactive GUI, display refresh, vsync or GPU presentation measurement.

The reference policy uses one OpenMP thread, disabled dynamic/nested execution
and the driver's one-thread OpenCV default. No multithread scalability benchmark
was performed.

No large-resolution benchmark, controlled repeated trial, memory/RSS benchmark
or transfer-inclusive GPU benchmark was performed.

## Implications for future approved work

The lean capture demonstrates that the instrumentation records separable stages
and that composition/rendering contribute substantially to this particular small
fixture run. It does not identify the dominant cost for real high-resolution
video analysis.

The traced suite's Rows total is larger than its Mask total, but tracing, tiny
inputs and original OpenMP overhead prevent generalizing that relationship.

Future optimization measurements should use representative identical pixel data,
repeat trials under a documented runtime configuration, separate trace capture
from performance capture and measure decoder cost independently.

Preserve the original timer boundaries when comparing results, or explicitly
version changes to them. Evaluate both stage and processing-loop durations;
do not claim a speedup from an isolated timer while ignoring displaced work.

Profiling-on/off semantic equivalence does not establish zero overhead or
quantify instrumentation cost.

Keep all regression gates and historical-defect classifications. New correctness
changes, optimization experiments and Phase C require separate authorization.
