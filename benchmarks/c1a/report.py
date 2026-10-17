"""Gate A1 protocol validation and deterministic reporting; no benchmark execution."""
import argparse
import hashlib
import itertools
import json
import math
import re
import statistics
import sys
from pathlib import Path

VERSION = 1
MAX_INTEGER = 2**63 - 1
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_LATENCY_SAMPLES = 1_000_000
PHASE_B_COMMIT = "df981aaed23827e3716ab0ca59ad28e3ea9ae828"
SOURCE_COMMIT = "a0b4563a076e336863f743ec92c1ee8221f5aba6"
WORKLOADS = ("decode", "analysis", "headless_pipeline", "gui_pipeline")
EXPORTS = ("none", "csv", "jpeg", "csv_jpeg")
PATTERNS = ("identical", "alternating", "periodic_duplicates", "sparse_change", "tear_heavy")
REQUIRED = {
    "decode": ["cpu", "memory", "threads", "latency.acquisition"],
    "analysis": ["cpu", "memory", "threads", "latency.analysis"],
    "headless_pipeline": ["cpu", "memory", "threads", "latency.processing"],
    "gui_pipeline": ["cpu", "memory", "threads", "latency.processing", "latency.gui_delivery"],
}
BOUNDARIES = {
    "acquisition": "batch_read_request_to_read_return",
    "analysis": "analysis_call_entry_to_return",
    "processing": "batch_acquisition_start_to_ordered_output_completion",
    "gui_delivery": "output_delivery_to_paint_callback",
}


class ProtocolError(ValueError):
    """Malformed or inconsistent protocol data."""


def require(condition, message):
    if not condition:
        raise ProtocolError(message)


def fields(value, expected, label):
    require(type(value) is dict, label + ": expected object")
    require(set(value) == set(expected), label + ": unexpected or missing fields")


def integer(value, label, minimum=0):
    require(type(value) is int and minimum <= value <= MAX_INTEGER,
            label + ": expected bounded integer")


def text(value, label):
    require(type(value) is str and bool(value.strip()), label + ": expected nonempty string")


def digest(value, size, label):
    require(type(value) is str and re.fullmatch("[0-9a-f]{" + str(size) + "}", value),
            label + ": invalid lowercase hexadecimal digest")


def identifier(value, label):
    require(type(value) is str and re.fullmatch(r"[a-z0-9][a-z0-9_-]*", value),
            label + ": invalid identifier")


def choices(value, allowed, label):
    require(type(value) is list and bool(value), label + ": expected nonempty list")
    require(all(type(v) in (str, int) and type(v) is not bool for v in value),
            label + ": invalid selection type")
    require(len(value) == len(set(value)), label + ": duplicate selection")
    require(all(v in allowed for v in value), label + ": unsupported selection")


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def canonical_sha256(value):
    return hashlib.sha256(canonical_json(value).encode("ascii")).hexdigest()


def matrix_sha256(matrix):
    validate_matrix(matrix)
    return canonical_sha256(matrix)


def validate_matrix(matrix):
    fields(matrix, ("schema_version", "protocol", "axes", "families"), "matrix")
    require(type(matrix["schema_version"]) is int and matrix["schema_version"] == VERSION,
            "unsupported matrix schema")
    protocol = matrix["protocol"]
    fields(protocol, ("warmup", "measured_trials", "percentile_method",
                      "required_metrics", "thread_policy", "analysis_options"), "protocol")
    fields(protocol["warmup"], ("minimum_batches", "ring_multiples"), "warmup")
    require(protocol["warmup"] == {"minimum_batches": 120, "ring_multiples": 2}
            and all(type(v) is int for v in protocol["warmup"].values()),
            "unsupported warmup policy")
    require(type(protocol["measured_trials"]) is int and protocol["measured_trials"] == 7,
            "protocol requires seven measured trials")
    require(protocol["percentile_method"] == "nearest_rank", "unsupported percentile method")
    require(protocol["required_metrics"] == REQUIRED, "required metric policy differs")
    fields(protocol["thread_policy"], ("openmp_threads", "opencv_threads",
                                      "dynamic", "nested"), "thread policy")
    require(protocol["thread_policy"] == {
        "openmp_threads": 1, "opencv_threads": 1, "dynamic": False, "nested": False
    } and type(protocol["thread_policy"]["openmp_threads"]) is int
      and type(protocol["thread_policy"]["opencv_threads"]) is int
      and type(protocol["thread_policy"]["dynamic"]) is bool
      and type(protocol["thread_policy"]["nested"]) is bool, "unsupported thread policy")
    fields(protocol["analysis_options"], ("pixel_threshold", "tear_dismiss_percent",
                                           "delta_rendering", "centering", "draw_tears"),
           "analysis options")
    require(protocol["analysis_options"] == {
        "pixel_threshold": 0, "tear_dismiss_percent": 10,
        "delta_rendering": False, "centering": False, "draw_tears": True
    } and type(protocol["analysis_options"]["pixel_threshold"]) is int
      and type(protocol["analysis_options"]["tear_dismiss_percent"]) is int
      and all(type(protocol["analysis_options"][k]) is bool for k in
              ("delta_rendering", "centering", "draw_tears")), "unsupported analysis options")
    axes = matrix["axes"]
    fields(axes, ("resolutions", "video_counts", "fps", "exports", "patterns", "preview"), "axes")
    fields(axes["resolutions"], ("720p", "1080p", "1440p", "4k"), "resolution axes")
    for name, expected in {
        "720p": (1280, 720), "1080p": (1920, 1080),
        "1440p": (2560, 1440), "4k": (3840, 2160)
    }.items():
        value = axes["resolutions"][name]
        fields(value, ("width", "height"), "resolution " + name)
        integer(value["width"], "width", 1)
        integer(value["height"], "height", 1)
        require((value["width"], value["height"]) == expected, "resolution differs: " + name)
    choices(axes["video_counts"], (1, 2, 3), "video counts")
    require(set(axes["video_counts"]) == {1, 2, 3}, "missing video count")
    require(type(axes["fps"]) is dict and bool(axes["fps"]), "missing FPS axes")
    rational_rates = set()
    for label, rate in axes["fps"].items():
        identifier(label, "FPS label")
        fields(rate, ("numerator", "denominator"), "FPS")
        integer(rate["numerator"], "FPS numerator", 1)
        integer(rate["denominator"], "FPS denominator", 1)
        require(math.gcd(rate["numerator"], rate["denominator"]) == 1, "FPS must be reduced")
        require(rate["numerator"] <= 255 * rate["denominator"], "FPS exceeds legacy range")
        pair = (rate["numerator"], rate["denominator"])
        require(pair not in rational_rates, "duplicate rational FPS")
        rational_rates.add(pair)
    require({(24, 1), (30, 1), (60, 1), (120, 1), (240, 1)} <= rational_rates,
            "missing core FPS coverage")
    for key, allowed in (("exports", EXPORTS), ("patterns", PATTERNS),
                         ("preview", ("absent", "enabled", "disabled"))):
        choices(axes[key], allowed, key)
        require(set(axes[key]) == set(allowed), "incomplete axis: " + key)
    require(type(matrix["families"]) is list and bool(matrix["families"]), "missing families")
    family_ids = set()
    for family in matrix["families"]:
        fields(family, ("id", "classification", "workload", "input_resolutions",
                        "output_resolution", "video_counts", "fps", "exports",
                        "patterns", "preview", "batch_policy"), "family")
        identifier(family["id"], "family ID")
        require(family["id"] not in family_ids, "duplicate family ID")
        family_ids.add(family["id"])
        require(family["classification"] in ("mandatory", "exploratory"), "invalid classification")
        require(family["workload"] in WORKLOADS, "invalid workload")
        choices(family["input_resolutions"], axes["resolutions"], "input resolutions")
        require(type(family["output_resolution"]) is str and
                (family["output_resolution"] == "match_input"
                 or family["output_resolution"] in axes["resolutions"]), "invalid output resolution")
        for key in ("video_counts", "fps", "exports", "patterns", "preview"):
            choices(family[key], axes[key], "family " + key)
        workload = family["workload"]
        if workload == "gui_pipeline":
            require("absent" not in family["preview"], "GUI preview cannot be absent")
        else:
            require(family["preview"] == ["absent"], "headless preview must be absent")
        if workload in ("decode", "analysis"):
            require(family["exports"] == ["none"], "isolated workload cannot export")
        require(family["batch_policy"] in ("complete_synchronized", "partial_decode", "eof_probe"),
                "invalid batch policy")
        require(family["batch_policy"] == "complete_synchronized" or workload == "decode",
                "partial/EOF policy only applies to decode workloads")
    return matrix


def expand_matrix(matrix):
    validate_matrix(matrix)
    axes = matrix["axes"]
    configurations = []
    for family in matrix["families"]:
        combinations = itertools.product(
            family["input_resolutions"], family["video_counts"], family["fps"],
            family["exports"], family["patterns"], family["preview"]
        )
        for resolution, videos, rate, export, pattern, preview in combinations:
            output = resolution if family["output_resolution"] == "match_input" \
                else family["output_resolution"]
            config_id = "-".join((family["id"], resolution, "out", output,
                                  "v" + str(videos), "fps", rate, export,
                                  pattern, preview, family["batch_policy"]))
            configuration = {
                "schema_version": VERSION, "id": config_id,
                "classification": family["classification"], "workload": family["workload"],
                "input_resolution": dict(axes["resolutions"][resolution]),
                "output_resolution": dict(axes["resolutions"][output]),
                "video_count": videos, "fps": dict(axes["fps"][rate]),
                "export_mode": export, "pattern": pattern, "preview": preview,
                "batch_policy": family["batch_policy"], "protocol": matrix["protocol"],
            }
            configurations.append(configuration)
    require(len(configurations) == len({c["id"] for c in configurations}), "duplicate config ID")
    return sorted(configurations, key=lambda c: c["id"])


def configuration_sha256(configuration):
    return canonical_sha256(configuration)


def warmup_batches(configuration):
    rate = configuration["fps"]
    ceiling = (rate["numerator"] + rate["denominator"] - 1) // rate["denominator"]
    policy = configuration["protocol"]["warmup"]
    return max(policy["minimum_batches"], policy["ring_multiples"] * ceiling)


def metric(value, label, applicable=True):
    require(type(value) is dict and "status" in value, label + ": missing metric status")
    status = value["status"]
    if status in ("unavailable", "not_applicable"):
        fields(value, ("status", "reason"), label)
        text(value["reason"], label + " reason")
        require(status != "not_applicable" or not applicable,
                label + ": required/applicable metric cannot be not_applicable")
        return False
    require(status == "measured", label + ": invalid metric status")
    require(applicable, label + ": metric is not applicable")
    return True


def required_metrics(configuration):
    result = list(configuration["protocol"]["required_metrics"][configuration["workload"]])
    if configuration["export_mode"] != "none":
        result.append("exports")
    return result


def validate_trial(trial, matrix):
    configurations = {c["id"]: c for c in expand_matrix(matrix)}
    fields(trial, ("schema_version", "configuration_id", "matrix_sha256",
                   "configuration_sha256", "trial_index", "status", "provenance",
                   "measurement"), "trial")
    require(type(trial["schema_version"]) is int and trial["schema_version"] == VERSION,
            "unsupported trial schema")
    require(type(trial["configuration_id"]) is str
            and trial["configuration_id"] in configurations, "unknown configuration")
    configuration = configurations[trial["configuration_id"]]
    for key, expected in (("matrix_sha256", matrix_sha256(matrix)),
                          ("configuration_sha256", configuration_sha256(configuration))):
        digest(trial[key], 64, key)
        require(trial[key] == expected, key + ": mismatch")
    integer(trial["trial_index"], "trial index", 1)
    require(trial["trial_index"] <= 7, "trial index exceeds protocol")
    require(trial["status"] in ("completed", "failed", "cancelled", "timed_out"),
            "invalid execution status")
    provenance = trial["provenance"]
    fields(provenance, (
        "phase_b_tag", "phase_b_commit", "frozen_source_commit", "infrastructure_commit",
        "input_manifest_sha256", "machine_id", "cpu_model", "physical_cores",
        "logical_processors", "os", "compiler", "qt_version", "opencv_version",
        "python_version", "decoder_backend", "storage_description"
    ), "provenance")
    require(provenance["phase_b_tag"] == "phase-b-windows-reference-v1"
            and provenance["phase_b_commit"] == PHASE_B_COMMIT
            and provenance["frozen_source_commit"] == SOURCE_COMMIT, "frozen reference mismatch")
    digest(provenance["infrastructure_commit"], 40, "infrastructure commit")
    digest(provenance["input_manifest_sha256"], 64, "input manifest")
    for key in ("machine_id", "cpu_model", "os", "compiler", "storage_description"):
        text(provenance[key], key)
    require(re.search(r"(?<![0-9])8\.1\.0(?![0-9])", provenance["compiler"]),
            "compiler must identify historical GCC 8.1.0")
    integer(provenance["logical_processors"], "logical processors", 1)
    if provenance["physical_cores"] is not None:
        integer(provenance["physical_cores"], "physical cores", 1)
        require(provenance["physical_cores"] <= provenance["logical_processors"],
                "physical cores exceed logical processors")
    require(provenance["qt_version"] == "5.15.2"
            and provenance["opencv_version"] == "4.5.1"
            and provenance["python_version"] == "3.13.15", "dependency version mismatch")
    backend = provenance["decoder_backend"]
    if configuration["workload"] == "analysis":
        require(backend is None, "predecoded analysis must not claim a decoder backend")
    else:
        require(type(backend) is list and len(backend) == configuration["video_count"],
                "decoder backend inventory mismatch")
        for value in backend:
            text(value, "decoder backend")
    measurement = trial["measurement"]
    fields(measurement, (
        "warmup_batches", "measured_batches", "submitted_source_frames",
        "acquired_source_frames", "wall_time_ns", "latency_ns", "cpu", "memory",
        "threads", "exports", "allocation_copy"
    ), "measurement")
    completed = trial["status"] == "completed"
    for key in ("warmup_batches", "measured_batches", "submitted_source_frames",
                "acquired_source_frames", "wall_time_ns"):
        integer(measurement[key], key)
    if completed:
        require(measurement["warmup_batches"] == warmup_batches(configuration),
                "warmup count differs from protocol")
        require(measurement["measured_batches"] > 0 and measurement["wall_time_ns"] > 0,
                "completed trial requires positive measured batches and wall time")
    if completed and configuration["batch_policy"] == "complete_synchronized":
        require(measurement["submitted_source_frames"] ==
                measurement["measured_batches"] * configuration["video_count"],
                "submitted frames do not match complete synchronized batches")
    if configuration["workload"] == "analysis":
        require(measurement["acquired_source_frames"] == 0,
                "predecoded analysis must not claim acquisition")
    else:
        require(measurement["acquired_source_frames"] >= measurement["submitted_source_frames"],
                "acquired frames smaller than submitted frames")

    available = set()
    latency = measurement["latency_ns"]
    require(type(latency) is dict and set(latency) <= set(BOUNDARIES), "invalid latency fields")
    required = required_metrics(configuration)
    for name, value in latency.items():
        applicable = "latency." + name in required
        if metric(value, "latency." + name, applicable):
            fields(value, ("status", "boundary", "sampling_policy", "samples_ns"), "latency")
            require(value["boundary"] == BOUNDARIES[name], "latency boundary mismatch")
            require(value["sampling_policy"] in ("every_batch", "sampled_batches"),
                    "invalid latency sampling policy")
            samples = value["samples_ns"]
            require(type(samples) is list and 0 < len(samples) <= MAX_LATENCY_SAMPLES,
                    "invalid latency sample count")
            for sample in samples:
                integer(sample, "latency sample")
                if completed:
                    require(sample <= measurement["wall_time_ns"],
                            "latency sample exceeds measurement window")
            if value["sampling_policy"] == "every_batch":
                require(len(samples) == measurement["measured_batches"],
                        "per-batch latency sample count differs from batches")
                available.add("latency." + name)
            else:
                require(len(samples) <= measurement["measured_batches"],
                        "sampled latency count exceeds batches")

    cpu = measurement["cpu"]
    if metric(cpu, "cpu"):
        fields(cpu, ("status", "method", "process_time_ns", "available_logical_processors"), "cpu")
        text(cpu["method"], "CPU collection method")
        integer(cpu["process_time_ns"], "CPU time")
        integer(cpu["available_logical_processors"], "available logical processors", 1)
        require(cpu["available_logical_processors"] == provenance["logical_processors"],
                "CPU normalization processor count mismatch")
        available.add("cpu")
    memory = measurement["memory"]
    if metric(memory, "memory"):
        fields(memory, ("status", "method", "sampling_interval_ns", "sample_count",
                        "sampled_peak_private_bytes", "sampled_peak_working_set_bytes",
                        "os_peak_working_set_bytes"), "memory")
        text(memory["method"], "memory collection method")
        integer(memory["sampling_interval_ns"], "memory sample interval", 1)
        integer(memory["sample_count"], "memory sample count", 1)
        for key in ("sampled_peak_private_bytes", "sampled_peak_working_set_bytes"):
            integer(memory[key], key)
        if memory["os_peak_working_set_bytes"] is not None:
            integer(memory["os_peak_working_set_bytes"], "OS working set peak")
            require(memory["os_peak_working_set_bytes"] >= memory["sampled_peak_working_set_bytes"],
                    "OS peak below sampled working set peak")
        available.add("memory")
    threads = measurement["threads"]
    if metric(threads, "threads"):
        fields(threads, ("status", "method", "sampling_interval_ns", "sample_count",
                         "configured_openmp_threads", "configured_opencv_threads",
                         "observed_process_threads_max", "openmp_dynamic", "openmp_nested"), "threads")
        text(threads["method"], "thread collection method")
        for key in ("sampling_interval_ns", "sample_count", "observed_process_threads_max"):
            integer(threads[key], key, 1)
        require(type(threads["configured_openmp_threads"]) is int
                and threads["configured_openmp_threads"] == 1
                and type(threads["configured_opencv_threads"]) is int
                and threads["configured_opencv_threads"] == 1
                and threads["openmp_dynamic"] is False
                and threads["openmp_nested"] is False, "thread policy mismatch")
        available.add("threads")
    export = measurement["exports"]
    exporting = configuration["export_mode"] != "none"
    if metric(export, "exports", exporting):
        fields(export, ("status", "csv_data_rows", "images", "interval_ns"), "exports")
        integer(export["csv_data_rows"], "CSV data rows")
        integer(export["images"], "exported images")
        integer(export["interval_ns"], "export interval", 1)
        mode = configuration["export_mode"]
        require(mode in ("csv", "csv_jpeg") or export["csv_data_rows"] == 0,
                "CSV rows incompatible with export mode")
        require(mode in ("jpeg", "csv_jpeg") or export["images"] == 0,
                "images incompatible with export mode")
        if completed:
            require(export["interval_ns"] <= measurement["wall_time_ns"],
                    "export interval exceeds measurement window")
            require(mode not in ("csv", "csv_jpeg") or export["csv_data_rows"] > 0,
                    "completed CSV export has no data rows")
            require(mode not in ("jpeg", "csv_jpeg") or export["images"] > 0,
                    "completed image export has no images")
        available.add("exports")
    accounting = measurement["allocation_copy"]
    require(type(accounting) is dict and "status" in accounting, "invalid allocation accounting")
    if accounting["status"] in ("measured", "estimated"):
        fields(accounting, ("status", "method", "allocations", "allocation_bytes",
                            "copy_operations", "copy_bytes"), "allocation/copy")
        text(accounting["method"], "allocation/copy method")
        for key in ("allocations", "allocation_bytes", "copy_operations", "copy_bytes"):
            if accounting["status"] == "estimated" and accounting[key] is None:
                continue
            integer(accounting[key], key)
        require(any(accounting[k] is not None for k in
                    ("allocations", "allocation_bytes", "copy_operations", "copy_bytes")),
                "estimated accounting requires at least one estimate")
    else:
        metric(accounting, "allocation/copy")
    missing = sorted(set(required) - available)
    return {"protocol_complete": not missing,
            "missing_required_metrics": missing, "configuration": configuration}


def nearest_rank(samples, percentile):
    require(type(samples) is list and bool(samples), "percentile requires samples")
    require(type(percentile) in (int, float) and math.isfinite(percentile)
            and 0 <= percentile <= 100, "invalid percentile")
    for sample in samples:
        require(type(sample) in (int, float) and math.isfinite(sample) and sample >= 0,
                "invalid percentile sample")
    ordered = sorted(samples)
    index = max(1, math.ceil(percentile * len(ordered) / 100)) - 1
    return ordered[index]


def trial_statistics(trial):
    measurement = trial["measurement"]
    wall = measurement["wall_time_ns"]
    require(wall > 0, "throughput requires positive wall time")
    latency = {}
    for name, value in sorted(measurement["latency_ns"].items()):
        if value["status"] == "measured":
            samples = value["samples_ns"]
            latency[name] = {
                "sampling_policy": value["sampling_policy"], "sample_count": len(samples),
                "p50_ns": nearest_rank(samples, 50), "p95_ns": nearest_rank(samples, 95),
                "p99_ns": nearest_rank(samples, 99),
            }
    cpu = measurement["cpu"]
    cpu_metrics = None
    if cpu["status"] == "measured":
        process_percent = 100 * cpu["process_time_ns"] / wall
        cpu_metrics = {
            "process_percent": process_percent,
            "normalized_percent": process_percent / cpu["available_logical_processors"],
        }
    export = measurement["exports"]
    export_metrics = None
    if export["status"] == "measured":
        export_metrics = {
            "csv_data_rows_per_second": export["csv_data_rows"] * 1e9 / export["interval_ns"],
            "images_per_second": export["images"] * 1e9 / export["interval_ns"],
        }
    return {
        "trial_index": trial["trial_index"],
        "batch_policy": None,
        "batches_per_second": measurement["measured_batches"] * 1e9 / wall,
        "submitted_source_frames_per_second": measurement["submitted_source_frames"] * 1e9 / wall,
        "acquired_source_frames_per_second": measurement["acquired_source_frames"] * 1e9 / wall,
        "latency": latency, "cpu_utilization": cpu_metrics, "export_throughput": export_metrics,
        "memory": measurement["memory"], "threads": measurement["threads"],
        "allocation_copy": measurement["allocation_copy"],
    }


def aggregate_trials(matrix, trials):
    validate_matrix(matrix)
    require(type(trials) is list and bool(trials), "aggregation requires trial records")
    validations = [validate_trial(t, matrix) for t in trials]
    ordered = sorted(zip(trials, validations), key=lambda pair: pair[0]["trial_index"])
    identity = trials[0]["configuration_id"]
    require(all(t["configuration_id"] == identity for t in trials), "mixed configurations")
    require(len({t["trial_index"] for t in trials}) == len(trials), "duplicate trial index")
    require(all(t["provenance"] == trials[0]["provenance"] for t in trials),
            "inconsistent trial provenance")
    completed = [t for t, v in ordered if t["status"] == "completed"]
    for key in ("measured_batches", "submitted_source_frames", "acquired_source_frames"):
        require(len({t["measurement"][key] for t in completed}) <= 1,
                key + ": workload count differs across completed trials")
    for key in ("csv_data_rows", "images"):
        counts = {
            t["measurement"]["exports"][key] for t in completed
            if t["measurement"]["exports"]["status"] == "measured"
        }
        require(len(counts) <= 1, key + ": export count differs across completed trials")
    # Collection methods and policies must match when measurements are available.
    signatures = {}
    for trial, validation in ordered:
        measurement = trial["measurement"]
        for name in ("cpu", "memory", "threads", "allocation_copy"):
            value = measurement[name]
            if value["status"] in ("measured", "estimated"):
                signature = tuple((k, value[k]) for k in
                                  ("status", "method", "sampling_interval_ns",
                                   "configured_openmp_threads", "configured_opencv_threads",
                                   "openmp_dynamic", "openmp_nested") if k in value)
                require(name not in signatures or signatures[name] == signature,
                        "inconsistent metric collection: " + name)
                signatures[name] = signature
        for name, value in measurement["latency_ns"].items():
            if value["status"] == "measured":
                signature = (value["boundary"], value["sampling_policy"])
                key = "latency." + name
                require(key not in signatures or signatures[key] == signature,
                        "inconsistent latency sampling")
                signatures[key] = signature
    statistics_records = [trial_statistics(t) for t in completed]
    configuration = validations[0]["configuration"]
    for value in statistics_records:
        value["batch_policy"] = configuration["batch_policy"]
    statistically_complete = len(completed) == 7 and len(trials) == 7
    protocol_complete = all(v["protocol_complete"] for v in validations)
    medians = None
    if statistics_records:
        medians = {
            key: statistics.median([v[key] for v in statistics_records])
            for key in ("batches_per_second", "submitted_source_frames_per_second",
                        "acquired_source_frames_per_second")
        }
    return {
        "configuration_id": identity, "configuration_sha256": configuration_sha256(configuration),
        "classification": "complete" if statistically_complete and protocol_complete else "partial",
        "statistical_completeness": "complete" if statistically_complete else "partial",
        "protocol_completeness": "complete" if protocol_complete else "partial",
        "performance_threshold": None,
        "trial_count": len(trials), "completed_trial_count": len(completed),
        "missing_required_metrics": [
            {"trial_index": t["trial_index"], "metrics": v["missing_required_metrics"]}
            for t, v in ordered if v["missing_required_metrics"]
        ],
        "noncompleted_trials": [
            {"trial_index": t["trial_index"], "status": t["status"]}
            for t in sorted(trials, key=lambda t: t["trial_index"]) if t["status"] != "completed"
        ],
        "provenance": trials[0]["provenance"],
        "median_throughput": medians, "trial_statistics": statistics_records,
    }


def build_report(matrix, trials):
    try:
        configurations = expand_matrix(matrix)
        require(type(trials) is list, "result root must be a trial array")
        errors = []
        groups = {}
        for index, trial in enumerate(trials):
            try:
                validate_trial(trial, matrix)
                groups.setdefault(trial["configuration_id"], []).append(trial)
            except ProtocolError as error:
                errors.append({"record_index": index, "message": str(error)})
        results = []
        for config_id in sorted(groups):
            try:
                results.append(aggregate_trials(matrix, groups[config_id]))
            except ProtocolError as error:
                errors.append({"configuration_id": config_id, "message": str(error)})
        mandatory = {c["id"] for c in configurations if c["classification"] == "mandatory"}
        missing = sorted(mandatory - set(groups))
        invalid = bool(errors)
        complete = bool(results) and not missing and all(
            group["classification"] == "complete" for group in results
        )
        return {
            "schema_version": VERSION, "matrix_sha256": matrix_sha256(matrix),
            "classification": "invalid" if invalid else "complete" if complete else "partial",
            "performance_threshold": None, "errors": errors,
            "missing_mandatory_configurations": missing, "configurations": results,
        }
    except ProtocolError as error:
        return {"schema_version": VERSION, "classification": "invalid",
                "performance_threshold": None, "errors": [{"message": str(error)}]}


def render_report(report):
    return json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n"


def load_json(path):
    def unique_pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key: " + key)
            result[key] = value
        return result

    def nonfinite(value):
        raise ProtocolError("nonfinite JSON constant: " + value)

    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    require(len(raw) <= MAX_JSON_BYTES, "JSON input size limit exceeded")
    try:
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_pairs,
                          parse_constant=nonfinite)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ProtocolError("invalid JSON: " + str(error)) from error


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matrix", help="versioned matrix JSON")
    parser.add_argument("trials", help="JSON array of recorded trial results")
    arguments = parser.parse_args(argv)
    try:
        report = build_report(load_json(arguments.matrix), load_json(arguments.trials))
    except (OSError, ProtocolError, RecursionError) as error:
        report = {"schema_version": VERSION, "classification": "invalid",
                  "performance_threshold": None, "errors": [{"message": str(error)}]}
    sys.stdout.write(render_report(report))
    return {"complete": 0, "invalid": 1, "partial": 2}[report["classification"]]


if __name__ == "__main__":
    raise SystemExit(main())
