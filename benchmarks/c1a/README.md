# Phase C1-A / Gate A1 benchmark protocol

Gate A1 defines configurations, result validation and statistical reporting only.
It does not execute TRDROP, collect measurements or implement concurrency.
All helper code uses the Python standard library. Unit-test values are synthetic;
they are not performance results, reference captures or new golden outputs.

## Frozen reference and scope

The semantic oracle remains `phase-b-windows-reference-v1`, checkpoint
`df981aaed23827e3716ab0ca59ad28e3ea9ae828`, with original source
`a0b4563a076e336863f743ec92c1ee8221f5aba6`.
Phase B comparisons, fixtures, tolerances and historical tear behavior remain
unchanged. A valid benchmark record is not evidence of semantic equivalence:
future runs must also pass the unchanged Phase B regression gates.

The recorded environment is Qt 5.15.2, MinGW/GCC 8.1.0, OpenCV 4.5.1 and
Python 3.13.15. Gate A1 introduces no dependencies or production changes.
Drivers, input generation, process sampling and execution orchestration belong
to later gates and are not supplied here.

## Versioned configuration matrix

`matrix.json` is schema version 1. Families expand as Cartesian products.
Each resolved configuration records input and output dimensions independently,
video count, rational FPS, export mode, pattern, preview, batch policy and the
full protocol. IDs are stable descriptive labels, not provenance hashes.

| Family | Class | Workload and coverage | Configurations |
| --- | --- | --- | ---: |
| mandatory | Mandatory | Headless, four resolutions, 1/2/3 videos, 60 FPS, all exports | 48 |
| fps | Exploratory | Headless, all resolutions/counts, other FPS, no export | 72 |
| analysis | Exploratory | Predecoded analysis, all resolutions/counts/FPS/patterns | 420 |
| decode | Exploratory | Decode only, all resolutions/counts/FPS | 84 |
| gui | Exploratory | GUI pipeline, all resolutions/counts, 60 FPS, preview on/off, all exports | 96 |
| scaling | Exploratory | Headless, 720p/1440p/4K input to 1080p output, all counts/exports | 36 |
| patterns | Exploratory | Headless, all resolutions/counts/exports, other patterns | 192 |
| partial | Exploratory | Explicit partial decode, all resolutions/counts, 60 FPS | 12 |
| eof | Exploratory | Explicit EOF probe, all resolutions/counts, 60 FPS | 12 |

The matrix defines 972 configurations: 48 mandatory and 924 exploratory.
Mandatory means required coverage for a complete performance report, not an
unmeasured numerical performance threshold. Exploratory families need not all
be run; any selected family/configuration must still satisfy its trial protocol.

Input axes: 1280x720, 1920x1080, 2560x1440, 3840x2160; one, two or three
independent videos; 24, 30, 60, 120, 240, 30000/1001 and 60000/1001 FPS.
Output defaults to input dimensions except the explicit scaling family.
Output dimensions denote the target composed/exported image, not decoded bytes.
Export modes: none, CSV, JPEG, CSV plus JPEG. Combined exports are proposed
benchmark coverage; Phase B did not validate a combined-export fixture.

Patterns: identical, alternating, periodic duplicates, sparse changes and
tear-heavy. The last two require deterministic future input definitions.
Input file bytes, codec, pixel format, duration and frame count must be frozen
in an input manifest before measurements; this gate does not invent those files.

Preview has three distinct states: GUI enabled, GUI disabled, or GUI absent.
Headless workloads require absent. GUI-disabled still exercises the GUI
application path; it must not be relabeled headless. Decode/analysis do not export.

## Immutable identity

Each trial requires both `matrix_sha256` and `configuration_sha256`.
Canonicalization uses Python JSON with sorted object keys, compact separators,
ASCII escaping and forbidden NaN/infinity. SHA-256 hashes the resulting ASCII
bytes. Array order is preserved. Whitespace/object-key reordering has no effect;
changing a matrix selection, protocol or resolved configuration does.

`matrix_sha256(matrix)` validates and hashes the entire canonical matrix.
`configuration_sha256(configuration)` hashes the fully resolved configuration,
including its protocol. Validation independently resolves the ID from the supplied
matrix and recomputes both hashes. A mismatch is invalid. Preserve the exact
matrix alongside results; neither an ID nor a hash alone supplies its contents.
The input manifest has a separate required SHA-256 in provenance.

## Measurement protocol

Use seven measured trials per configuration, indexed 1 through 7, after warm-up
in each trial. Warm-up batches are exactly
`max(120, 2 * ceil(input_FPS))`. The two multiples allow history initialization
over two nominal seconds; they do not introduce a new RAM buffering policy.
Discard warm-up timings/counters. Initialize a fresh application state per trial;
do not substitute reset/re-export behavior that Phase B characterized as hazardous.

Use identical measured batch/source counts, input bytes, hardware, software,
collector methods and sampling intervals across the seven trials. Fix execution
order in future orchestration, record external contention and cache policy in
the machine/storage description, and keep cold-start observations separate.
No automatic outlier deletion or hidden replacement of failed trials is permitted.
Failed, cancelled and timed-out records remain visible.

The future driver must define the measured segment before running, measure it
with a monotonic high-resolution clock, include ordered output completion and
export finalization where applicable, and exclude warm-up, setup and teardown.
No throughput result may omit outstanding export work at its stop boundary.
Stage timers can overlap or nest; do not sum them into total wall time.

The initial comparison policy fixes OpenMP and OpenCV to one thread each, with
OpenMP dynamic and nested execution disabled. Record actual configured values
and observed total process thread counts; decoder, Qt and OS threads are separate.
This establishes a controlled synchronous reference, not a scalability benchmark.
Other thread settings require a separately approved protocol version.

## Throughput, latency and exceptions

Batch throughput = measured batches / measured wall seconds.
Submitted source-frame throughput = submitted frames / measured wall seconds.
Acquired source-frame throughput = successful physical frame reads / measured
wall seconds. Analysis on already decoded pixels records acquisition as zero;
submitted analysis frames still count as work.

For completed `complete_synchronized` trials:
`submitted_source_frames = measured_batches * video_count`.
A batch contains one submitted source frame from each configured video.
Physical acquisition can exceed submission because of explicitly recorded reads,
but cannot be smaller in decode/pipeline workloads. Warm-up is excluded.

Only the explicit decode configurations `partial_decode` and `eof_probe`
are exempt from that product invariant. Record actual submitted and acquired
counts; do not manufacture complete batches for EOF or failed reads.
These workloads cannot be compared as ordinary synchronized pipeline throughput.
A completed EOF probe still needs at least one measured batch and positive time.
A probe with zero measured work is not a complete throughput trial.

Latency is an elapsed time per batch, not reciprocal throughput or source-frame
time. The schema accepts these exact boundary labels:

| Metric | Start and stop | Required workload |
| --- | --- | --- |
| acquisition | Batch read request to read return, including decode | decode |
| analysis | Analysis call entry to return, using predecoded frames | analysis |
| processing | Batch acquisition start to ordered output completion | headless and GUI pipeline |
| gui_delivery | Output delivery to paint callback | GUI pipeline |

A paint callback does not prove display presentation or GPU completion.
Acquisition includes decoding in the current synchronous API; distinguishing
decode internals from acquisition overhead needs additional instrumentation.
The Gate A1 latency schema records workload-level boundaries, not every Phase B
stage. Additional stage counters require an independently approved extension.

Complete latency coverage requires `sampling_policy: every_batch` and exactly
one sample per measured batch. `sampled_batches` is valid but protocol-partial.
Samples are integer nanoseconds, nonnegative, no larger than the measurement
window. Use nearest rank: sorted sample at `max(1, ceil(p*N/100))`, one-based.
Report p50, p95 and p99 separately within each trial; do not pool trials or average
their percentiles. Percentile zero returns the minimum. Very short samples cannot
support meaningful tail claims even though the formula is defined.

Report the median of seven per-trial throughput values. Fewer valid completed
trials can yield provisional statistics but cannot yield complete results.
Retain individual latency distributions and resource records.

## Strict trial schema

Result input is a JSON array of trial objects. All listed object keys are required,
and unknown keys are rejected except the explicitly variable latency map.
Version fields and counters require exact integer types; booleans are not numbers.
Integers are bounded by 2^63-1; NaN/infinity and duplicate JSON keys are rejected.
Input files are limited to 16 MiB and each latency series to 1,000,000 samples.
Excessive JSON nesting is rejected as a structured invalid result; recursion
errors during CLI processing also produce an invalid JSON report and exit code 1.

Top-level fields:
`schema_version, configuration_id, matrix_sha256, configuration_sha256,
trial_index, status, provenance, measurement`.

Execution status is completed, failed, cancelled or timed_out.
Provenance fields:
`phase_b_tag, phase_b_commit, frozen_source_commit, infrastructure_commit,
input_manifest_sha256, machine_id, cpu_model, physical_cores, logical_processors,
os, compiler, qt_version, opencv_version, python_version, decoder_backend,
storage_description`.
Commit IDs are lowercase 40-digit hexadecimal; SHA-256 IDs are 64 digits.
Physical cores may be null if unavailable; logical processor count is required.
Decoder backend is a per-video string list, or null for predecoded analysis.
Compiler description must identify 8.1.0. Record complete toolchain/build and
input/storage details in the associated provenance records and input manifest.
These declarations validate consistency; they are not independent binary attestation.

Measurement fields:
`warmup_batches, measured_batches, submitted_source_frames,
acquired_source_frames, wall_time_ns, latency_ns, cpu, memory, threads, exports,
allocation_copy`.
Core counters cannot be omitted. For optional/unavailable observations, use
explicit status records rather than zero placeholders.

A measured latency object has:
`status, boundary, sampling_policy, samples_ns`.
Only workload-applicable latency names may be measured.

A measured CPU object has:
`status, method, process_time_ns, available_logical_processors`.
Process CPU percent = 100 * process CPU time / wall time; it can exceed 100%.
Normalized percent divides by available logical processors, which must match
the provenance count. CPU time covers all process threads, not one analysis thread.

A measured memory object has:
`status, method, sampling_interval_ns, sample_count,
sampled_peak_private_bytes, sampled_peak_working_set_bytes,
os_peak_working_set_bytes`.
OS peak may be null; if present it cannot be below the sampled working-set peak.
Periodic samples can miss brief peaks. The future sampler must label whether the
OS peak is process-lifetime or reset to the measurement window.

A measured thread object has:
`status, method, sampling_interval_ns, sample_count,
configured_openmp_threads, configured_opencv_threads,
observed_process_threads_max, openmp_dynamic, openmp_nested`.
Observed threads are not equivalent to busy workers or configured parallelism.

A measured export object has:
`status, csv_data_rows, images, interval_ns`.
Count actual successfully finalized outputs, excluding CSV headers. CSV-only
requires zero images; JPEG-only requires zero CSV rows; each enabled output
requires a positive count for a completed trial. Export time is positive and
cannot exceed the trial window. Rates are rows/second and images/second over
the declared export interval, not frame-analysis throughput.
Future collectors must specify whether that interval includes formatting,
composition, encoding, file writes and final flush. Counts do not replace
Phase B export inventory/semantic validation.

Allocation/copy accounting has measured or estimated status and:
`method, allocations, allocation_bytes, copy_operations, copy_bytes`.
Measured values require all four counters; estimates may use null for unknown
counters but need at least one known estimate. Label explicit known copies as
estimates; they do not represent complete OpenCV/Qt/decoder allocation activity.
This metric is exploratory and is not required for initial completeness.

Any unavailable metric is exactly `{"status":"unavailable","reason":"..."}`.
A non-applicable metric is exactly
`{"status":"not_applicable","reason":"..."}` and is accepted only when the
workload does not require it, such as exports disabled. A required missing latency
series or unavailable required metric yields partial data, not fabricated values.
Omitting a required structural field entirely is malformed and invalid.

## Completeness and deterministic reports

Invalid means malformed data, identity mismatch, invalid counters, duplicate
trial indices or incompatible comparable-trial provenance/collection policies.
Invalid records are reported, never silently discarded to improve a result.

Partial means structurally valid records with fewer than seven completed trials,
unavailable required measurements, sampled latency coverage or missing mandatory
configurations. Complete means seven valid comparable completed trials with every
workload-required measurement available.

Every workload requires CPU, memory, threads and its latency fields.
Exporting workloads additionally require measured exports. Allocation/copy
estimates do not prevent completeness and remain clearly labeled.
Group reports compute two independent indicators:

- Statistical completeness requires exactly seven valid, comparable completed trials.
- Measurement/protocol completeness requires all workload-required measurements
  to be available and conform to their validated measurement rules in every supplied trial.
  It does not depend on trial count or execution status.

Both indicators must be complete for the group's overall classification to be complete.
Six conforming completed trials are statistically partial but protocol-complete;
seven completed trials with unavailable required measurements are statistically
complete but protocol-partial. Failed, cancelled and timed-out trials never count
toward statistical completeness; their measurements are not automatically marked
unavailable solely because of execution status.
Provisional statistics remain available for fewer than seven completed trials,
with statistical completeness and overall classification explicitly partial.

Completed trials with measured exports must agree on both CSV data-row and image
counts. Inconsistent known counts make the group invalid. Unavailable export
measurements remain unavailable and protocol-partial; no expected counts are invented.
The whole report is complete only when all mandatory configurations and any
included exploratory configurations are complete.

`report.py` validates, aggregates and emits sorted deterministic JSON to stdout.
It does not run processes, write files, access the network or generate measurements.
CLI, for future separately authorized use:
`python -B benchmarks/c1a/report.py benchmarks/c1a/matrix.json trials.json`.
Exit codes: 0 complete, 1 invalid, 2 partial. No performance thresholds are set.
Input ordering does not change valid report contents; errors retain input record
indices for diagnosis. No timestamps are synthesized.

## Tests ready for separate authorization

`tests/c1a/test_protocol.py` contains synthetic unit tests for strict schemas,
invalid combinations, canonical identities, hash mismatches, rational warm-up,
workload-dependent requirements, source-frame invariants and exceptions,
unavailable metrics, export mode/count validation, nearest-rank percentiles,
seven-trial aggregation, incomplete/noncompleted trials, incompatible provenance,
mandatory/exploratory counts, independent canonical SHA-256 vectors, independent
completeness indicators, export-count comparability, JSON and latency size limits,
empty arrays, invalid indices, failed/timed-out trials, malformed nested fields,
even-count provisional medians, CLI exit codes, deterministic serialization and
malformed/deeply nested JSON with structured recursion-error handling.

The tests import the new reporting helper when run. They execute no TRDROP
binaries, read no credentials, perform no network access and create no fixtures,
goldens or output files. Mocked streams exercise malformed JSON loading.
Future separately authorized test command:
`python -B -m unittest discover -s tests/c1a -p test_protocol.py -v`.
Gate A1 creation approval does not authorize executing this command.

## Remaining gates and unresolved measurements

Before collection, approve deterministic encoded inputs and input manifests,
codec/pixel format, measured duration/batch count, cache policy, trial ordering,
machine power/affinity policy, sampling tools and precise export interval scope.
Longer workloads are needed for defensible p95/p99 and memory peaks.
No unavailable measurement may be replaced with a guessed value.

Separate decode/acquisition timing, conversion, composition, rendering, allocation
and copy costs need future driver/collector or instrumentation work. Phase B's
predecoded lean captures cannot measure real multi-video decode throughput.
No GUI affinity, pause/reset/cancellation, asynchronous ownership, concurrency
correctness or scaling test is implemented by this gate.

Gate A2 must be separately authorized. Preserve the frozen baseline and existing
regression oracle; do not regenerate golden outputs or silently fix legacy defects.
