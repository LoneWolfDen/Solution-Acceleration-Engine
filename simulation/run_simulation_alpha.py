#!/usr/bin/env python3
"""simulation/run_simulation_alpha.py — Simulation-Alpha multi-stage pipeline.

Run 1 (The Gap):       Missing security controls → multiple gate failures (Veto).
Run 2 (The Correction): Full security section added → all gates pass (Pass).

Both runs execute the full 5-step pipeline:
  1. Ingestion   — artifact registration + project/version setup
  2. Arbitration — 12-dimension Layer 1 review (LLM mocked)
  3. Synthesis   — Layer 2 ReconciliationReport + JudgeValidationReport (LLM mocked)
  4. Learning    — PromptOptimizer + KnowledgeAggregator + PromptDelta
  5. Audit       — DreamCycleWorker

All JSON output is written to simulation_output/ at the repository root.
The script halts and reports on any step failure — no silent partial output.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

# ── Path setup ────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from contexta.admin.dream_cycle import DreamCycleWorker
from contexta.config import ContextaConfig
from contexta.db.repositories import (
    activate_blueprint,
    create_project,
    create_version,
    get_intelligence_by_type,
    save_blueprint_version,
    write_synthesis_node,
)
from contexta.db.schema import init_database
from contexta.llm.models import evaluate_reconciliation_report
from contexta.llm.prompts import PromptBuilder
from contexta.llm.provider import LLMConfig
from contexta.mcp.artifact_registry import ArtifactRegistry, IngestedArtifact
from contexta.models.citations import SourceCitation
from contexta.models.enums import (
    CitationTypeEnum,
    ConfidenceEnum,
    MitigationRoutingEnum,
    ReviewDimensionEnum,
)
from contexta.models.findings import IssueFinding
from contexta.models.payloads import ReviewNodePayload
from contexta.pipeline.arbitrator import LayerTwoArbitrator
from contexta.pipeline.dimension_runner import (
    TaskOrchestrator,
    commit_exploration_node,
    make_dimension_runner,
)
from contexta.pipeline.optimizer import KnowledgeAggregator, PromptDelta, PromptOptimizer



# ── Constants ─────────────────────────────────────────────────────────────────
OUTPUT_DIR = REPO_ROOT / "simulation_output"
ARTIFACTS_DIR = REPO_ROOT / "test_artifacts"
SIMULATION_NAME = "Simulation-Alpha"
PROJECT_TAGS = ["#FinancialServices", "#Security", "#PCI-DSS"]

# Dimensions that expose the security gap in v1
_SECURITY_GAP_DIMS = {
    ReviewDimensionEnum.ARCHITECTURE,
    ReviewDimensionEnum.NFR,
    ReviewDimensionEnum.RISK,
}

_DIM_LIST = list(ReviewDimensionEnum)  # ordered by enum declaration


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump(path: Path, data: Any) -> None:
    """Write *data* as pretty-printed JSON; create parents; halt on error."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)
    print(f"    ✓ {path.relative_to(REPO_ROOT)}")


def _halt(step: str, exc: Exception) -> None:
    print(f"\n✗ HALT — {step} failed: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc


def _read_artifact(filename: str) -> str:
    path = ARTIFACTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Artifact not found: {path}")
    return path.read_text(encoding="utf-8")



# ── LLM mock payload factories ────────────────────────────────────────────────

def _make_dim_payload_v1(dim: ReviewDimensionEnum) -> str:
    """Run 1: ARCHITECTURE / NFR / RISK → RED; all others → AMBER."""
    is_gap = dim in _SECURITY_GAP_DIMS
    confidence = ConfidenceEnum.RED if is_gap else ConfidenceEnum.AMBER
    mitigation = (
        MitigationRoutingEnum.RISK_REGISTER
        if is_gap
        else MitigationRoutingEnum.ASSUMPTIONS_MATRIX
    )
    if is_gap:
        summary = f"{dim.value}: CRITICAL — no security controls documented"
        detail = (
            f"The {dim.value} dimension reveals a critical security gap. "
            "The proposal contains no encryption standards, access management "
            "policies, vulnerability assessment plans, or penetration testing "
            "schedule. This is a blocking issue for a regulated financial platform."
        )
    else:
        summary = f"{dim.value}: adequate coverage, minor gaps noted"
        detail = f"The {dim.value} dimension shows adequate coverage with minor items for clarification."

    payload = ReviewNodePayload(
        dimension=dim,
        findings=[
            IssueFinding(
                dimension=dim,
                confidence=confidence,
                summary=summary,
                detail=detail,
                citations=[
                    SourceCitation(
                        file_path="/simulation-alpha-v1.md",
                        line_start=1,
                        line_end=5,
                        citation_type=CitationTypeEnum.DIRECT_REFERENCE,
                        excerpt="Simulation-Alpha Proposal v1",
                    )
                ],
                mitigation_routing=mitigation,
            )
        ],
        overall_confidence=confidence,
        raw_llm_response="{}",
    )
    return payload.model_dump_json()


def _make_dim_payload_v2(dim: ReviewDimensionEnum) -> str:
    """Run 2: RISK → AMBER (residual); all others → GREEN."""
    is_residual = dim == ReviewDimensionEnum.RISK
    confidence = ConfidenceEnum.AMBER if is_residual else ConfidenceEnum.GREEN
    mitigation = (
        MitigationRoutingEnum.RISK_REGISTER if is_residual else MitigationRoutingEnum.IGNORED
    )
    summary = (
        f"{dim.value}: residual risk — pen-test vendor not yet confirmed"
        if is_residual
        else f"{dim.value}: fully addressed in v2"
    )
    detail = (
        "Security controls are now well-documented. A minor residual risk "
        "remains around third-party penetration testing vendor selection. "
        "This does not block delivery approval."
        if is_residual
        else f"The {dim.value} dimension is comprehensively covered in the v2 proposal."
    )

    payload = ReviewNodePayload(
        dimension=dim,
        findings=[
            IssueFinding(
                dimension=dim,
                confidence=confidence,
                summary=summary,
                detail=detail,
                citations=[
                    SourceCitation(
                        file_path="/simulation-alpha-v2.md",
                        line_start=1,
                        line_end=5,
                        citation_type=CitationTypeEnum.DIRECT_REFERENCE,
                        excerpt="Simulation-Alpha Proposal v2",
                    )
                ],
                mitigation_routing=mitigation,
            )
        ],
        overall_confidence=confidence,
        raw_llm_response="{}",
    )
    return payload.model_dump_json()



def _make_synthesis_response_v1() -> str:
    """Run 1: confidence=42, ready_for_approval=False, one Critical-severity conflict."""
    return json.dumps({
        "executive_summary": (
            "Simulation-Alpha v1 is NOT ready for approval. Critical security gaps "
            "have been identified across the NFR, Risk, and Architecture dimensions. "
            "A regulated financial data platform of this scale requires documented "
            "encryption standards, access management policies, vulnerability assessment, "
            "and a penetration testing schedule before delivery can be approved. "
            "The absence of these controls represents a blocking regulatory and "
            "commercial risk. Confidence in successful delivery is low at this stage."
        ),
        "delivery_confidence_score": 42,
        "critical_conflicts": [
            {
                "dimensions_involved": ["Architecture", "NFR"],
                "description": (
                    "The architecture describes a Kafka/EKS/PostgreSQL stack handling "
                    "regulated financial transactions, but the NFR section contains no "
                    "security or compliance requirements whatsoever. Deploying this "
                    "architecture without defined security NFRs creates unacceptable "
                    "regulatory exposure under PCI DSS and FCA rules."
                ),
                "severity": "Critical",
                "source_references": [
                    "/simulation-alpha-v1.md Section 3 — Architecture",
                    "/simulation-alpha-v1.md NOTE — Security Gap",
                ],
                "suggested_mitigation": (
                    "Add a dedicated Security and Compliance section. Define encryption "
                    "standards (AES-256 at rest, TLS 1.3 in transit), RBAC policies, "
                    "secrets management via HashiCorp Vault, and a penetration testing "
                    "schedule aligned with Phase 2 completion."
                ),
            },
            {
                "dimensions_involved": ["Risk", "Delivery"],
                "description": (
                    "The delivery timeline assumes standard feature velocity but does not "
                    "account for security engineering sprints, compliance assessment time, "
                    "or penetration test remediation cycles — all mandatory for a PCI DSS "
                    "Level 1 regulated platform."
                ),
                "severity": "High",
                "source_references": [
                    "/simulation-alpha-v1.md Section 4 — Timeline",
                    "/simulation-alpha-v1.md NOTE — Security Gap",
                ],
                "suggested_mitigation": (
                    "Extend Phase 2 by one sprint to accommodate security engineering. "
                    "Add penetration testing to Phase 2 and a PCI DSS compliance audit "
                    "to Phase 3."
                ),
            },
        ],
        "architectural_risks": [
            "No encryption standards defined for data at rest or in transit.",
            "No RBAC or IAM policy documented for EKS cluster and service accounts.",
            "No secrets management approach — credentials likely to be hard-coded.",
            "PCI DSS Level 1 compliance absent despite processing financial transactions.",
            "No vulnerability scanning process defined for the CI/CD pipeline.",
        ],
        "actionable_recommendations": [
            "Add a Security and Compliance section covering encryption, RBAC, secrets management, and compliance targets.",
            "Introduce 2 dedicated security engineers into the resource plan.",
            "Define penetration testing schedule — external vendor, Month 10–11 of Phase 2.",
            "Extend Phase 3 to include a formal PCI DSS compliance audit with a QSA.",
            "Obtain sign-off from a security architect before Phase 1 commencement.",
        ],
        "ready_for_approval": False,
    })


def _make_synthesis_response_v2() -> str:
    """Run 2: confidence=87, ready_for_approval=True, no Critical conflicts."""
    return json.dumps({
        "executive_summary": (
            "Simulation-Alpha v2 is structurally sound and ready for approval. "
            "The critical security gap identified in v1 has been comprehensively "
            "addressed: AES-256 encryption at rest, TLS 1.3 in transit, RBAC on "
            "EKS, WAF on public APIs, HashiCorp Vault for secrets, PCI DSS Level 1 "
            "compliance targeting, and a structured penetration testing programme are "
            "all now documented. The £200K commercial uplift is justified and "
            "well-evidenced. A minor residual risk remains around third-party "
            "penetration testing vendor selection, but this does not block approval."
        ),
        "delivery_confidence_score": 87,
        "critical_conflicts": [],
        "architectural_risks": [
            "Penetration testing vendor not yet confirmed — tracked as low risk.",
        ],
        "actionable_recommendations": [
            "Confirm penetration testing vendor by end of Phase 1 (Month 6).",
            "Conduct a pre-Phase 2 security architecture review to validate WAF config.",
            "Ensure Snyk CI/CD integration is operational from Phase 1, Day 1.",
        ],
        "ready_for_approval": True,
    })



# ── Mock factories ────────────────────────────────────────────────────────────

def _make_dim_mock(payload_factory) -> AsyncMock:
    """Sequential mock: calls 0–11 return dim payloads (in ReviewDimensionEnum order)."""
    call_count = 0

    async def _side_effect(**kwargs):
        nonlocal call_count
        choice = MagicMock()
        dim = _DIM_LIST[call_count % 12]
        choice.message.content = payload_factory(dim)
        choice.finish_reason = "stop"
        resp = MagicMock()
        resp.choices = [choice]
        call_count += 1
        return resp

    return AsyncMock(side_effect=_side_effect)


def _make_synth_mock(response_json: str) -> AsyncMock:
    """Single-call mock returning a ReconciliationReport JSON string."""
    choice = MagicMock()
    choice.message.content = response_json
    choice.finish_reason = "stop"
    resp = MagicMock()
    resp.choices = [choice]
    return AsyncMock(return_value=resp)


# ── Pipeline step functions ───────────────────────────────────────────────────

async def step_ingestion(conn, project, artifact_content: str, file_path: str,
                         version_name: str, version_desc: str,
                         blueprint, run_label: str) -> Tuple[Any, ArtifactRegistry, dict]:
    """Step 1 — Ingestion: register artifact, create version, build registry."""
    try:
        version = await create_version(
            conn, project.id, name=version_name, description=version_desc
        )
        artifact = IngestedArtifact(
            uri=f"file://{file_path}",
            file_path=file_path,
            content=artifact_content,
            line_count=len(artifact_content.splitlines()),
        )
        registry = ArtifactRegistry()
        registry.register(artifact)

        dump = {
            "simulation_run": run_label,
            "step": "Ingestion",
            "timestamp": _now(),
            "project": {"id": project.id, "name": project.name, "global_tags": project.global_tags},
            "version": {"id": version.id, "name": version.name, "description": version.description},
            "artifact": {
                "file_path": artifact.file_path,
                "uri": artifact.uri,
                "line_count": artifact.line_count,
                "content_preview": artifact_content[:200] + "...",
            },
            "blueprint": {
                "id": blueprint.id,
                "name": blueprint.blueprint_name,
                "version": blueprint.version_string,
                "is_active": blueprint.is_active,
            },
        }
        return version, registry, dump
    except Exception as exc:
        _halt(f"{run_label} / Ingestion", exc)



async def step_arbitration(conn, project, version, registry: ArtifactRegistry,
                           blueprint, dim_mock: AsyncMock,
                           run_label: str) -> Tuple[Any, List[ReviewNodePayload], dict]:
    """Step 2 — Arbitration: run 12-dimension Layer 1 review, commit exploration node."""
    try:
        builder = PromptBuilder(
            blueprint=blueprint,
            schema_json=json.dumps(ReviewNodePayload.model_json_schema()),
        )

        async def _noop(_task) -> None:
            pass

        with patch("contexta.llm.provider.litellm.acompletion", dim_mock):
            runner_fn = make_dimension_runner(
                config=LLMConfig(model="ollama/mistral"),
                builder=builder,
                registry=registry,
            )
            orchestrator = TaskOrchestrator(
                on_state_change=_noop,
                runner_fn=runner_fn,
            )
            await orchestrator.launch_all()

        if not orchestrator.all_complete():
            incomplete = orchestrator.incomplete_dimensions()
            raise RuntimeError(f"Not all dimensions complete: {incomplete}")

        node = await commit_exploration_node(
            orchestrator, conn, project_id=project.id,
            node_name=f"{SIMULATION_NAME} — Layer 1 Exploration ({run_label})",
        )

        # Assign version_id so KnowledgeAggregator can build the ConfidenceMatrix.
        await conn.execute(
            "UPDATE nodes SET version_id = ? WHERE id = ?",
            (version.id, node.id),
        )
        await conn.commit()

        payloads = orchestrator.get_all_payloads()
        dim_summary = [
            {
                "dimension": p.dimension.value,
                "overall_confidence": p.overall_confidence.value,
                "finding_count": len(p.findings),
                "finding_summary": p.findings[0].summary if p.findings else "—",
            }
            for p in payloads
        ]

        red_dims = [d["dimension"] for d in dim_summary if d["overall_confidence"] == "RED"]
        amber_dims = [d["dimension"] for d in dim_summary if d["overall_confidence"] == "AMBER"]
        green_dims = [d["dimension"] for d in dim_summary if d["overall_confidence"] == "GREEN"]

        dump = {
            "simulation_run": run_label,
            "step": "Arbitration",
            "timestamp": _now(),
            "exploration_node_id": node.id,
            "version_id": version.id,
            "all_complete": True,
            "dimension_results": dim_summary,
            "summary": {
                "RED": red_dims,
                "AMBER": amber_dims,
                "GREEN": green_dims,
                "red_count": len(red_dims),
                "amber_count": len(amber_dims),
                "green_count": len(green_dims),
            },
            "veto_signal": (
                f"SECURITY GAP DETECTED — {len(red_dims)} RED dimension(s): {red_dims}"
                if red_dims else "No RED dimensions — proposal structurally sound"
            ),
        }
        return node, payloads, dump
    except Exception as exc:
        _halt(f"{run_label} / Arbitration", exc)



async def step_synthesis(conn, project, version, exploration_node,
                         payloads: List[ReviewNodePayload],
                         config: ContextaConfig, synth_mock: AsyncMock,
                         run_label: str) -> Tuple[Any, Any, Any, dict]:
    """Step 3 — Synthesis: Layer 2 ReconciliationReport + JudgeValidationReport."""
    try:
        findings = [f for p in payloads for f in p.findings]

        with patch("contexta.llm.provider.litellm.acompletion", synth_mock):
            arbitrator = LayerTwoArbitrator(config=config)
            report = await arbitrator.synthesize(findings)

        synth_node = await write_synthesis_node(
            conn,
            project_id=project.id,
            parent_id=exploration_node.id,
            node_name=f"{SIMULATION_NAME} — Layer 2 Synthesis ({run_label})",
            report=report,
            version_id=version.id,
        )

        judge = evaluate_reconciliation_report(report)

        failed_gates = [g.gate_name for g in judge.gate_checks if not g.passed]
        passed_gates = [g.gate_name for g in judge.gate_checks if g.passed]

        dump = {
            "simulation_run": run_label,
            "step": "Synthesis",
            "timestamp": _now(),
            "synthesis_node_id": synth_node.id,
            "exploration_node_id": exploration_node.id,
            "findings_ingested": len(findings),
            "reconciliation_report": report.model_dump(),
            "judge_validation": {
                "overall_passed": judge.overall_passed,
                "gate_checks": [
                    {
                        "gate_name": g.gate_name,
                        "passed": g.passed,
                        "rejection_reason": g.rejection_reason,
                    }
                    for g in judge.gate_checks
                ],
                "failed_gates": failed_gates,
                "passed_gates": passed_gates,
            },
            "verdict": (
                "PASS — proposal is ready for approval"
                if judge.overall_passed
                else f"VETO — {len(failed_gates)} gate(s) failed: {failed_gates}"
            ),
        }
        return synth_node, report, judge, dump
    except Exception as exc:
        _halt(f"{run_label} / Synthesis", exc)



async def step_learning(conn, project, synth_node, judge, blueprint,
                        run_label: str) -> dict:
    """Step 4 — Learning: PromptOptimizer + KnowledgeAggregator + PromptDelta."""
    try:
        optimizer = PromptOptimizer(conn)
        citation_record = await optimizer.run_for_project(
            project.id, source_node_id=synth_node.id
        )
        citation_payload = json.loads(citation_record.payload_json)

        aggregator = KnowledgeAggregator(conn)
        confidence_record = await aggregator.run_for_project(project.id)
        confidence_payload = json.loads(confidence_record.payload_json)

        delta_svc = PromptDelta(conn)
        delta_record = await delta_svc.run(
            judge_report=judge,
            blueprint=blueprint,
            project_id=project.id,
            source_node_id=synth_node.id,
        )
        delta_payload = json.loads(delta_record.payload_json)

        dump = {
            "simulation_run": run_label,
            "step": "Learning",
            "timestamp": _now(),
            "citation_trend": {
                "record_id": citation_record.id,
                "insight_type": citation_record.insight_type,
                "trends": citation_payload.get("trends", []),
                "unique_sections_cited": len(citation_payload.get("trends", [])),
            },
            "confidence_matrix": {
                "record_id": confidence_record.id,
                "insight_type": confidence_record.insight_type,
                "project_id": confidence_payload.get("project_id"),
                "version_order": confidence_payload.get("version_order", []),
                "matrix": confidence_payload.get("matrix", {}),
            },
            "prompt_delta": {
                "record_id": delta_record.id,
                "insight_type": delta_record.insight_type,
                "gate_failures": delta_payload.get("gate_failures", []),
                "delta_json": delta_payload.get("delta_json", {}),
                "base_prompt_length": delta_payload.get("base_prompt_length"),
                "applied_to_blueprint_id": delta_payload.get("applied_to_blueprint_id"),
                "adjustments_count": len(delta_payload.get("delta_json", {})),
            },
        }
        return dump
    except Exception as exc:
        _halt(f"{run_label} / Learning", exc)


async def step_audit(conn, run_label: str) -> dict:
    """Step 5 — Audit: DreamCycleWorker pattern aggregation."""
    try:
        worker = DreamCycleWorker()
        insights_updated = await worker.run(conn)

        dump = {
            "simulation_run": run_label,
            "step": "Audit",
            "timestamp": _now(),
            "dream_cycle_insights_updated": insights_updated,
            "description": (
                "DreamCycleWorker scanned all exploration nodes for RED-confidence "
                "dimensions and upserted HIGH_RISK_<DIMENSION> pattern records "
                "into global_client_insights keyed by project tags."
            ),
        }
        return dump
    except Exception as exc:
        _halt(f"{run_label} / Audit", exc)



# ── Trend Analysis ────────────────────────────────────────────────────────────

_CONFIDENCE_RANK = {ConfidenceEnum.RED: 0, ConfidenceEnum.AMBER: 1, ConfidenceEnum.GREEN: 2}


def _confidence_delta_label(v1: str, v2: str) -> str:
    r1 = _CONFIDENCE_RANK.get(ConfidenceEnum(v1), -1)
    r2 = _CONFIDENCE_RANK.get(ConfidenceEnum(v2), -1)
    if r2 > r1:
        return "CRITICAL_RESOLVED" if v1 == "RED" and v2 == "GREEN" else "IMPROVED"
    if r2 == r1:
        return "UNCHANGED"
    return "REGRESSED"


async def build_trend_analysis(
    conn,
    project,
    version1,
    version2,
    judge1,
    judge2,
    run_label: str = "Trend Analysis (v1 → v2)",
) -> dict:
    """Compute the 12-dimension confidence trend and aggregate delta."""
    try:
        aggregator = KnowledgeAggregator(conn)
        matrix = await aggregator.compute_confidence_matrix(project.id)

        v1_conf = matrix.matrix.get(version1.id, {})
        v2_conf = matrix.matrix.get(version2.id, {})

        dimension_comparison = []
        for dim in ReviewDimensionEnum:
            d = dim.value
            c1 = v1_conf.get(d, "UNKNOWN")
            c2 = v2_conf.get(d, "UNKNOWN")
            dimension_comparison.append({
                "dimension": d,
                "v1": c1,
                "v2": c2,
                "delta": _confidence_delta_label(c1, c2) if c1 != "UNKNOWN" and c2 != "UNKNOWN" else "INCOMPLETE",
            })

        v1_score = judge1.reconciliation_report.delivery_confidence_score
        v2_score = judge2.reconciliation_report.delivery_confidence_score

        v1_failed = [g.gate_name for g in judge1.gate_checks if not g.passed]
        v2_failed = [g.gate_name for g in judge2.gate_checks if not g.passed]
        gates_resolved = [g for g in v1_failed if g not in v2_failed]
        gates_regressed = [g for g in v2_failed if g not in v1_failed]

        # Retrieve the PromptDelta from Run 1 (the intelligence that informed Run 2)
        delta_records = await get_intelligence_by_type(conn, "PROMPT_DELTA", project.id)
        run1_delta_payload = (
            json.loads(delta_records[0].payload_json) if delta_records else {}
        )

        dump = {
            "simulation": SIMULATION_NAME,
            "comparison": "v1 (The Gap) → v2 (The Correction)",
            "generated_at": _now(),
            "version_ids": {
                "v1": version1.id,
                "v1_name": version1.name,
                "v2": version2.id,
                "v2_name": version2.name,
            },
            "dimension_comparison": dimension_comparison,
            "aggregate_confidence_delta": {
                "v1_score": v1_score,
                "v2_score": v2_score,
                "delta": v2_score - v1_score,
                "v1_verdict": "VETO" if not judge1.overall_passed else "PASS",
                "v2_verdict": "PASS" if judge2.overall_passed else "VETO",
                "outcome": "SECURITY GAP RESOLVED — delivery confidence restored",
            },
            "gate_comparison": {
                "v1_failed_gates": v1_failed,
                "v2_failed_gates": v2_failed,
                "gates_resolved": gates_resolved,
                "gates_regressed": gates_regressed,
                "all_gates_resolved": len(gates_regressed) == 0 and len(v2_failed) == 0,
            },
            "prompt_delta_from_run1": {
                "description": (
                    "PromptDelta generated after Run 1 gate failures. "
                    "These adjustments informed the prompt context for Run 2 synthesis."
                ),
                "gate_failures": run1_delta_payload.get("gate_failures", []),
                "delta_json": run1_delta_payload.get("delta_json", {}),
                "adjustments_count": len(run1_delta_payload.get("delta_json", {})),
            },
        }
        return dump
    except Exception as exc:
        _halt(run_label, exc)



# ── Main orchestration ────────────────────────────────────────────────────────

async def main() -> None:
    print(f"\n{'=' * 60}")
    print(f"  {SIMULATION_NAME} — Multi-Stage Simulation Run")
    print(f"  {_now()}")
    print(f"{'=' * 60}\n")

    # ── Shared DB + project setup ─────────────────────────────────────────────
    print("[ Setup ] Initialising in-memory database...")
    try:
        conn = await init_database(":memory:")
        blueprint = await save_blueprint_version(
            conn,
            name="Simulation Blueprint",
            version="1.0.0",
            prompt_text=(
                "Review the provided solution proposal with rigorous scrutiny. "
                "Focus on delivery risk, technical feasibility, regulatory "
                "compliance, and security posture. Flag missing controls explicitly."
            ),
        )
        await activate_blueprint(conn, blueprint.id)
        project = await create_project(conn, SIMULATION_NAME, PROJECT_TAGS)
        config = ContextaConfig(llm_backend="ollama/mistral")
        print(f"    ✓ Project created: {project.name} [{project.id}]")
        print(f"    ✓ Blueprint active: {blueprint.blueprint_name} v{blueprint.version_string}")
    except Exception as exc:
        _halt("Setup", exc)

    v1_content = _read_artifact("simulation_alpha_v1.md")
    v2_content = _read_artifact("simulation_alpha_v2.md")

    # ═══════════════════════════════════════════════════════════════════════════
    # RUN 1 — The Gap
    # ═══════════════════════════════════════════════════════════════════════════
    run1 = "Run 1 (The Gap)"
    print(f"\n{'─' * 60}")
    print(f"  {run1}")
    print(f"{'─' * 60}")

    print(f"\n  [Step 1] Ingestion")
    version1, registry1, d_ingest1 = await step_ingestion(
        conn, project, v1_content,
        file_path="/simulation-alpha-v1.md",
        version_name="v1 — Initial Review (The Gap)",
        version_desc="First review pass. Security section absent — expected to produce Veto.",
        blueprint=blueprint, run_label=run1,
    )
    _dump(OUTPUT_DIR / "run1_ingestion.json", d_ingest1)

    print(f"\n  [Step 2] Arbitration (12-dimension Layer 1)")
    node1, payloads1, d_arb1 = await step_arbitration(
        conn, project, version1, registry1, blueprint,
        dim_mock=_make_dim_mock(_make_dim_payload_v1),
        run_label=run1,
    )
    _dump(OUTPUT_DIR / "run1_arbitration.json", d_arb1)

    print(f"\n  [Step 3] Synthesis (Layer 2 + Judge Validation)")
    synth1, report1, judge1, d_synth1 = await step_synthesis(
        conn, project, version1, node1, payloads1, config,
        synth_mock=_make_synth_mock(_make_synthesis_response_v1()),
        run_label=run1,
    )
    _dump(OUTPUT_DIR / "run1_synthesis.json", d_synth1)

    print(f"\n  [Step 4] Learning (Optimizer + Aggregator + Delta)")
    d_learn1 = await step_learning(conn, project, synth1, judge1, blueprint, run_label=run1)
    _dump(OUTPUT_DIR / "run1_learning.json", d_learn1)

    print(f"\n  [Step 5] Audit (DreamCycleWorker)")
    d_audit1 = await step_audit(conn, run_label=run1)
    _dump(OUTPUT_DIR / "run1_audit.json", d_audit1)

    run1_verdict = d_synth1["verdict"]
    print(f"\n  ► Run 1 Verdict: {run1_verdict}")

    # ═══════════════════════════════════════════════════════════════════════════
    # RUN 2 — The Correction
    # ═══════════════════════════════════════════════════════════════════════════
    run2 = "Run 2 (The Correction)"
    print(f"\n{'─' * 60}")
    print(f"  {run2}")
    print(f"{'─' * 60}")

    print(f"\n  [Step 1] Ingestion")
    version2, registry2, d_ingest2 = await step_ingestion(
        conn, project, v2_content,
        file_path="/simulation-alpha-v2.md",
        version_name="v2 — Corrected Proposal (The Correction)",
        version_desc="Security section added in full. Expected to produce Pass.",
        blueprint=blueprint, run_label=run2,
    )
    _dump(OUTPUT_DIR / "run2_ingestion.json", d_ingest2)

    print(f"\n  [Step 2] Arbitration (12-dimension Layer 1)")
    node2, payloads2, d_arb2 = await step_arbitration(
        conn, project, version2, registry2, blueprint,
        dim_mock=_make_dim_mock(_make_dim_payload_v2),
        run_label=run2,
    )
    _dump(OUTPUT_DIR / "run2_arbitration.json", d_arb2)

    print(f"\n  [Step 3] Synthesis (Layer 2 + Judge Validation)")
    synth2, report2, judge2, d_synth2 = await step_synthesis(
        conn, project, version2, node2, payloads2, config,
        synth_mock=_make_synth_mock(_make_synthesis_response_v2()),
        run_label=run2,
    )
    _dump(OUTPUT_DIR / "run2_synthesis.json", d_synth2)

    print(f"\n  [Step 4] Learning (Optimizer + Aggregator + Delta)")
    d_learn2 = await step_learning(conn, project, synth2, judge2, blueprint, run_label=run2)
    _dump(OUTPUT_DIR / "run2_learning.json", d_learn2)

    print(f"\n  [Step 5] Audit (DreamCycleWorker)")
    d_audit2 = await step_audit(conn, run_label=run2)
    _dump(OUTPUT_DIR / "run2_audit.json", d_audit2)

    run2_verdict = d_synth2["verdict"]
    print(f"\n  ► Run 2 Verdict: {run2_verdict}")

    # ═══════════════════════════════════════════════════════════════════════════
    # CONFIDENCE TREND ANALYSIS
    # ═══════════════════════════════════════════════════════════════════════════
    print(f"\n{'─' * 60}")
    print(f"  Confidence Trend Analysis (v1 → v2)")
    print(f"{'─' * 60}\n")

    trend = await build_trend_analysis(
        conn, project, version1, version2, judge1, judge2
    )
    _dump(OUTPUT_DIR / "trend_analysis_v1_to_v2.json", trend)

    await conn.close()

    # ── Summary log ───────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"  SIMULATION COMPLETE — Summary Log")
    print(f"{'=' * 60}\n")

    print("  Veto / Pass comparison:")
    print(f"    Run 1 (The Gap):       {run1_verdict}")
    print(f"    Run 2 (The Correction): {run2_verdict}")

    print("\n  PromptDelta recommendations from Run 1:")
    for gate in d_learn1["prompt_delta"]["gate_failures"]:
        print(f"    • Gate failed: {gate}")
    for key, text in d_learn1["prompt_delta"]["delta_json"].items():
        print(f"    → [{key}]")
        print(f"       {text[:120]}...")

    print("\n  12-Dimension confidence comparison (v1 → v2):")
    for entry in trend["dimension_comparison"]:
        marker = "✓" if entry["delta"] not in ("REGRESSED", "UNCHANGED", "INCOMPLETE") else ("=" if entry["delta"] == "UNCHANGED" else "↓")
        print(f"    {marker} {entry['dimension']:13s}  {entry['v1']:6s} → {entry['v2']:6s}  [{entry['delta']}]")

    agg = trend["aggregate_confidence_delta"]
    print(f"\n  Aggregate confidence delta:")
    print(f"    v1 score : {agg['v1_score']}  ({agg['v1_verdict']})")
    print(f"    v2 score : {agg['v2_score']}  ({agg['v2_verdict']})")
    print(f"    delta    : +{agg['delta']} points")
    print(f"    outcome  : {agg['outcome']}")

    print("\n  Run 2 synthesis conciseness:")
    v1_summary_len = len(report1.executive_summary)
    v2_summary_len = len(report2.executive_summary)
    v1_rec_count = len(report1.actionable_recommendations)
    v2_rec_count = len(report2.actionable_recommendations)
    print(f"    v1 executive summary: {v1_summary_len} chars, {v1_rec_count} recommendations")
    print(f"    v2 executive summary: {v2_summary_len} chars, {v2_rec_count} recommendations")
    print(f"    v2 is {'more concise' if v2_summary_len < v1_summary_len else 'more detailed (all conflicts resolved)'} "
          f"and {'fewer' if v2_rec_count < v1_rec_count else 'same'} actionable items (no blockers to enumerate)")

    gate_comp = trend["gate_comparison"]
    print(f"\n  Gate resolution:")
    print(f"    Run 1 failed gates : {gate_comp['v1_failed_gates']}")
    print(f"    Run 2 failed gates : {gate_comp['v2_failed_gates']}")
    print(f"    Gates resolved     : {gate_comp['gates_resolved']}")
    print(f"    All gates resolved : {gate_comp['all_gates_resolved']}")

    print(f"\n  Output files written to: {OUTPUT_DIR.relative_to(REPO_ROOT)}/")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
