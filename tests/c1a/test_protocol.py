"""Synthetic Gate A1 protocol tests; no binaries, fixtures or benchmarks are run."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("c1a_report", ROOT / "benchmarks/c1a/report.py")
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = json.loads((ROOT / "benchmarks/c1a/matrix.json").read_text(encoding="utf-8"))
        cls.configurations = report.expand_matrix(cls.matrix)

    def configuration(self, workload="headless_pipeline", export="none", policy="complete_synchronized"):
        return next(c for c in self.configurations if
                    c["workload"] == workload and c["export_mode"] == export
                    and c["batch_policy"] == policy)

    def trial(self, index=1, configuration=None):
        c = configuration or self.configuration()
        required = report.required_metrics(c)
        latency = {}
        for name in report.BOUNDARIES:
            if "latency." + name in required:
                latency[name] = {
                    "status": "measured", "boundary": report.BOUNDARIES[name],
                    "sampling_policy": "every_batch",
                    "samples_ns": [1_000_000, 2_000_000, 3_000_000, 4_000_000],
                }
        return {
            "schema_version": 1, "configuration_id": c["id"],
            "matrix_sha256": report.matrix_sha256(self.matrix),
            "configuration_sha256": report.configuration_sha256(c),
            "trial_index": index, "status": "completed",
            "provenance": {
                "phase_b_tag": "phase-b-windows-reference-v1",
                "phase_b_commit": report.PHASE_B_COMMIT,
                "frozen_source_commit": report.SOURCE_COMMIT,
                "infrastructure_commit": "a" * 40, "input_manifest_sha256": "b" * 64,
                "machine_id": "synthetic-unit-test", "cpu_model": "synthetic CPU",
                "physical_cores": 2, "logical_processors": 4,
                "os": "synthetic Windows", "compiler": "MinGW GCC 8.1.0",
                "qt_version": "5.15.2", "opencv_version": "4.5.1", "python_version": "3.13.15",
                "decoder_backend": None if c["workload"] == "analysis" else ["SYNTHETIC"] * c["video_count"],
                "storage_description": "synthetic storage",
            },
            "measurement": {
                "warmup_batches": report.warmup_batches(c), "measured_batches": 4,
                "submitted_source_frames": 4 * c["video_count"],
                "acquired_source_frames": 0 if c["workload"] == "analysis" else 4 * c["video_count"],
                "wall_time_ns": index * 1_000_000_000, "latency_ns": latency,
                "cpu": {"status": "measured", "method": "synthetic process CPU",
                        "process_time_ns": 500_000_000, "available_logical_processors": 4},
                "memory": {"status": "measured", "method": "synthetic samples",
                           "sampling_interval_ns": 10_000_000, "sample_count": 3,
                           "sampled_peak_private_bytes": 4096,
                           "sampled_peak_working_set_bytes": 8192,
                           "os_peak_working_set_bytes": 16384},
                "threads": {"status": "measured", "method": "synthetic samples",
                            "sampling_interval_ns": 10_000_000, "sample_count": 3,
                            "configured_openmp_threads": 1, "configured_opencv_threads": 1,
                            "observed_process_threads_max": 5,
                            "openmp_dynamic": False, "openmp_nested": False},
                "exports": (
                    {"status": "not_applicable", "reason": "exports disabled"}
                    if c["export_mode"] == "none" else {
                        "status": "measured", "interval_ns": 1_000_000,
                        "csv_data_rows": 4 if c["export_mode"] in ("csv", "csv_jpeg") else 0,
                        "images": 4 if c["export_mode"] in ("jpeg", "csv_jpeg") else 0
                    }
                ),
                "allocation_copy": {"status": "unavailable", "reason": "not collected in this synthetic record"},
            },
        }

    def seven(self, configuration=None):
        return [self.trial(i, configuration) for i in range(1, 8)]

    def test_matrix_coverage_and_mandatory_count(self):
        report.validate_matrix(self.matrix)
        self.assertEqual(sum(c["classification"] == "mandatory" for c in self.configurations), 48)
        self.assertEqual(sum(c["classification"] == "exploratory" for c in self.configurations), 924)
        self.assertEqual(len(self.configurations), len({c["id"] for c in self.configurations}))
        self.assertEqual({c["video_count"] for c in self.configurations}, {1, 2, 3})
        self.assertEqual({c["input_resolution"]["height"] for c in self.configurations}, {720, 1080, 1440, 2160})
        self.assertTrue(any(c["input_resolution"] != c["output_resolution"] for c in self.configurations))
        self.assertEqual({c["workload"] for c in self.configurations}, set(report.WORKLOADS))

    def test_matrix_strict_fields_and_version(self):
        for change in ({"schema_version": True}, {"schema_version": 2}, {"extra": 0}):
            matrix = copy.deepcopy(self.matrix)
            matrix.update(change)
            with self.assertRaises(report.ProtocolError):
                report.validate_matrix(matrix)

    def test_invalid_family_combinations(self):
        for key, value in (("preview", ["enabled"]), ("video_counts", [0]),
                           ("fps", ["missing"]), ("output_resolution", []),
                           ("classification", "unknown"), ("input_resolutions", ["8k"])):
            matrix = copy.deepcopy(self.matrix)
            matrix["families"][0][key] = value
            with self.assertRaises(report.ProtocolError):
                report.validate_matrix(matrix)

    def test_invalid_isolated_export_and_partial_policy(self):
        for workload, export, policy in (
            ("analysis", ["csv"], "complete_synchronized"),
            ("headless_pipeline", ["none"], "partial_decode")
        ):
            matrix = copy.deepcopy(self.matrix)
            matrix["families"][0].update(workload=workload, exports=export, batch_policy=policy)
            with self.assertRaises(report.ProtocolError):
                report.validate_matrix(matrix)

    def test_duplicate_families_and_selections(self):
        for duplicate_family in (False, True):
            matrix = copy.deepcopy(self.matrix)
            if duplicate_family:
                matrix["families"].append(copy.deepcopy(matrix["families"][0]))
            else:
                matrix["families"][0]["video_counts"] = [1, 1]
            with self.assertRaises(report.ProtocolError):
                report.validate_matrix(matrix)

    def test_canonical_identity_ignores_object_key_order(self):
        reordered = {key: self.matrix[key] for key in reversed(list(self.matrix))}
        self.assertEqual(report.matrix_sha256(self.matrix), report.matrix_sha256(reordered))
        self.assertEqual(report.canonical_sha256({"b": 2, "a": 1}),
                         report.canonical_sha256({"a": 1, "b": 2}))

    def test_changed_matrix_and_config_hashes_rejected(self):
        for field in ("matrix_sha256", "configuration_sha256"):
            trial = self.trial()
            trial[field] = "0" * 64
            with self.assertRaises(report.ProtocolError):
                report.validate_trial(trial, self.matrix)
        matrix = copy.deepcopy(self.matrix)
        matrix["families"][0]["patterns"] = ["identical"]
        with self.assertRaises(report.ProtocolError):
            report.validate_trial(self.trial(), matrix)

    def test_protocol_is_part_of_configuration_identity(self):
        c = copy.deepcopy(self.configuration())
        changed = copy.deepcopy(c)
        changed["protocol"]["warmup"]["minimum_batches"] += 1
        self.assertNotEqual(report.configuration_sha256(c), report.configuration_sha256(changed))

    def test_warmup_exact_rational_fps(self):
        c = copy.deepcopy(self.configuration())
        c["fps"] = {"numerator": 30000, "denominator": 1001}
        self.assertEqual(report.warmup_batches(c), 120)
        c["fps"] = {"numerator": 240, "denominator": 1}
        self.assertEqual(report.warmup_batches(c), 480)

    def test_invalid_trial_schema_and_numeric_types(self):
        for mutate in (
            lambda t: t.update(extra=1),
            lambda t: t.update(trial_index=True),
            lambda t: t["measurement"].update(wall_time_ns=0),
            lambda t: t["measurement"].update(wall_time_ns=float("inf")),
            lambda t: t["measurement"].update(measured_batches=-1),
            lambda t: t["measurement"].pop("cpu"),
        ):
            trial = self.trial()
            mutate(trial)
            with self.assertRaises(report.ProtocolError):
                report.validate_trial(trial, self.matrix)

    def test_synchronized_source_frame_invariant(self):
        trial = self.trial()
        trial["measurement"]["submitted_source_frames"] += 1
        trial["measurement"]["acquired_source_frames"] += 1
        with self.assertRaises(report.ProtocolError):
            report.validate_trial(trial, self.matrix)

    def test_partial_and_eof_invariant_exceptions(self):
        for policy in ("partial_decode", "eof_probe"):
            trial = self.trial(configuration=self.configuration("decode", policy=policy))
            trial["measurement"]["submitted_source_frames"] += 1
            trial["measurement"]["acquired_source_frames"] += 1
            self.assertTrue(report.validate_trial(trial, self.matrix)["protocol_complete"])

    def test_unavailable_metrics_are_valid_partial(self):
        trials = self.seven()
        for trial in trials:
            trial["measurement"]["cpu"] = {"status": "unavailable", "reason": "not collected"}
        result = report.aggregate_trials(self.matrix, trials)
        self.assertEqual(result["classification"], "partial")
        self.assertEqual(result["statistical_completeness"], "complete")
        self.assertEqual(result["protocol_completeness"], "partial")
        self.assertEqual(result["missing_required_metrics"][0]["metrics"], ["cpu"])

    def test_missing_required_latency_is_partial(self):
        trial = self.trial()
        trial["measurement"]["latency_ns"] = {}
        self.assertEqual(report.validate_trial(trial, self.matrix)["missing_required_metrics"],
                         ["latency.processing"])

    def test_required_metric_not_applicable_is_invalid(self):
        trial = self.trial()
        trial["measurement"]["cpu"] = {"status": "not_applicable", "reason": "disabled"}
        with self.assertRaises(report.ProtocolError):
            report.validate_trial(trial, self.matrix)

    def test_latency_counts_and_sampling_policy(self):
        trial = self.trial()
        latency = trial["measurement"]["latency_ns"]["processing"]
        latency["samples_ns"] = [1]
        with self.assertRaises(report.ProtocolError):
            report.validate_trial(trial, self.matrix)
        latency["sampling_policy"] = "sampled_batches"
        self.assertFalse(report.validate_trial(trial, self.matrix)["protocol_complete"])
        latency["boundary"] = "unknown"
        with self.assertRaises(report.ProtocolError):
            report.validate_trial(trial, self.matrix)

    def test_latency_boundary_and_nonfinite_samples(self):
        for value in (True, -1, float("nan"), 2_000_000_000):
            trial = self.trial()
            trial["measurement"]["latency_ns"]["processing"]["samples_ns"][0] = value
            with self.assertRaises(report.ProtocolError):
                report.validate_trial(trial, self.matrix)

    def test_workload_specific_latency_requirements(self):
        analysis = self.trial(configuration=self.configuration("analysis"))
        self.assertEqual(report.validate_trial(analysis, self.matrix)["missing_required_metrics"], [])
        gui = self.trial(configuration=self.configuration("gui_pipeline"))
        del gui["measurement"]["latency_ns"]["gui_delivery"]
        self.assertEqual(report.validate_trial(gui, self.matrix)["missing_required_metrics"],
                         ["latency.gui_delivery"])

    def test_export_modes_and_empty_outputs(self):
        for mode in ("csv", "jpeg", "csv_jpeg"):
            trial = self.trial(configuration=self.configuration(export=mode))
            self.assertTrue(report.validate_trial(trial, self.matrix)["protocol_complete"])
            key = "images" if mode == "jpeg" else "csv_data_rows"
            trial["measurement"]["exports"][key] = 0
            with self.assertRaises(report.ProtocolError):
                report.validate_trial(trial, self.matrix)

    def test_export_mode_mismatch(self):
        trial = self.trial(configuration=self.configuration(export="csv"))
        trial["measurement"]["exports"]["images"] = 1
        with self.assertRaises(report.ProtocolError):
            report.validate_trial(trial, self.matrix)

    def test_estimates_do_not_fabricate_missing_allocations(self):
        trial = self.trial()
        trial["measurement"]["allocation_copy"] = {
            "status": "estimated", "method": "known explicit copies only",
            "allocations": None, "allocation_bytes": None, "copy_operations": 2, "copy_bytes": 64
        }
        self.assertTrue(report.validate_trial(trial, self.matrix)["protocol_complete"])

    def test_nearest_rank_percentiles(self):
        values = list(range(1, 101))
        self.assertEqual(report.nearest_rank(values, 0), 1)
        self.assertEqual(report.nearest_rank(values, 50), 50)
        self.assertEqual(report.nearest_rank(values, 95), 95)
        self.assertEqual(report.nearest_rank(values, 99), 99)
        self.assertEqual(report.nearest_rank(values, 100), 100)
        self.assertEqual(report.nearest_rank([4, 1, 3, 2], 50), 2)
        self.assertEqual(report.nearest_rank([9], 99), 9)

    def test_invalid_percentile_inputs(self):
        for samples, percentile in (([], 50), ([1], -1), ([1], 101),
                                    ([True], 50), ([float("nan")], 50),
                                    ([1], float("inf")), ([1], True)):
            with self.assertRaises(report.ProtocolError):
                report.nearest_rank(samples, percentile)

    def test_seven_trial_aggregation(self):
        result = report.aggregate_trials(self.matrix, self.seven())
        self.assertEqual(result["classification"], "complete")
        self.assertEqual(result["statistical_completeness"], "complete")
        self.assertEqual(result["median_throughput"]["batches_per_second"], 1.0)
        self.assertIsNone(result["performance_threshold"])
        first = result["trial_statistics"][0]
        self.assertEqual(first["cpu_utilization"]["process_percent"], 50)
        self.assertEqual(first["cpu_utilization"]["normalized_percent"], 12.5)

    def test_throughput_and_latency_are_distinct(self):
        configuration = next(c for c in self.configurations if
                             c["workload"] == "headless_pipeline" and c["export_mode"] == "none"
                             and c["video_count"] == 3)
        result = report.aggregate_trials(self.matrix, self.seven(configuration))
        self.assertEqual(result["median_throughput"]["batches_per_second"], 1.0)
        self.assertEqual(result["median_throughput"]["submitted_source_frames_per_second"], 3.0)
        self.assertEqual(result["trial_statistics"][0]["latency"]["processing"]["p50_ns"], 2_000_000)

    def test_insufficient_or_failed_trials_are_partial(self):
        self.assertEqual(report.aggregate_trials(self.matrix, self.seven()[:6])["classification"], "partial")
        trials = self.seven()
        trial = trials[-1]
        trial["status"] = "cancelled"
        trial["measurement"]["measured_batches"] = 0
        trial["measurement"]["submitted_source_frames"] = 0
        trial["measurement"]["acquired_source_frames"] = 0
        trial["measurement"]["wall_time_ns"] = 0
        trial["measurement"]["latency_ns"] = {}
        self.assertEqual(report.aggregate_trials(self.matrix, trials)["classification"], "partial")

    def test_inconsistent_trials_are_invalid(self):
        for mutate in (
            lambda t: t["provenance"].update(machine_id="another-machine"),
            lambda t: t["measurement"].update(measured_batches=5, submitted_source_frames=5,
                                             acquired_source_frames=5, latency_ns={}),
            lambda t: t["measurement"]["memory"].update(sampling_interval_ns=20_000_000),
        ):
            trials = self.seven()
            mutate(trials[-1])
            with self.assertRaises(report.ProtocolError):
                report.aggregate_trials(self.matrix, trials)

    def test_duplicate_trials_are_invalid(self):
        trials = self.seven()
        trials[-1]["trial_index"] = 1
        result = report.build_report(self.matrix, trials)
        self.assertEqual(result["classification"], "invalid")

    def test_partial_report_retains_missing_mandatory_coverage(self):
        result = report.build_report(self.matrix, self.seven())
        self.assertEqual(result["classification"], "partial")
        self.assertEqual(result["configurations"][0]["classification"], "complete")
        self.assertTrue(result["missing_mandatory_configurations"])

    def test_complete_report_requires_all_mandatory_configurations(self):
        trials = []
        for configuration in self.configurations:
            if configuration["classification"] == "mandatory":
                trials.extend(self.seven(configuration))
        self.assertEqual(report.build_report(self.matrix, trials)["classification"], "complete")

    def test_invalid_record_is_reported_not_silently_dropped(self):
        trials = self.seven()
        trials[0]["matrix_sha256"] = "0" * 64
        result = report.build_report(self.matrix, trials)
        self.assertEqual(result["classification"], "invalid")
        self.assertEqual(result["errors"][0]["record_index"], 0)

    def test_deterministic_rendering(self):
        trials = self.seven()
        first = report.render_report(report.build_report(self.matrix, trials))
        second = report.render_report(report.build_report(self.matrix, list(reversed(trials))))
        self.assertEqual(first, second)
        self.assertEqual(first, report.render_report(json.loads(first)))

    def test_duplicate_and_nonfinite_json_are_rejected(self):
        for raw in (b'{"schema_version":1,"schema_version":1}', b'{"x":NaN}', b'\xff'):
            with mock.patch.object(report.Path, "open", return_value=io.BytesIO(raw)):
                with self.assertRaises(report.ProtocolError):
                    report.load_json("synthetic-input")

    def test_dependency_and_reference_mismatches(self):
        for key, value in (("qt_version", "6.0.0"), ("phase_b_commit", "0" * 40),
                           ("compiler", "GCC 12.0.0")):
            trial = self.trial()
            trial["provenance"][key] = value
            with self.assertRaises(report.ProtocolError):
                report.validate_trial(trial, self.matrix)

    def test_independent_completeness_indicators(self):
        for count in (6, 7):
            for available in (False, True):
                with self.subTest(count=count, available=available):
                    trials = self.seven()[:count]
                    if not available:
                        for trial in trials:
                            trial["measurement"]["cpu"] = {
                                "status": "unavailable", "reason": "not collected"
                            }
                    result = report.aggregate_trials(self.matrix, trials)
                    self.assertEqual(result["statistical_completeness"],
                                     "complete" if count == 7 else "partial")
                    self.assertEqual(result["protocol_completeness"],
                                     "complete" if available else "partial")
                    self.assertEqual(result["classification"],
                                     "complete" if count == 7 and available else "partial")

    def test_export_counts_must_match_completed_trials(self):
        for mode in ("csv", "jpeg", "csv_jpeg"):
            keys = ("csv_data_rows",) if mode == "csv" else (
                ("images",) if mode == "jpeg" else ("csv_data_rows", "images")
            )
            for key in keys:
                with self.subTest(mode=mode, key=key):
                    configuration = self.configuration(export=mode)
                    trials = self.seven(configuration)
                    self.assertEqual(report.aggregate_trials(self.matrix, trials)["classification"],
                                     "complete")
                    trials[-1]["measurement"]["exports"][key] += 1
                    with self.assertRaises(report.ProtocolError):
                        report.aggregate_trials(self.matrix, trials)
                    self.assertEqual(report.build_report(self.matrix, trials)["classification"],
                                     "invalid")
        trials = self.seven(self.configuration(export="csv"))
        trials[-1]["measurement"]["exports"] = {
            "status": "unavailable", "reason": "not collected"
        }
        self.assertEqual(trials[-1]["status"], "completed")
        validation = report.validate_trial(trials[-1], self.matrix)
        self.assertFalse(validation["protocol_complete"])
        self.assertIn("exports", validation["missing_required_metrics"])
        result = report.aggregate_trials(self.matrix, trials)
        self.assertEqual(result["statistical_completeness"], "complete")
        self.assertEqual(result["protocol_completeness"], "partial")
        self.assertEqual(result["classification"], "partial")
        complete_coverage = []
        unavailable_id = next(c["id"] for c in self.configurations
                              if c["classification"] == "mandatory" and c["export_mode"] == "csv")
        for configuration in self.configurations:
            if configuration["classification"] == "mandatory":
                recorded = self.seven(configuration)
                if configuration["id"] == unavailable_id:
                    recorded[-1]["measurement"]["exports"] = {
                        "status": "unavailable", "reason": "not collected"
                    }
                complete_coverage.extend(recorded)
        overall = report.build_report(self.matrix, complete_coverage)
        self.assertEqual(overall["errors"], [])
        self.assertEqual(overall["missing_mandatory_configurations"], [])
        self.assertEqual(overall["classification"], "partial")

    def test_independent_canonical_sha256_vectors(self):
        vectors = (
            ({}, b"{}", "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"),
            ([], b"[]", "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"),
            ({"b": [True, None, "caf\u00e9"], "a": 1},
             b'{"a":1,"b":[true,null,"caf\\u00e9"]}', None),
        )
        for value, canonical, known_digest in vectors:
            with self.subTest(canonical=canonical):
                expected = known_digest or hashlib.sha256(canonical).hexdigest()
                self.assertEqual(report.canonical_json(value).encode("ascii"), canonical)
                self.assertEqual(report.canonical_sha256(value), expected)

    def test_json_size_limits(self):
        self.assertEqual(report.MAX_JSON_BYTES, 16 * 1024 * 1024)
        with mock.patch.object(report, "MAX_JSON_BYTES", 32):
            for size in (32, 33):
                with self.subTest(size=size):
                    raw = b"[]" + b" " * (size - 2)
                    with mock.patch.object(report.Path, "open", return_value=io.BytesIO(raw)):
                        if size == 32:
                            self.assertEqual(report.load_json("synthetic-input"), [])
                        else:
                            with self.assertRaises(report.ProtocolError):
                                report.load_json("synthetic-input")

    def test_latency_sample_limits(self):
        self.assertEqual(report.MAX_LATENCY_SAMPLES, 1_000_000)
        for limit, valid in ((4, True), (3, False)):
            with self.subTest(limit=limit), mock.patch.object(report, "MAX_LATENCY_SAMPLES", limit):
                trial = self.trial()
                if valid:
                    self.assertTrue(report.validate_trial(trial, self.matrix)["protocol_complete"])
                else:
                    with self.assertRaises(report.ProtocolError):
                        report.validate_trial(trial, self.matrix)
        trial = self.trial()
        trial["measurement"]["latency_ns"]["processing"]["samples_ns"] = []
        with self.assertRaises(report.ProtocolError):
            report.validate_trial(trial, self.matrix)

    def test_empty_trial_arrays(self):
        with self.assertRaises(report.ProtocolError):
            report.aggregate_trials(self.matrix, [])
        result = report.build_report(self.matrix, [])
        self.assertEqual(result["classification"], "partial")
        self.assertEqual(result["configurations"], [])
        self.assertEqual(len(result["missing_mandatory_configurations"]), 48)

    def test_invalid_trial_indices(self):
        for index in (0, 8, -1, 1.0, None):
            with self.subTest(index=index):
                trial = self.trial()
                trial["trial_index"] = index
                with self.assertRaises(report.ProtocolError):
                    report.validate_trial(trial, self.matrix)

    def test_failed_and_timed_out_trials(self):
        for status in ("failed", "timed_out"):
            with self.subTest(status=status):
                trials = self.seven()
                trials[-1]["status"] = status
                result = report.aggregate_trials(self.matrix, trials)
                self.assertEqual(result["classification"], "partial")
                self.assertEqual(result["statistical_completeness"], "partial")
                self.assertEqual(result["protocol_completeness"], "complete")
                self.assertEqual(result["completed_trial_count"], 6)
                self.assertEqual(len(result["trial_statistics"]), 6)
                self.assertEqual(result["noncompleted_trials"],
                                 [{"trial_index": 7, "status": status}])

    def test_malformed_nested_fields(self):
        cases = (
            (("provenance",), []),
            (("measurement",), None),
            (("measurement", "latency_ns"), []),
            (("measurement", "latency_ns", "processing"), None),
            (("measurement", "cpu"), None),
            (("measurement", "memory"), []),
            (("measurement", "threads"), None),
            (("measurement", "exports"), []),
            (("measurement", "allocation_copy"), None),
        )
        for path, value in cases:
            with self.subTest(path=path):
                trial = self.trial()
                target = trial
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with self.assertRaises(report.ProtocolError):
                    report.validate_trial(trial, self.matrix)
                self.assertEqual(report.build_report(self.matrix, [trial])["classification"],
                                 "invalid")
        for field in ("warmup", "thread_policy", "analysis_options"):
            with self.subTest(matrix_field=field):
                matrix = copy.deepcopy(self.matrix)
                matrix["protocol"][field] = None
                with self.assertRaises(report.ProtocolError):
                    report.validate_matrix(matrix)

    def test_even_count_provisional_median(self):
        result = report.aggregate_trials(self.matrix, self.seven()[:2])
        self.assertEqual(result["median_throughput"]["batches_per_second"], 3.0)
        self.assertEqual(result["statistical_completeness"], "partial")
        self.assertEqual(result["protocol_completeness"], "complete")
        self.assertEqual(result["classification"], "partial")

    def test_cli_exit_codes(self):
        complete = []
        for configuration in self.configurations:
            if configuration["classification"] == "mandatory":
                complete.extend(self.seven(configuration))
        invalid = self.seven()
        invalid[0]["matrix_sha256"] = "0" * 64
        for trials, classification, expected_code in (
            (complete, "complete", 0),
            (invalid, "invalid", 1),
            (self.seven(), "partial", 2),
        ):
            with self.subTest(classification=classification):
                with mock.patch.object(report, "load_json", side_effect=[self.matrix, trials]):
                    with mock.patch.object(report.sys, "stdout", new_callable=io.StringIO) as output:
                        code = report.main(["synthetic-matrix", "synthetic-trials"])
                self.assertEqual(code, expected_code)
                self.assertEqual(json.loads(output.getvalue())["classification"], classification)

    def test_nested_json_recursion_is_invalid(self):
        depth = report.sys.getrecursionlimit() + 100
        raw = b"[" * depth + b"0" + b"]" * depth
        with mock.patch.object(report.Path, "open", return_value=io.BytesIO(raw)):
            with self.assertRaises(report.ProtocolError) as caught:
                report.load_json("synthetic-input")
        self.assertIsInstance(caught.exception.__cause__, RecursionError)
        with mock.patch.object(report.Path, "open", return_value=io.BytesIO(raw)):
            with mock.patch.object(report.sys, "stdout", new_callable=io.StringIO) as output:
                code = report.main(["synthetic-matrix", "synthetic-trials"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue())["classification"], "invalid")

    def test_cli_recursion_errors_are_structured(self):
        for stage in ("load_json", "build_report"):
            with self.subTest(stage=stage):
                with mock.patch.object(report, "load_json", side_effect=[self.matrix, []]) as loader:
                    with mock.patch.object(report, "build_report") as builder:
                        failing = loader if stage == "load_json" else builder
                        failing.side_effect = RecursionError("synthetic CLI recursion")
                        with mock.patch.object(report.sys, "stdout", new_callable=io.StringIO) as output:
                            code = report.main(["synthetic-matrix", "synthetic-trials"])
                result = json.loads(output.getvalue())
                self.assertEqual(code, 1)
                self.assertEqual(result["classification"], "invalid")
                self.assertIn("synthetic CLI recursion", result["errors"][0]["message"])


if __name__ == "__main__":
    unittest.main()
