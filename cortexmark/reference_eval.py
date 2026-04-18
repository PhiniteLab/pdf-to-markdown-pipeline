"""Reference robustness benchmark runner for scholarly Markdown outputs.

Evaluates a small gold benchmark suite focused on:
  - citation mention extraction
  - bibliography/reference extraction
  - citation→reference link status correctness
  - missing / phantom / ambiguous audit behavior
  - scientific-object and RAG link propagation
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cortexmark.citations import CitationGraph
from cortexmark.citations import analyze_file as analyze_citations
from cortexmark.common import load_config, resolve_quality_report_path, setup_logging
from cortexmark.rag_export import parse_chunk_file

BENCHMARK_DEFAULT = Path("benchmarks/references")
LINK_STATUSES: tuple[str, ...] = ("resolved", "missing", "ambiguous")
AUDIT_FIELDS: tuple[str, ...] = ("missing_references", "phantom_references", "ambiguous_references")


@dataclass
class ReferenceEvalFailure:
    """One benchmark assertion failure."""

    case_id: str
    category: str
    expected: Any
    observed: Any
    message: str = ""


@dataclass
class ReferenceEvalCaseResult:
    """Evaluation result for a single benchmark case."""

    case_id: str
    document_id: str
    phenomena: list[str] = field(default_factory=list)
    passed: bool = True
    duration_ms: float = 0.0
    metrics: dict[str, float] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    failures: list[ReferenceEvalFailure] = field(default_factory=list)


@dataclass
class ReferenceEvalReport:
    """Top-level benchmark report."""

    benchmark_root: str
    manifest_path: str
    schema_path: str
    summary: dict[str, Any] = field(default_factory=dict)
    cases: list[ReferenceEvalCaseResult] = field(default_factory=list)
    failures: list[ReferenceEvalFailure] = field(default_factory=list)
    gate: dict[str, Any] = field(default_factory=dict)


def _normalize_string(value: Any) -> str:
    return str(value or "").strip()


def _normalize_gold_mentions(gold: dict[str, Any]) -> Counter[str]:
    mentions = gold.get("citation_mentions", [])
    return Counter(
        _normalize_string(item["raw_text"] if isinstance(item, dict) else item)
        for item in mentions
        if _normalize_string(item["raw_text"] if isinstance(item, dict) else item)
    )


def _normalize_pred_mentions(graph: CitationGraph) -> Counter[str]:
    return Counter(_normalize_string(cite.raw_text) for cite in graph.citations if _normalize_string(cite.raw_text))


def _normalize_gold_references(gold: dict[str, Any]) -> dict[str, dict[str, str]]:
    refs: dict[str, dict[str, str]] = {}
    for item in gold.get("references", []):
        if isinstance(item, str):
            refs[_normalize_string(item)] = {"reference_id": _normalize_string(item)}
            continue
        ref_id = _normalize_string(item.get("reference_id") or item.get("key"))
        if not ref_id:
            continue
        refs[ref_id] = {
            "reference_id": ref_id,
            "year": _normalize_string(item.get("year")),
            "title": _normalize_string(item.get("title")),
            "doi": _normalize_string(item.get("doi")).lower(),
        }
    return refs


def _normalize_pred_references(graph: CitationGraph) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    refs: dict[str, dict[str, str]] = {}
    ref_id_aliases: dict[str, str] = {}
    key_counts: Counter[str] = Counter()
    for ref in graph.references:
        base_id = _normalize_string(ref.key)
        if not base_id:
            continue
        key_counts[base_id] += 1
        eval_id = base_id if key_counts[base_id] == 1 else f"{base_id}-{key_counts[base_id]}"
        ref_id_aliases[_normalize_string(ref.reference_id)] = eval_id
        refs[eval_id] = {
            "reference_id": eval_id,
            "year": _normalize_string(ref.year),
            "title": _normalize_string(ref.title),
            "doi": _normalize_string(ref.doi).lower(),
        }
    return refs, ref_id_aliases


def _normalize_link_specs(items: list[dict[str, Any]] | list[Any]) -> Counter[tuple[str, str]]:
    specs: Counter[tuple[str, str]] = Counter()
    for item in items:
        if isinstance(item, dict):
            target_ref = _normalize_string(item.get("target_ref"))
            status = _normalize_string(item.get("status"))
        else:
            continue
        if target_ref and status:
            specs[(target_ref, status)] += 1
    return specs


def _normalize_pred_links(graph: CitationGraph) -> Counter[tuple[str, str]]:
    return Counter(
        (_normalize_string(edge.target_ref), _normalize_string(edge.status))
        for edge in graph.edges
        if _normalize_string(edge.target_ref) and _normalize_string(edge.status)
    )


def _normalize_scientific_assertions(items: list[dict[str, Any]] | list[Any]) -> set[tuple[str, str, str]]:
    assertions: set[tuple[str, str, str]] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        relation = _normalize_string(item.get("relation"))
        target_label = _normalize_string(item.get("target_label"))
        status = _normalize_string(item.get("status") or "resolved")
        if relation:
            assertions.add((relation, target_label, status))
    return assertions


def _aggregate_rag_predictions(input_path: Path) -> dict[str, Any]:
    records = [parse_chunk_file(input_path)]
    object_links = [
        (
            _normalize_string(link.get("relation")),
            _normalize_string(link.get("target_label")),
            _normalize_string(link.get("status") or "resolved"),
        )
        for record in records
        for link in record.metadata.get("object_links", [])
        if _normalize_string(link.get("relation"))
    ]
    parent_labels = (
        {
            _normalize_string(record.metadata.get("parent_label"))
            for record in records
            if _normalize_string(record.metadata.get("parent_label"))
        }
        | {
            _normalize_string(link.get("target_label"))
            for record in records
            for link in record.metadata.get("object_links", [])
            if _normalize_string(link.get("target_label"))
        }
        | {
            _normalize_string(obj.get("metadata", {}).get("parent_label"))
            for record in records
            for obj in record.metadata.get("scientific_objects", [])
            if _normalize_string(obj.get("metadata", {}).get("parent_label"))
        }
    )
    cross_ref_statuses = {
        _normalize_string(link.get("status"))
        for record in records
        for link in record.metadata.get("cross_ref_links", [])
        if _normalize_string(link.get("status"))
    }
    scientific_object_ids = sorted(
        {
            _normalize_string(object_id)
            for record in records
            for object_id in record.metadata.get("scientific_object_ids", [])
            if _normalize_string(object_id)
        }
    )
    object_link_ids = sorted(
        {
            "||".join(
                [
                    _normalize_string(link.get("source_object_id")),
                    _normalize_string(link.get("target_object_id")),
                    _normalize_string(link.get("relation")),
                    _normalize_string(link.get("status")),
                ]
            )
            for record in records
            for link in record.metadata.get("object_links", [])
            if _normalize_string(link.get("relation"))
        }
    )
    return {
        "records": records,
        "object_links": set(object_links),
        "parent_labels": parent_labels,
        "cross_ref_statuses": cross_ref_statuses,
        "scientific_object_ids": scientific_object_ids,
        "object_link_ids": object_link_ids,
    }


def _precision(tp: int, fp: int) -> float:
    return 1.0 if tp == 0 and fp == 0 else tp / max(tp + fp, 1)


def _recall(tp: int, fn: int) -> float:
    return 1.0 if tp == 0 and fn == 0 else tp / max(tp + fn, 1)


def _f1(tp: int, fp: int, fn: int) -> float:
    precision = _precision(tp, fp)
    recall = _recall(tp, fn)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _status_metrics(
    gold_links: Counter[tuple[str, str]],
    pred_links: Counter[tuple[str, str]],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for status in LINK_STATUSES:
        keys = {item for item in gold_links if item[1] == status} | {item for item in pred_links if item[1] == status}
        tp = fp = fn = 0
        for key in keys:
            gold_count = gold_links.get(key, 0)
            pred_count = pred_links.get(key, 0)
            tp += min(gold_count, pred_count)
            fp += max(pred_count - gold_count, 0)
            fn += max(gold_count - pred_count, 0)
        counts[f"{status}_tp"] = tp
        counts[f"{status}_fp"] = fp
        counts[f"{status}_fn"] = fn
    return counts


def _compare_set(
    *,
    case_id: str,
    category: str,
    gold: set[Any],
    predicted: set[Any],
) -> tuple[list[ReferenceEvalFailure], dict[str, int]]:
    failures: list[ReferenceEvalFailure] = []
    missing_items = sorted(gold - predicted)
    extra_items = sorted(predicted - gold)
    for item in missing_items:
        failures.append(
            ReferenceEvalFailure(
                case_id=case_id,
                category=category,
                expected=item,
                observed=None,
                message="expected item missing from prediction",
            )
        )
    for item in extra_items:
        failures.append(
            ReferenceEvalFailure(
                case_id=case_id,
                category=category,
                expected=None,
                observed=item,
                message="unexpected predicted item",
            )
        )
    return failures, {"tp": len(gold & predicted), "fp": len(extra_items), "fn": len(missing_items)}


def _compare_counter(
    *,
    case_id: str,
    category: str,
    gold: Counter[Any],
    predicted: Counter[Any],
) -> tuple[list[ReferenceEvalFailure], dict[str, int]]:
    failures: list[ReferenceEvalFailure] = []
    keys = set(gold) | set(predicted)
    tp = fp = fn = 0
    for key in sorted(keys):
        gold_count = gold.get(key, 0)
        predicted_count = predicted.get(key, 0)
        if gold_count == predicted_count:
            tp += gold_count
            continue
        tp += min(gold_count, predicted_count)
        if gold_count > predicted_count:
            fn += gold_count - predicted_count
            failures.append(
                ReferenceEvalFailure(
                    case_id=case_id,
                    category=category,
                    expected={key: gold_count},
                    observed={key: predicted_count},
                    message="predicted count below gold count",
                )
            )
        else:
            fp += predicted_count - gold_count
            failures.append(
                ReferenceEvalFailure(
                    case_id=case_id,
                    category=category,
                    expected={key: gold_count},
                    observed={key: predicted_count},
                    message="predicted count above gold count",
                )
            )
    return failures, {"tp": tp, "fp": fp, "fn": fn}


def validate_gold_case(gold: dict[str, Any], schema: dict[str, Any], *, case_id: str = "") -> None:
    """Enforce the benchmark gold schema without requiring external jsonschema."""
    required = schema.get("required", [])
    for key in required:
        if key not in gold:
            raise ValueError(f"benchmark case {case_id or '<unknown>'}: missing required field '{key}'")

    properties = schema.get("properties", {})
    type_map = {
        "object": dict,
        "array": list,
        "string": str,
    }
    for key, spec in properties.items():
        if key not in gold:
            continue
        declared_type = spec.get("type")
        expected_type = type_map.get(declared_type)
        if expected_type is not None and not isinstance(gold[key], expected_type):
            raise ValueError(
                f"benchmark case {case_id or '<unknown>'}: field '{key}' must be {declared_type}, "
                f"got {type(gold[key]).__name__}"
            )

    phenomena = gold.get("phenomena", [])
    if not all(isinstance(item, str) for item in phenomena):
        raise ValueError(f"benchmark case {case_id or '<unknown>'}: 'phenomena' must be an array of strings")

    if not isinstance(gold.get("citation_audit", {}), dict):
        raise ValueError(f"benchmark case {case_id or '<unknown>'}: 'citation_audit' must be an object")
    for audit_field in AUDIT_FIELDS:
        audit_values = gold.get("citation_audit", {}).get(audit_field, [])
        if not isinstance(audit_values, list) or not all(isinstance(item, str) for item in audit_values):
            raise ValueError(f"benchmark case {case_id or '<unknown>'}: '{audit_field}' must be an array of strings")

    for link in gold.get("citation_links", []):
        if not isinstance(link, dict) or "target_ref" not in link or "status" not in link:
            raise ValueError(f"benchmark case {case_id or '<unknown>'}: invalid citation_links entry")
        if not isinstance(link["target_ref"], str) or not isinstance(link["status"], str):
            raise ValueError(f"benchmark case {case_id or '<unknown>'}: citation_links values must be strings")

    for assertion in gold.get("scientific_link_assertions", []):
        if not isinstance(assertion, dict) or "relation" not in assertion:
            raise ValueError(f"benchmark case {case_id or '<unknown>'}: invalid scientific_link_assertions entry")
        for field_name in ("relation", "target_label", "status"):
            if field_name in assertion and not isinstance(assertion[field_name], str):
                raise ValueError(
                    f"benchmark case {case_id or '<unknown>'}: scientific_link_assertions '{field_name}' must be string"
                )

    for item in gold.get("citation_mentions", []):
        if isinstance(item, str):
            continue
        if not isinstance(item, dict) or "raw_text" not in item or not isinstance(item["raw_text"], str):
            raise ValueError(f"benchmark case {case_id or '<unknown>'}: invalid citation_mentions entry")

    for item in gold.get("references", []):
        if isinstance(item, str):
            continue
        if not isinstance(item, dict) or "reference_id" not in item or not isinstance(item["reference_id"], str):
            raise ValueError(f"benchmark case {case_id or '<unknown>'}: invalid references entry")
        for field_name in ("year", "title", "doi"):
            if field_name in item and not isinstance(item[field_name], str):
                raise ValueError(f"benchmark case {case_id or '<unknown>'}: references '{field_name}' must be string")

    rag_assertions = gold.get("rag_assertions", {})
    if not isinstance(rag_assertions, dict):
        raise ValueError(f"benchmark case {case_id or '<unknown>'}: 'rag_assertions' must be an object")
    for field_name in ("required_parent_labels", "required_object_link_relations", "required_cross_ref_statuses"):
        values = rag_assertions.get(field_name, [])
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise ValueError(f"benchmark case {case_id or '<unknown>'}: '{field_name}' must be an array of strings")


def load_manifest(benchmark_root: Path) -> dict[str, Any]:
    """Load benchmark manifest JSON."""
    return json.loads((benchmark_root / "manifest.json").read_text(encoding="utf-8"))


def load_schema(benchmark_root: Path) -> dict[str, Any]:
    """Load benchmark schema JSON."""
    return json.loads((benchmark_root / "schema.json").read_text(encoding="utf-8"))


def load_baseline(baseline_path: Path) -> dict[str, Any]:
    """Load benchmark baseline JSON."""
    return json.loads(baseline_path.read_text(encoding="utf-8"))


def evaluate_baseline_gate(
    report: ReferenceEvalReport,
    manifest: dict[str, Any],
    baseline: dict[str, Any],
    *,
    baseline_path: Path,
) -> dict[str, Any]:
    """Evaluate benchmark summary against a stored baseline contract."""
    failed_checks: list[str] = []
    warnings: list[str] = []

    manifest_case_ids = [
        _normalize_string(case.get("case_id"))
        for case in manifest.get("cases", [])
        if _normalize_string(case.get("case_id"))
    ]
    if baseline.get("benchmark_name") and baseline.get("benchmark_name") != manifest.get("benchmark_name"):
        failed_checks.append("baseline benchmark_name does not match manifest benchmark_name")
    if baseline.get("benchmark_version") is not None and baseline.get("benchmark_version") != manifest.get("version"):
        failed_checks.append("baseline benchmark_version does not match manifest version")
    if baseline.get("manifest_case_count") is not None and baseline.get("manifest_case_count") != len(
        manifest_case_ids
    ):
        failed_checks.append("baseline manifest_case_count is stale relative to manifest.json")
    if baseline.get("manifest_case_ids") is not None and baseline.get("manifest_case_ids") != manifest_case_ids:
        failed_checks.append("baseline manifest_case_ids differ from manifest.json")

    summary = report.summary
    for threshold_key, threshold_value in baseline.get("summary_thresholds", {}).items():
        if threshold_key.endswith("_min"):
            metric_name = threshold_key[: -len("_min")]
            observed = summary.get(metric_name)
            if observed is None:
                failed_checks.append(f"missing summary metric '{metric_name}' required by baseline")
            elif observed < threshold_value:
                failed_checks.append(f"{metric_name}={observed} below minimum {threshold_value}")
        elif threshold_key.endswith("_max"):
            metric_name = threshold_key[: -len("_max")]
            observed = summary.get(metric_name)
            if observed is None:
                failed_checks.append(f"missing summary metric '{metric_name}' required by baseline")
            elif observed > threshold_value:
                failed_checks.append(f"{metric_name}={observed} above maximum {threshold_value}")
        else:
            failed_checks.append(f"unsupported baseline threshold key '{threshold_key}'")

    for warning_key, threshold_value in baseline.get("report_only_metrics", {}).items():
        if warning_key.endswith("_warn_if_above"):
            metric_name = warning_key[: -len("_warn_if_above")]
            observed = summary.get(metric_name)
            if observed is not None and observed > threshold_value:
                warnings.append(f"{metric_name}={observed} above warning threshold {threshold_value}")
        elif warning_key.endswith("_warn_if_below"):
            metric_name = warning_key[: -len("_warn_if_below")]
            observed = summary.get(metric_name)
            if observed is not None and observed < threshold_value:
                warnings.append(f"{metric_name}={observed} below warning threshold {threshold_value}")
        else:
            warnings.append(f"unsupported report_only_metrics key '{warning_key}'")

    return {
        "enabled": True,
        "passed": not failed_checks,
        "baseline_path": str(baseline_path),
        "failed_checks": failed_checks,
        "warnings": warnings,
    }


def evaluate_case(case_id: str, case_dir: Path, gold: dict[str, Any]) -> ReferenceEvalCaseResult:
    """Evaluate a single benchmark case directory."""
    start = time.perf_counter()
    input_path = case_dir / "input.md"
    graph = analyze_citations(input_path)
    rag_predictions = _aggregate_rag_predictions(input_path)

    second_graph = analyze_citations(input_path)
    second_rag_predictions = _aggregate_rag_predictions(input_path)

    failures: list[ReferenceEvalFailure] = []
    counts: dict[str, int] = {}

    gold_mentions = _normalize_gold_mentions(gold)
    pred_mentions = _normalize_pred_mentions(graph)
    mention_failures, mention_counts = _compare_counter(
        case_id=case_id,
        category="citation_mentions",
        gold=gold_mentions,
        predicted=pred_mentions,
    )
    failures.extend(mention_failures)
    counts.update({f"mention_{key}": value for key, value in mention_counts.items()})

    gold_refs = _normalize_gold_references(gold)
    pred_refs, pred_ref_aliases = _normalize_pred_references(graph)
    ref_failures, ref_counts = _compare_set(
        case_id=case_id,
        category="references",
        gold=set(gold_refs),
        predicted=set(pred_refs),
    )
    failures.extend(ref_failures)
    counts.update({f"reference_{key}": value for key, value in ref_counts.items()})

    for field_name in ("year", "title", "doi"):
        gold_with_field = {ref_id: ref for ref_id, ref in gold_refs.items() if _normalize_string(ref.get(field_name))}
        match_count = 0
        for ref_id, ref in gold_with_field.items():
            predicted = pred_refs.get(ref_id)
            if predicted and _normalize_string(predicted.get(field_name)) == _normalize_string(ref.get(field_name)):
                match_count += 1
            elif predicted:
                failures.append(
                    ReferenceEvalFailure(
                        case_id=case_id,
                        category=f"reference_field:{field_name}",
                        expected={ref_id: ref.get(field_name)},
                        observed={ref_id: predicted.get(field_name)},
                        message="reference field mismatch",
                    )
                )
        counts[f"{field_name}_matches"] = match_count
        counts[f"{field_name}_total"] = len(gold_with_field)

    gold_links = _normalize_link_specs(gold.get("citation_links", []))
    pred_links = _normalize_pred_links(graph)
    link_failures, link_counts = _compare_counter(
        case_id=case_id,
        category="citation_links",
        gold=gold_links,
        predicted=pred_links,
    )
    failures.extend(link_failures)
    counts.update({f"link_{key}": value for key, value in link_counts.items()})
    counts.update(_status_metrics(gold_links, pred_links))

    resolved_gold = Counter({item: count for item, count in gold_links.items() if item[1] == "resolved"})
    resolved_pred = Counter({item: count for item, count in pred_links.items() if item[1] == "resolved"})
    counts["resolved_link_matches"] = sum(
        min(resolved_gold.get(item, 0), resolved_pred.get(item, 0)) for item in set(resolved_gold) | set(resolved_pred)
    )
    counts["resolved_link_total"] = sum(resolved_gold.values())
    counts["false_resolve_count"] = sum(
        max(resolved_pred.get(item, 0) - resolved_gold.get(item, 0), 0) for item in resolved_pred
    )
    counts["predicted_resolved_total"] = sum(resolved_pred.values())

    for audit_field in AUDIT_FIELDS:
        gold_audit = {
            _normalize_string(item)
            for item in gold.get("citation_audit", {}).get(audit_field, [])
            if _normalize_string(item)
        }
        raw_pred_audit = {
            _normalize_string(item) for item in getattr(graph.audit, audit_field, []) if _normalize_string(item)
        }
        pred_audit = {pred_ref_aliases.get(item, item) for item in raw_pred_audit}
        audit_failures, audit_counts = _compare_set(
            case_id=case_id,
            category=f"audit:{audit_field}",
            gold=gold_audit,
            predicted=pred_audit,
        )
        failures.extend(audit_failures)
        counts.update({f"{audit_field}_{key}": value for key, value in audit_counts.items()})

    gold_scientific = _normalize_scientific_assertions(gold.get("scientific_link_assertions", []))
    pred_scientific = rag_predictions["object_links"]
    scientific_failures, scientific_counts = _compare_set(
        case_id=case_id,
        category="scientific_links",
        gold=gold_scientific,
        predicted=pred_scientific,
    )
    failures.extend(scientific_failures)
    counts.update({f"scientific_link_{key}": value for key, value in scientific_counts.items()})

    rag_assertions = gold.get("rag_assertions", {})
    required_parent_labels = {
        _normalize_string(item) for item in rag_assertions.get("required_parent_labels", []) if _normalize_string(item)
    }
    found_parent_labels = {item for item in rag_predictions["parent_labels"] if item}
    parent_failures, parent_counts = _compare_set(
        case_id=case_id,
        category="rag_parent_labels",
        gold=required_parent_labels,
        predicted=found_parent_labels & required_parent_labels,
    )
    failures.extend(parent_failures)
    counts.update({f"parent_link_{key}": value for key, value in parent_counts.items()})

    required_relations = {
        _normalize_string(item)
        for item in rag_assertions.get("required_object_link_relations", [])
        if _normalize_string(item)
    }
    found_relations = {
        relation for relation, _, _ in rag_predictions["object_links"] if relation and relation in required_relations
    }
    relation_failures, relation_counts = _compare_set(
        case_id=case_id,
        category="rag_object_link_relations",
        gold=required_relations,
        predicted=found_relations,
    )
    failures.extend(relation_failures)
    counts.update({f"rag_relation_{key}": value for key, value in relation_counts.items()})

    required_cross_ref_statuses = {
        _normalize_string(item)
        for item in rag_assertions.get("required_cross_ref_statuses", [])
        if _normalize_string(item)
    }
    found_cross_ref_statuses = rag_predictions["cross_ref_statuses"] & required_cross_ref_statuses
    cross_ref_failures, cross_ref_counts = _compare_set(
        case_id=case_id,
        category="rag_cross_ref_statuses",
        gold=required_cross_ref_statuses,
        predicted=found_cross_ref_statuses,
    )
    failures.extend(cross_ref_failures)
    counts.update({f"rag_cross_ref_{key}": value for key, value in cross_ref_counts.items()})

    ids_stable = (
        [cite.mention_id for cite in graph.citations] == [cite.mention_id for cite in second_graph.citations]
        and [ref.reference_id for ref in graph.references] == [ref.reference_id for ref in second_graph.references]
        and rag_predictions["scientific_object_ids"] == second_rag_predictions["scientific_object_ids"]
        and rag_predictions["object_link_ids"] == second_rag_predictions["object_link_ids"]
    )
    counts["id_stability_matches"] = 1 if ids_stable else 0
    counts["id_stability_total"] = 1
    if not ids_stable:
        failures.append(
            ReferenceEvalFailure(
                case_id=case_id,
                category="id_stability",
                expected="deterministic ids across reruns",
                observed="changed ids across reruns",
                message="identifier stability regression",
            )
        )

    duration_ms = round((time.perf_counter() - start) * 1000, 3)
    counts["runtime_ms"] = round(duration_ms)
    metrics = {
        "mention_precision": round(_precision(counts["mention_tp"], counts["mention_fp"]), 4),
        "mention_recall": round(_recall(counts["mention_tp"], counts["mention_fn"]), 4),
        "mention_f1": round(_f1(counts["mention_tp"], counts["mention_fp"], counts["mention_fn"]), 4),
        "reference_precision": round(_precision(counts["reference_tp"], counts["reference_fp"]), 4),
        "reference_recall": round(_recall(counts["reference_tp"], counts["reference_fn"]), 4),
        "reference_f1": round(_f1(counts["reference_tp"], counts["reference_fp"], counts["reference_fn"]), 4),
        "scientific_link_f1": round(
            _f1(
                counts["scientific_link_tp"],
                counts["scientific_link_fp"],
                counts["scientific_link_fn"],
            ),
            4,
        ),
        "rag_reference_propagation_recall": round(
            _recall(
                counts["rag_relation_tp"] + counts["parent_link_tp"],
                counts["rag_relation_fn"] + counts["parent_link_fn"],
            ),
            4,
        ),
        "parent_link_accuracy": round(_recall(counts["parent_link_tp"], counts["parent_link_fn"]), 4),
        "id_stability_rate": 1.0 if ids_stable else 0.0,
    }
    return ReferenceEvalCaseResult(
        case_id=case_id,
        document_id=_normalize_string(gold.get("document_id") or case_id),
        phenomena=[_normalize_string(item) for item in gold.get("phenomena", []) if _normalize_string(item)],
        passed=not failures,
        duration_ms=duration_ms,
        metrics=metrics,
        counts=counts,
        failures=failures,
    )


def build_summary(case_results: list[ReferenceEvalCaseResult]) -> dict[str, Any]:
    """Aggregate case-level benchmark results into a top-level summary."""
    total_cases = len(case_results)
    counts: dict[str, int] = {}
    for result in case_results:
        for key, value in result.counts.items():
            counts[key] = counts.get(key, 0) + value

    link_macro_f1 = 1.0
    if total_cases:
        per_status = []
        for status in LINK_STATUSES:
            tp = counts.get(f"{status}_tp", 0)
            fp = counts.get(f"{status}_fp", 0)
            fn = counts.get(f"{status}_fn", 0)
            per_status.append(_f1(tp, fp, fn))
        link_macro_f1 = sum(per_status) / len(per_status)

    summary = {
        "total_cases": total_cases,
        "passed_cases": sum(1 for result in case_results if result.passed),
        "failed_cases": sum(1 for result in case_results if not result.passed),
        "mention_precision": round(_precision(counts.get("mention_tp", 0), counts.get("mention_fp", 0)), 4),
        "mention_recall": round(_recall(counts.get("mention_tp", 0), counts.get("mention_fn", 0)), 4),
        "mention_f1": round(
            _f1(counts.get("mention_tp", 0), counts.get("mention_fp", 0), counts.get("mention_fn", 0)), 4
        ),
        "reference_precision": round(
            _precision(counts.get("reference_tp", 0), counts.get("reference_fp", 0)),
            4,
        ),
        "reference_recall": round(
            _recall(counts.get("reference_tp", 0), counts.get("reference_fn", 0)),
            4,
        ),
        "reference_f1": round(
            _f1(counts.get("reference_tp", 0), counts.get("reference_fp", 0), counts.get("reference_fn", 0)),
            4,
        ),
        "doi_accuracy": round(
            counts.get("doi_matches", 0) / max(counts.get("doi_total", 0), 1),
            4,
        ),
        "year_accuracy": round(
            counts.get("year_matches", 0) / max(counts.get("year_total", 0), 1),
            4,
        ),
        "title_accuracy": round(
            counts.get("title_matches", 0) / max(counts.get("title_total", 0), 1),
            4,
        ),
        "link_status_macro_f1": round(link_macro_f1, 4),
        "resolved_link_accuracy": round(
            counts.get("resolved_link_matches", 0) / max(counts.get("resolved_link_total", 0), 1),
            4,
        ),
        "false_resolve_rate": round(
            counts.get("false_resolve_count", 0) / max(counts.get("predicted_resolved_total", 0), 1),
            4,
        ),
        "scientific_link_f1": round(
            _f1(
                counts.get("scientific_link_tp", 0),
                counts.get("scientific_link_fp", 0),
                counts.get("scientific_link_fn", 0),
            ),
            4,
        ),
        "rag_reference_propagation_recall": round(
            _recall(
                counts.get("rag_relation_tp", 0) + counts.get("parent_link_tp", 0),
                counts.get("rag_relation_fn", 0) + counts.get("parent_link_fn", 0),
            ),
            4,
        ),
        "parent_link_accuracy": round(
            _recall(counts.get("parent_link_tp", 0), counts.get("parent_link_fn", 0)),
            4,
        ),
        "id_stability_rate": round(
            counts.get("id_stability_matches", 0) / max(counts.get("id_stability_total", 0), 1),
            4,
        ),
        "total_eval_runtime_s": round(counts.get("runtime_ms", 0) / 1000.0, 4),
        "avg_runtime_ms_per_case": round(counts.get("runtime_ms", 0) / max(total_cases, 1), 3),
    }

    for audit_field in AUDIT_FIELDS:
        summary[f"{audit_field}_precision"] = round(
            _precision(counts.get(f"{audit_field}_tp", 0), counts.get(f"{audit_field}_fp", 0)),
            4,
        )
        summary[f"{audit_field}_recall"] = round(
            _recall(counts.get(f"{audit_field}_tp", 0), counts.get(f"{audit_field}_fn", 0)),
            4,
        )
    return summary


def evaluate_benchmark(benchmark_root: Path) -> ReferenceEvalReport:
    """Run the full benchmark suite under ``benchmark_root``."""
    manifest = load_manifest(benchmark_root)
    schema = load_schema(benchmark_root)

    case_results: list[ReferenceEvalCaseResult] = []
    failures: list[ReferenceEvalFailure] = []
    for case_entry in manifest.get("cases", []):
        case_id = _normalize_string(case_entry.get("case_id"))
        if not case_id:
            continue
        case_dir = benchmark_root / "cases" / case_id
        gold = json.loads((case_dir / "gold.json").read_text(encoding="utf-8"))
        validate_gold_case(gold, schema, case_id=case_id)
        result = evaluate_case(case_id, case_dir, gold)
        case_results.append(result)
        failures.extend(result.failures)

    return ReferenceEvalReport(
        benchmark_root=str(benchmark_root),
        manifest_path=str((benchmark_root / "manifest.json").resolve()),
        schema_path=str((benchmark_root / "schema.json").resolve()),
        summary=build_summary(case_results),
        cases=case_results,
        failures=failures,
    )


def write_json_report(report: ReferenceEvalReport, output_path: Path) -> Path:
    """Write benchmark results as JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "benchmark_root": report.benchmark_root,
        "manifest_path": report.manifest_path,
        "schema_path": report.schema_path,
        "summary": report.summary,
        "cases": [asdict(case) for case in report.cases],
        "failures": [asdict(failure) for failure in report.failures],
        "gate": report.gate,
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output_path


def write_failures_jsonl(failures: list[ReferenceEvalFailure], output_path: Path) -> Path:
    """Write failures as JSONL for machine-friendly debugging."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for failure in failures:
            fh.write(json.dumps(asdict(failure), ensure_ascii=False) + "\n")
    return output_path


def write_markdown_report(report: ReferenceEvalReport, output_path: Path) -> Path:
    """Write a compact human-readable benchmark scorecard."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary = report.summary
    lines = [
        "# Reference Robustness Benchmark",
        "",
        f"- Benchmark root: `{report.benchmark_root}`",
        f"- Cases: **{summary['total_cases']}**",
        f"- Passed: **{summary['passed_cases']}**",
        f"- Failed: **{summary['failed_cases']}**",
        f"- False resolve rate: **{summary['false_resolve_rate']:.4f}**",
        f"- ID stability rate: **{summary['id_stability_rate']:.4f}**",
        "",
        "## Summary metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key in (
        "mention_f1",
        "reference_f1",
        "link_status_macro_f1",
        "resolved_link_accuracy",
        "scientific_link_f1",
        "rag_reference_propagation_recall",
        "parent_link_accuracy",
        "doi_accuracy",
        "year_accuracy",
        "title_accuracy",
        "avg_runtime_ms_per_case",
    ):
        lines.append(f"| {key} | {summary[key]} |")

    lines.extend(["", "## Cases", "", "| Case | Passed | Runtime (ms) | Phenomena |", "|---|---:|---:|---|"])
    for case in report.cases:
        phenomena = ", ".join(case.phenomena)
        lines.append(f"| {case.case_id} | {'yes' if case.passed else 'no'} | {case.duration_ms:.3f} | {phenomena} |")

    if report.failures:
        lines.extend(["", "## Failures", ""])
        for failure in report.failures[:20]:
            lines.append(
                f"- **{failure.case_id} / {failure.category}** — expected `{failure.expected}`, observed `{failure.observed}`"
            )
    else:
        lines.extend(["", "## Failures", "", "- None."])

    if report.gate.get("enabled"):
        lines.extend(
            [
                "",
                "## Baseline gate",
                "",
                f"- Passed: **{'yes' if report.gate.get('passed') else 'no'}**",
                f"- Baseline: `{report.gate.get('baseline_path', '')}`",
            ]
        )
        if report.gate.get("failed_checks"):
            lines.append("- Failed checks:")
            for item in report.gate["failed_checks"]:
                lines.append(f"  - {item}")
        if report.gate.get("warnings"):
            lines.append("- Warnings:")
            for item in report.gate["warnings"]:
                lines.append(f"  - {item}")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the reference robustness benchmark suite.")
    parser.add_argument(
        "--benchmarks",
        type=Path,
        default=BENCHMARK_DEFAULT,
        help="Path to benchmark root (default: benchmarks/references)",
    )
    parser.add_argument("--output", type=Path, help="Path for JSON summary report")
    parser.add_argument("--markdown", type=Path, help="Path for Markdown scorecard")
    parser.add_argument("--failures", type=Path, help="Path for failures JSONL")
    parser.add_argument("--baseline", type=Path, help="Optional baseline contract JSON to enforce")
    parser.add_argument("--config", type=Path, help="Path to pipeline.yaml")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    cfg = load_config(args.config)
    log = setup_logging("reference_eval", cfg)
    benchmark_root = args.benchmarks.resolve()
    json_output = (args.output or resolve_quality_report_path(cfg, "reference_eval.json")).resolve()
    markdown_output = (args.markdown or resolve_quality_report_path(cfg, "reference_eval.md")).resolve()
    failures_output = (args.failures or resolve_quality_report_path(cfg, "reference_eval_failures.jsonl")).resolve()
    baseline_path = args.baseline.resolve() if args.baseline else None

    try:
        report = evaluate_benchmark(benchmark_root)
        if baseline_path is not None:
            baseline = load_baseline(baseline_path)
            manifest = load_manifest(benchmark_root)
            report.gate = evaluate_baseline_gate(report, manifest, baseline, baseline_path=baseline_path)
        write_json_report(report, json_output)
        write_markdown_report(report, markdown_output)
        write_failures_jsonl(report.failures, failures_output)
        log.info(
            "reference benchmark: %d/%d cases passed → %s",
            report.summary.get("passed_cases", 0),
            report.summary.get("total_cases", 0),
            json_output,
        )
        if report.gate.get("enabled"):
            if report.gate.get("warnings"):
                for item in report.gate["warnings"]:
                    log.warning("baseline warning: %s", item)
            if not report.gate.get("passed", False):
                for item in report.gate["failed_checks"]:
                    log.error("baseline check failed: %s", item)
                return 2
    except FileNotFoundError as exc:
        log.error("file not found: %s", exc)
        return 1
    except json.JSONDecodeError as exc:
        log.error("invalid benchmark json: %s", exc)
        return 1
    except ValueError as exc:
        log.error("invalid benchmark fixture: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
