# TRDROP — Phase 0 technical baseline

Audit date: 2026-09-05. Source baseline: `a0b4563a076e336863f743ec92c1ee8221f5aba6`.
Local origin: `https://github.com/Redcomet73/trdrop.git`. The requested upstream is
`https://github.com/cirquit/trdrop`; no upstream remote is configured locally.
This audit describes the local checkout, not an asserted comparison with current upstream.

## Scope and evidence

Phase 0 only: repository inspection, behavioral specification, optimization candidates,
and regression design. No production code, algorithms, build files, or workflows changed.
No benchmark, executable, golden analysis output, or Windows artifact was generated.
“Bottleneck” below means a source-backed source of work worth profiling, not a measured
dominant cost or a promised speedup. Function names and paths refer to the baseline above.

Inspection covered the tracked source/header tree, QML/JS and resources, project file,
workflow, documentation/history, installer metadata and asset inventory. Binary media,
fonts and images were inventoried; the sample video was hashed, not decoded or analyzed.
There are no existing test targets, benchmark runners, golden outputs, CMakeLists.txt,
vendored dependency sources, CUDA kernels or compute shaders in the tracked tree.

The host is macOS/Darwin ARM64. `command -v` did not find `qmake`, `cmake`,
`pkg-config`, or `ffprobe` on this session's PATH. This is not proof they are absent
elsewhere. The Windows MinGW/Qt deployment build cannot be executed natively here;
no application build or runtime correctness/performance test was attempted.

Local static verification performed: all 80 baseline tracked files were readable;
all 15 qml.qrc resource paths exist; tracked XML files parsed successfully using Python's
ElementTree; the demonstration video's SHA-256 was computed; audit whitespace was checked.
These checks do not validate QML execution, compilation, codecs or numerical results.

## Repository map and architecture

| Location | Responsibility |
| --- | --- |
| `trdrop/src/main.cpp` | Sole application translation unit; QApplication, QML engine, fonts, models, object construction and signal wiring |
| `trdrop/headers/cpp_interface/videocapturelist.h` | OpenCV capture ownership, sequential reads, counters, metadata and restart |
| `trdrop/headers/cpp_interface/frameprocessing.h` | Active comparison, tear inference, FPS ring and frametime calculation, implemented inline |
| `trdrop/headers/cpp_interface/{frameratemodel,frametimemodel}.h` | Three current values and three 1,200-sample history deques per model |
| `trdrop/headers/cpp_interface/{framerateplot,frametimeplot,tearmodel,teardata}.h` | QPainter plots, retained/fading tear lines and coordinate scaling |
| `trdrop/headers/cpp_interface/{framerateoptions,tearoptions}.h` | Per-video options; FPS text drawing also lives in FramerateOptions |
| Other `cpp_interface` value headers | Checkbox, color, numeric, text/font, file, resolution and image-format values |
| `trdrop/headers/qml_interface/` | QObject pipeline adapters; conversion/composition/render/export; QQuickPaintedItem viewer |
| `trdrop/headers/qml_models/` | Seven QAbstractListModel adapters: file, general, FPS, tear, resolution, image format, export; shared mutable options |
| `trdrop/qml/` | Main Material window, file selection/reordering, options, export controls, preview and startup UI |
| `trdrop/utils.js`, `qml.qrc`, `fonts/`, `images/` | URL/path helpers, rounding, resource manifest and bundled presentation assets |
| `trdrop/trdrop.pro` | qmake, C++11, Qt/OpenCV linkage, OpenMP flags, Windows icon |
| `.github/workflows/ci-win64.yml` | Only CI workflow: Windows x64 build, packaging, artifact and release upload |
| `installer-template/` | Qt Installer Framework config/package XML and MIT license copies; version 1.1.1, package date 2021-01-06 |
| Root Markdown, LICENSE, `.gitignore` | README, development/deployment guidance, historical notes, MIT license, generated-file exclusions |
| Root `images/`, `videos/` | Logos, historical pipeline PNG/XML and one demonstration MP4 |

The old `deltaprocessing.h`, `tearprocessing.h` and their QML wrappers are inactive:
not wired by main and not listed in the project's HEADERS. They reference missing
`fpsoptions.h`/old `FPSOptions`; the old tear implementation also uses obsolete TearData
methods. Do not mistake their OpenMP loops for additional stages in the live pipeline.
Several QML prototypes are not in qml.qrc: AddFilesDialog, FileModel, FpsOptionsModel,
FileManagementActionsModel, StartupText and the empty MaterialIconButton. The historical
pipeline diagram and README are not authoritative descriptions of the active algorithm.

## Execution flow and decoding

1. `FileWindow.qml::onUpdateFileItemPaths` opens the ordered paths, resets the analysis
   using capture FPS metadata, updates option/model rows, and immediately reads a preview
   frame. File changes can occur through browsing, removal or visual reordering.
2. `VideoCaptureList::open_videos` constructs `cv::VideoCapture(path.toStdString())`.
   No backend is explicitly selected, no `isOpened()` validation is performed, and no
   explicit hardware decoder or decoder-thread configuration is present. Windows CI
   packages `opencv_videoio_ffmpeg451_64.dll`; that establishes availability intent,
   not proof that FFmpeg is selected for every input. Record the actual backend at runtime.
3. `populate_next_frames` calls `read(frame_list[i])` serially for each video (maximum
   three through the application). Each successful read increments its source counter.
   It stops on the first failed read, so earlier videos can have one extra decoded frame
   that never reaches analysis. EOF and decoding error use the same false return path.
4. `VideoCaptureListQML::readNextFrames` emits framesReady synchronously. On failure it
   seeks all captures to frame zero, clears capture counters and emits finishedProcessing.
   Seek success is not checked. Progress divides successful reads by CAP_PROP_FRAME_COUNT;
   the “shortest” progress is the maximum fraction across videos, without a zero guard.
5. Direct connections in main run: capture → FrameProcessingQML → ImageConverterQML →
   ImageComposerQML → RendererQML → ExporterQML. The adapter always calculates FPS,
   frametime and tears, even when their visualization switches are disabled.
6. Analysis publishes either original BGR frames or binary three-channel delta frames.
   Conversion copies into RGB888 QImages and swaps channels; composition scales/crops;
   renderer delays images for centered plots and paints overlays; exporter writes images
   and/or CSV, then emits imageReady.
7. `TrdropContent.qml` explicitly calls `gc()` on every image and passes it to ViewerQML.
   `setImage` optionally scales the preview but always calls update(). `paint()` emits
   requestNextImages; the QML handler requests another read if exporting. Thus even
   preview-disabled export depends on the viewer repaint/event cycle. `startExporting`
   triggers the first read through the exporter signal, not a free-running worker loop.

No decode/analysis queue, frame batching, time-stamp synchronization between inputs,
or asynchronous image writer exists. Inputs advance in lockstep by frame index despite
potentially different recorded rates. Source pixels are analyzed before display scaling.

## Exact analysis semantics to preserve

Evidence: `frameprocessing.h::{check_for_difference,_are_equal_with_draw,
_get_frame_difference,_get_max_tear_percentage,_calculate_framerate,_calculate_frametime}`.

- First call caches full frames and returns the originals; no difference decision is
  inserted. Histories get initial zero measurements through the QML adapter.
- Both previous and current frames are converted with `cv::COLOR_BGRA2GRAY`, although
  downstream code asserts CV_8UC3 and writes Vec3b. Preserve the exact OpenCV conversion
  behavior/rounding on actual three-channel inputs; do not substitute decoded luma or
  a different grayscale formula without equivalence evidence.
- A pixel changes iff `max(grayA, grayB) - min(grayA, grayB) > pixel_difference`.
  Equality at the threshold is unchanged. The GUI range is 0–255, default 0.
  Output has all three bytes 255 or all three bytes zero. Color changes with equal
  converted grayscale are invisible to the algorithm.
- A row's score is count(pixels whose **all three** channels are nonzero) / width.
  For the generated binary mask this is simply the changed-pixel fraction.
- A tear boundary is adjacent rows where one score is exactly zero and the other is
  at least 0.1. This completeness constant is hardcoded, not the user dismissal option.
  Boundaries store `(row-1,row,video_index,video_count,original_height)`.
- For each boundary, scan away into the contiguous positive-score region and find the
  maximum such run length / height. If this fraction is below the user dismissal
  percentage / 100, return 1 when a changed pixel was found, otherwise 0. If it meets
  the threshold, return `1 - maximum_fraction`. Default dismissal is 10%; the QML
  model setter converts through `toUInt()`, even though the stored option is double.
  Tear records are emitted even when the fractional contribution is dismissed.
- Without a tear, return 1 for detected change, else 0. The `found_different_pixel`
  update only examines row A, excluding the last row. Therefore a sparse last-row-only
  change below completeness can return 0; a height-one image always returns 0 here.
  These are source-derived edge cases, not validated runtime observations.
- For each video, a zero-initialized ring has length `quint8(ceil(CAP_PROP_FPS))`.
  Each comparison overwrites one slot and advances the index modulo ring length.
  FPS is the sum of the entire ring, including fractional tear contributions, with
  no warm-up normalization. GUI “analysis range” controls plot history, not this ring.
- Frametime returns zero if ring length is zero or its sum is below 2. Otherwise it
  scans backward from the last-written slot, finds the latest positive contribution,
  then counts backward to the previous positive contribution (including that slot).
  Return `count / ring_length * 1000` milliseconds. Fractional positives are treated
  as positive events, not proportional durations. It measures a prior completed
  interval; it is not the growing duration of the currently held duplicate frame.
  Durations extending outside the ring can consequently yield zero.
- There is no cumulative unique-frame total or exported duplicate decision stream.
  Binary changed decisions and sum of fractional contributions must be separate
  reference fields; neither should be silently named a physical unique-frame count.

## Threading analysis and correctness hazards

`frameprocessing.h` has OpenMP at lines 63 (videos), 382 (rows), and 394 (columns with
a double reduction). The column loop is invoked once per row inside the row loop,
itself inside the video loop. No runtime nesting/thread-budget policy is set in source.
With nested parallelism inactive, the inner teams serialize: only up to three video
iterations provide useful outer parallelism, and one video gets only one useful outer
iteration. With nesting active, team creation and oversubscription are risks. Neither
configuration establishes good single-video scaling. OpenCV/decoder internal workers
may also contribute; their actual build configuration and thread counts are unknown.

More serious than performance: `_tear_rows` is one shared vector, cleared once per batch
and pushed by multiple video iterations without synchronization. `_get_max_tear_percentage`
reads that shared vector concurrently and does not filter by video. This can race/reallocate,
mix tear indices across videos and index outside a shorter video's row vector. Even with
one OpenMP thread, later videos can read earlier videos' tears. Equal heights avoid that
specific bounds mismatch but do not make the results independent. Parallel writes via
non-const QList access also deserve a Qt implicit-sharing/ownership review.

`main.cpp` constructs pipeline objects on the GUI thread, with direct stage connections.
There is no QThread, moveToThread, QtConcurrent or std::thread worker implementation.
Opening/reading captures, analysis orchestration, image transforms, QPainter composition,
CSV and image writes therefore execute synchronously in the caller's pipeline context
and normally the GUI event path. Qt Quick can have its own rendering thread; exact
paint-to-QML signal scheduling needs Windows tracing. Do not assert that Qt or codecs
are single-threaded merely because application workers are absent. The current design
blocks its caller until each OpenMP region and downstream stage completes.

Further baseline risks:

- `FrameProcessingQML::processFrames` appends the entire tear list inside the three-entry
  FPS-model loop, so each batch's tears are added three times, even for a single video.
- TearModel removes tears only while drawing them. Disabling tear visualization while
  analysis keeps appending can grow retained tear memory without bound.
- `FrameProcessing::reset_state` does not clear `_tear_rows`; the first post-reset call
  can expose stale tears because the first-frame branch does not clear them either.
- Invalid/zero FPS with a nonempty decoded frame can leave an empty ring later indexed
  by check_for_difference. Nonfinite/out-of-range metadata is not validated before
  floating-to-quint8 conversion; do not assume a defined wraparound for values above 255.
- Resolution/type changes, invalid paths, read/seek failures and zero frame counts have
  no robust validation contract. End-of-input and state reset need explicit test coverage.
- Renderer redraw calls processImage and can advance centering/tear rendering state;
  while exporting, redraw can also reach the exporter without a newly decoded frame.
- Export finish clears `_file_item_list` but retains `_active_video_count`; a subsequent
  CSV export without a file-list update can index cleared names. Treat as a defect case.

These defects must not be silently repaired as “optimizations.” Undefined/racy behavior
cannot be an exact portable golden contract; characterize it separately and approve any
correctness fixes with distinct expectations and commits.

## Bottlenecks and memory/copy analysis

| Evidence | Work and likely impact | Future measurement |
| --- | --- | --- |
| `_are_equal_with_draw` | Two grayscale conversions per pair; scalar nested row/column loop; repeated Mat::at reads, max/min and three output writes | Grayscale and mask time separately; generated assembly; pixels/s |
| `check_for_difference`, `_cache_framelist` | Clone input to output before overwriting every pixel; clone returned difference again; clone every current BGR frame for next comparison | Allocation counts, copy bytes and peak RSS |
| `_get_row_differences`, `_get_row_difference` | Second full mask scan, three channel accesses/pixel and nested OpenMP reduction per row | Row-reduction time, team overhead and scaling |
| `_get_max_tear_percentage` | Rescans contiguous changed runs from boundaries (often from both ends); shared vector adds cross-video scans | Rows visited and tear-heavy test timings; not an asserted quadratic single-video cost |
| `VideoCaptureList::populate_next_frames` and direct pipeline | Serial reads, no overlap with comparison or file writing | Decode-only vs analysis-only vs full-export wall time |
| `ImageConverterQML::_process_frame_to_image` | Same-size cv::resize copies into a reusable QImage buffer, then in-place RGB/BGR swap | Conversion and copy cost; no claim that cv::Mat view creation copies pixels |
| `ImageComposerQML` | Multi-input full-width scaled images, copied central crops, newly allocated/filled composite and drawing | Scale/crop/compose timing per output resolution |
| `RendererQML::{processImage,_get_next_image}` | Deque front `.copy()`, returned image `.copy()`, redraw cache `.copy()`; front is copied even when centering is disabled | Image copy counts and centering memory |
| History getters, plot `_get_max_*`, FPS text | History deques returned by value; repeated 1,200-element copies/max scans, including repeated axis-label and text drawing requests | Render-only profile; smaller priority than full-image passes until measured |
| Exporter and TrdropContent/Viewer | Synchronous image compression/disk I/O, per-frame QTextStream, per-frame JS gc(), smooth preview scaling and repaint pacing | CSV-only/image-only, preview on/off, storage and event-loop latency |

For N = width × height CV_8UC3 pixels, the three explicit analysis clones copy
approximately 9N payload bytes per comparison (18N read+write traffic), excluding
conversion, mask writes/scan, decoder and GUI work. Two grayscale temporaries add 2N
bytes of image storage. This is a source-derived byte accounting, not a measurement;
allocator/stride overhead and overlapping lifetimes change actual peak memory.
Mat list returns and Mat headers are reference-counted shallow copies, not extra
full-image copies. The previous-frame clone currently protects against capture-buffer
reuse, so removing it requires a buffer ownership design. QImage is implicitly shared;
explicit `.copy()` is deep, while ordinary assignment may defer copies until writes.

The renderer retains images even with centering disabled. Its constructor holds 30
placeholders; reshape uses half the plot range (default range 360, hence 180 after
reshape; GUI maximum 1200, hence 600). At 3840×2160 RGB888, 180 independent images
represent about 4.48 GB decimal of pixel payload; 600 represent about 14.93 GB. These
are capacity estimates, not measured allocations; null/shared fillers cost less.

The active pixel loops are row-major, so there is no demonstrated strided column-major
traversal. Cache concerns are repeated full-frame passes, three-byte masks, concurrent
video working sets and retained images. Mat::at is not proof of release bounds-check
overhead: compiler inlining/vectorization must be examined before attributing cost.

## CPU optimization candidates (future only)

1. **Best first kernel candidate:** retain one-channel grayscale state, use OpenCV
   `absdiff` plus strict `compare(..., CMP_GT)`/binary threshold and row counts/reduction.
   Keep a one-channel binary mask; expand to three channels only for delta presentation.
   Reuse destination storage. This targets both scalar work and full-frame traffic.
   Preserve conversion rounding, threshold boundaries, row fractions and legacy edge behavior.
2. Compare that primitive chain with a fused row-pointer loop producing exact integer
   row counts and an optional mask. Respect Mat step, unaligned starts, odd widths and
   tails; don't require continuous input. Cache grayscale without changing the source
   frame shown to the user. Test runtime option changes when reusing derived state.
3. Use one parallel layer over coarse row ranges (`cv::parallel_for_` OR a restructured
   OpenMP loop), with private per-video tear outputs and an ordered merge. Avoid per-row
   column teams. Establish an explicit combined OpenCV/OpenMP/decoder thread budget.
4. SIMD-friendly unsigned-byte absolute differences, comparisons and integer counts
   are candidates for compiler vectorization/OpenCV dispatch first. AVX2 is a possible
   x64 specialization; AVX-512 only after target capability, bandwidth and clock behavior
   measurements. AVX alone is less attractive for byte-integer kernels. Never globally
   require these ISAs for distributed binaries: runtime dispatch and scalar fallback,
   including ARM portability, are necessary. No existing intrinsics/ISA flags were found.
5. After equivalence is established, use bounded owned buffers for decode/analysis overlap,
   move long work off the GUI thread and throttle preview independently. Preserve frame
   ordering, cancellation, EOF, option snapshots and writer backpressure. Qt models must
   remain safely owned; just moving existing shared objects to a worker is insufficient.
6. Remove redundant render/conversion copies and repeated history scans. A BGR-capable
   display format or direct conversion into the final buffer may avoid a swap/pass;
   verify Qt format support and painter behavior. Avoid computing display products in a
   future analysis-only mode, but retain numerical analysis when visualization is off.

Profile each stage using release builds and monotonic timing before choosing priorities.
Use fixed decoded-frame inputs for kernel comparisons and separate real-video decode
and full-export runs. Record warm-up, at least five repeats, median and spread, hardware,
resolution, storage, thread counts, preview/export options and peak RSS. Measure 1/2/4/8
threads where available, one versus three videos, and nested parallelism explicitly.

## GPU opportunities (future only)

No active GpuMat, UMat, CUDA, OpenCL or DirectX compute use was found. Linking OpenCV
G-API/DNN libraries or Qt's graphics runtime does not mean video analysis uses the GPU.

The most promising GPU unit is grayscale → strict difference mask → per-row integer
counts, retaining previous/current grayscale on device and reading back only O(height)
counts. Keep the small, stateful FPS/frametime/tear interpretation on CPU initially.
This is most plausible for large frames and repeated processing, especially if frames
are already resident on device. For CPU-decoded frames, include upload, readback, kernel
launch, synchronization and required display/export downloads in the comparison.

| Backend | Proposed scope | Tradeoffs / adoption gate |
| --- | --- | --- |
| CUDA | GpuMat primitives or fused mask/count kernel, later asynchronous transfers/optional hardware decode | NVIDIA-only deployment; compatible OpenCV CUDA build/toolchain needed; exact grayscale rounding and end-to-end transfer cost must pass tests |
| OpenCL / OpenCV T-API | UMat conversion/difference/threshold chain, then row reduction or custom kernel | Broader device option, but operations may fall back to CPU; confirm actual execution, avoid repeated Mat mappings and test vendor-specific rounding |
| DirectX 12 Compute | HLSL byte/int grayscale/diff and row reductions, upload/readback buffers | Windows integration possibility; largest new backend surface: device/resource management, descriptors, queues, fences and shader compilation; current Qt/OpenCV CPU images provide no existing zero-copy route |

OpenCV documents UMat dispatch and possible CPU fallback in its
[OpenCL optimization guide](https://github.com/opencv/opencv/wiki/OpenCL-optimizations).
Microsoft's [D3D12 component guide](https://learn.microsoft.com/en-us/windows/win32/direct3d12/creating-a-basic-direct3d-12-component)
documents the explicit device/queue/resource infrastructure. The rankings above are
engineering inferences from TRDROP's data flow, not measured backend results.
Hardware decode is a separate experiment: pixel format, color matrix/range and codec
rounding can change discrete decisions at threshold zero. It must not be mixed into
the first comparison-kernel optimization. Keep a CPU fallback and report backend choice.

## Windows build assessment

The application uses **qmake**, not CMake. `trdrop.pro` requests C++11 and Qt Quick,
Quick Controls 2, Widgets and Multimedia. `DEVELOPMENT.md` specifies **Qt 5.15.2 and
MinGW GCC 8.1.0 x64** (`mingw810_64`); OpenCV **4.5.1** is built separately with
CMake/MinGW Makefiles. The project hardcodes `451` library suffixes and
`OpenCV_DIR\build_64\install\x64\mingw\lib`. Unix linkage assumes `/usr/local`
OpenCV4 paths. OpenMP uses unconditional GCC `-fopenmp` compile/link flags, unsuitable
as-is for MSVC and not a portable macOS setup. The project lists many unused OpenCV
modules; live operations principally need core, imgproc and videoio, with Qt doing
image export. Review linkage before removing any deployment DLL.

Windows-specific material is concentrated in qmake paths/icon, PowerShell CI, DLL
deployment and installer metadata. `utils.js::urlToPath` handles drive-letter URLs;
QML gives Linux windows SubWindow flags and other platforms Dialog flags. There is
no active Win32 analysis API, DirectX compute implementation or platform-specific
pixel kernel. Non-ASCII Windows paths through `toStdString()` merit runtime tests.

CMake would improve dependency discovery, per-target flags, test targets, presets and
optional CUDA integration; it is beneficial, not itself a CUDA requirement. NVIDIA's
[Windows CUDA compiler support table](https://docs.nvidia.com/cuda/cuda-installation-guide-microsoft-windows/index.html)
lists MSVC toolchains, not MinGW. For conventional native CUDA C++ integration, plan
a compatible MSVC x64 Qt/OpenCV/toolkit set, rebuilding dependencies consistently;
do not link existing MinGW C++ binaries into that build. A separate DLL with a narrow
C ABI is an alternative boundary, not a reason to assume MinGW supports nvcc host
compilation. Choose the exact toolkit/compiler pair later; a Qt major-version upgrade
is not required merely for CUDA and would add unrelated QML migration risk.

## CI assessment and artifact provenance

The single workflow triggers on pushes and pull requests on `windows-latest`:

1. Checkout (`actions/checkout@v2`), derive seven-character SHA, set Qt 5.15.2/OpenCV 4.5.1.
2. Cache `C:\build_temp` objects/generated files and `C:\Qt` with fixed OS-only keys
   (`actions/cache@v1`); restore object files into release when available.
3. Download third-party precompiled OpenCV from `illusion0001/opencv-build` GitHub release
   4.5.1; install Qt `win64_mingw81` using `jurplel/install-qt-action@v2` plus IFW/Creator tools.
4. Run `qmake -o Makefile trdrop\trdrop.pro -spec win32-g++ "CONFIG+=qtquickcompiler"
   "OBJECTS_DIR=C:\build_temp" "MOC_DIR=C:\build_temp"`, then `mingw32-make -f Makefile.Release`.
5. Copy GCC/OpenMP runtime DLLs from `C:\msys64\mingw64\bin`, four OpenCV module DLLs
   plus the FFmpeg videoio plugin, and run windeployqt with the repository QML directory.
6. Remove selected Qt plugins/modules and graphics fallback DLLs; create
   `trdrop-release-<short-sha>.7z` using LZMA2 level 9.
7. Upload **release/** contents as an Actions artifact, not the .7z, with 90-day retention.
   For non-PR events, create a GitHub release at the full triggering SHA and attach the .7z.
   The installer-template is not built by this workflow.

This describes the configured artifact recipe, **not a currently verified reproducible
build**. There are no build/run logs or artifacts from this audit. Specific concerns:

- `windows-latest`, action tags, MSYS2 runtime DLLs and compiler resolution through PATH
  can drift. Qt arch identifies the intended GCC family, but the actual invoked GCC
  version and copied runtime compatibility are not asserted by the workflow.
- Fixed cache keys omit source, header, toolchain, Qt/OpenCV versions and build flags;
  stale objects/generated files can undermine clean-build provenance. Wildcard restore,
  cleanup and Move-Item assumptions need a fresh and cached run.
- OpenCV archive contents/checksum/build configuration and bundled FFmpeg provenance
  are not pinned or verified in-tree. Download availability was not tested here.
- Artifact action v2 is retired on GitHub.com, so the upload step requires modernization
  before relying on a new run: [GitHub retirement notice](https://github.blog/changelog/2024-02-13-deprecation-notice-v1-and-v2-of-the-artifact-actions/).
  Cache v1 and other old actions also require compatibility review. No workflow changed here.
- No numerical tests, GUI launch/decode smoke test, dependency manifest, binary hash,
  explicit token permissions or signing step. `gh release create` needs appropriate
  repository permissions and can conflict on reruns of the same short-SHA tag.
- Removing graphics fallback DLLs/plugins may affect clean PCs, remote sessions and
  systems without expected graphics drivers. Verify packaged TIFF/JPEG and QML loading.

Future reproducibility work: pin runner/toolchain/dependency versions and checksums,
use clean isolated builds for reference releases, modern supported actions pinned to
commits, explicit permissions, upload dependency/build manifests and full source SHA,
and smoke-test the downloaded artifact on a clean Windows VM. Demonstrate repeatable
functional outputs first; byte-identical PE/archive output requires additional control
of timestamps, generated paths and packaging metadata and is not currently established.

## Regression/reference testing plan — prerequisite to optimization

No supporting executable scaffolding was added: without the reference toolchain it
would be unvalidated and could falsely imply a captured baseline. The plan below is
the required next verification work, not a claim of tests already passing.

### Freeze provenance and separate layers

Keep baseline commit `a0b4563a076e336863f743ec92c1ee8221f5aba6` immutable and build it
in a separate clean checkout on Windows. Archive source SHA, compiler/qmake versions,
flags, dependency hashes, `cv::getBuildInformation()`, actual video backend, OpenCV
thread count, OpenMP environment (threads/dynamic/nesting), OS/CPU/GPU/driver, locale,
all analysis/display/export options and input SHA-256. Set colors/fonts explicitly
because FramerateOptionsModel seeds random colors from time.

1. **Algorithm layer:** a small separately built driver instantiates the unchanged
   FrameProcessing and option types, calls reset_state then check_for_difference once
   per deterministic CV_8UC3 input frame, and records public FPS/frametime/tear outputs
   plus returned delta bytes. It needs Qt because the headers include Qt/model types.
   Ensure original symbols are called; a Python reimplementation is not the oracle.
2. **Decode layer:** use unchanged VideoCaptureList separately to record metadata,
   every successful read index/hash/type/size and which complete batches reach analysis.
   Hash packed logical pixel rows, excluding padding. Store small decoded BGR fixtures
   to compare kernels with identical bytes independent of codecs or hardware decoders.
3. **GUI/export layer:** exercise the original application from file load through export,
   including preview consumption, pause/resume, EOF, re-export, centering and redraw.
   Record raw CSV/logs and image sequence count/names. Compare displayed delayed images
   separately from current CSV metrics; do not align them by filename alone.

For internal decisions not directly exposed, prefer a test-only observer in a separate
reference build, subject to review before any production edit. Alternatively a driver
can reconstruct per-pair ring contribution from consecutive FPS sums and its ring history:
`new = fps_now - fps_previous + overwritten_contribution`, checking reconstruction
drift and tagging this as derived. The first frame has no decision. An observed exact
internal stream is preferable before accepting optimized-backend equivalence.

### Record schema and equality rules

Manifest: schema version, source/toolchain/dependency provenance, case id, fixture hash,
input ordering, raw FPS and effective ring length, pixel threshold, dismissal percentage,
hardcoded completeness 0.1, option changes with frame indices and thread/backend policy.

Per source/video: reported CAP_PROP_FRAME_COUNT; actual successful reads; submitted
analysis frames; first/last source indices; exported rows. Per pair: source frame index,
previous-frame index, comparison availability, binary mask/hash, integer changed count
per row, ordered tear `(video,rowA,rowB)` list, fractional contribution, zero/nonzero
decision, FPS and frametime_ms. Summary: compared pairs, duplicate/nonduplicate counts
and sum of fractional contributions. First source frame is recorded separately;
optionally report `1 + nonduplicate_pairs` only as a clearly labeled derived event count
for nonempty inputs, not an existing TRDROP output or count of distinct images globally.

| Result | Acceptance rule |
| --- | --- |
| Source counts/order, duplicate decisions, thresholds, changed-pixel/row counts, tear indices and multiplicity | Exact integer/discrete equality; no tolerance or sorting that hides lost/duplicated tear records |
| Grayscale and delta bytes from identical decoded input | Exact byte/hash match; one-byte grayscale changes can flip threshold decisions |
| Fractional contributions, row fractions, FPS, frametime_ms | `abs(actual-reference) <= 1e-9 + 1e-12 * abs(reference)` in the field's own units; reject unexpected NaN/Inf; discrete branch outcomes still exact |
| Raw original CSV/log output on the same frozen setup | Exact bytes, including header, ordering, append behavior and diagnostics; store UTF-8/line-ending provenance |
| CSV across platforms/toolchains | Normalize CRLF to LF only; exact headers/row/column counts and compare parsed numeric fields with the above tolerance; report textual differences separately |
| Rendered artifacts | Exact decoded image pixels only on frozen Qt/font/render setup; separate review across graphics/font stacks, never relax numerical criteria because rendering differs |

Capture numerical reference fields with 17 significant digits. CSV alone uses default
QTextStream precision and cannot prove full double precision; do not compare its rounded
values directly to high-precision traces. Lossy JPEG bytes are not the kernel oracle.
Logs may contain paths/environment details: retain raw originals and explicitly list any
normalization, rather than dropping arbitrary lines. Timing logs are not semantic goldens.

### Fixture matrix

- Empty/invalid input, one frame, two frames; identical and fully changed images;
  periodic repeats (e.g. A A B B), alternating and long holds exceeding the ring;
  enough frames for multiple wraps. Fractional rates 29.97/59.94, rates 1/24/30/60/120/240,
  and invalid 0/nonfinite/>255 metadata as expected-defect/validation cases.
- Grayscale levels at threshold-1/threshold/threshold+1 for thresholds 0/1/5/255;
  saturated byte differences; equal-gray different-color pairs; sparse noise.
- Top/bottom single changed pixel/row; heights 1 and 2; widths below 10 and odd widths;
  changed row fractions just below/exactly/above 0.1; all-black rows, isolated positive
  runs, multiple tear boundaries, complementing tear sequences; dismissal below/equal/
  above run-height fraction including 0/10/100 percent.
- Contiguous and padded/non-contiguous ROI Mats with identical logical bytes; 720p,
  1080p and 4K. Wrong channel type/dimension changes belong to validation/defect tests.
- One/two/three inputs, differing lengths/FPS/resolutions, reordered inputs, failed reads
  in each slot, repeat reset/restart/export, changed thresholds mid-run, preview on/off,
  delta on/off, centered plots on/off, CSV-only and image export, redraw during export.

Use generated uncompressed or lossless source fixtures plus their decoded-pixel hashes;
store generator seed/parameters and independently specified small-case expectations.
Include real raw capture examples with known motion/tears after obtaining them. The
existing `videos/2019-07-02-first-fps-analysis.mp4` is a historical rendered demonstration,
not labeled raw truth. Its SHA-256 is
`1f878fc33d2fa8a611b2f278b063b6d076a5057c235294a9a8551f8deffb9795`;
use it only as a smoke case until decoded and characterized.

### Nondeterminism, failures and gate

First capture repeated single-video references with OMP_NUM_THREADS=1 and controlled
OpenCV threads. Also capture multi-video serial behavior as legacy behavior, including
cross-video contamination. Repeat with 2/4/8 threads and nested execution on/off in
separate processes. Crashes, timeouts and unstable multi-video tears are defect evidence,
not a reference to average or bless. A stable serial oracle does not remove the logical
cross-video bug. Add bounds/race diagnostics where the compiler supports them; gate on
deterministic valid cases and explicitly quarantine known-invalid cases with reasons.

Before an optimization is merged: baseline and candidate must consume identical decoded
fixtures, pass all applicable exact/tolerance checks, preserve end-to-end CSV/source-index
mapping and pass clean Windows package smoke tests. Report the first differing field/frame,
not only aggregate FPS. Correctness changes need a separate approved expected-result set.
Performance claims require measured stage and end-to-end improvement with no unbounded
memory growth. Golden files may only be generated by an identified reference executable;
never automatically overwrite them when a comparison fails.

## Proposed phases and unresolved verification

| Phase | Deliverable / gate |
| --- | --- |
| Phase 0 (this commit) | Audit and reference design; no production or CI changes |
| Phase B, only after approval | Restore a reproducible Windows reference build/CI, implement minimal driver and fixtures, capture originals, profile stages and characterize correctness defects |
| Phase C | Separately approved correctness fixes where required; retain legacy oracle and explicitly document intentional behavioral differences |
| Phase D | CPU primitive/fused-kernel experiments, storage reuse and one-layer threading; each change independently regression checked |
| Phase E | Worker pipeline, bounded buffering, preview/writer separation and rendering-copy reductions |
| Phase F | Optional CMake/MSVC migration as an independently validated build change before conventional Windows CUDA integration |
| Phase G | GPU prototype selected from measured CPU costs; transfer-inclusive benchmark, fallback, packaging and hardware matrix |

Open questions for Windows verification: exact decoder and pixel format; OpenCV CPU
dispatch/parallel backend and compiler/runtime provenance in the prebuilt archive;
single-video scaling and nested-team behavior; repeated multi-video race manifestation;
Qt paint/QML thread scheduling and preview/vsync pacing; long-run retained image/tear
memory; CSV re-export/first-frame/EOF behavior; graphics fallback and TIFF plugins on a
clean PC; Unicode paths and codec metadata edge cases. Also determine intended semantics
for last-row changes, fractional tears, >255 FPS and “unique frames” before approving fixes.

Only Phase 0 is complete here. Runtime baseline capture, Windows build success, regression
execution and optimization performance remain unverified. Stop before Phase B.
