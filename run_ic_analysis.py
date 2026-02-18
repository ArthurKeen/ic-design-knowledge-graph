#!/usr/bin/env python3
"""
IC Knowledge Graph — Agentic Graph Analytics Runner

Runs the agentic graph analytics workflow from agentic-graph-analytics against
the IC Knowledge Graph (OR1200 demo data) and produces Markdown + interactive HTML
reports (Plotly).

Usage:
    python run_ic_analysis.py

Prereqs:
    - Install agentic-graph-analytics: cd ~/code/agentic-graph-analytics && git pull && pip install -e .
    - Configure `.env` (copy from env.template); ensure ARANGO_ENDPOINT, ARANGO_USERNAME, ARANGO_PASSWORD are valid
    - Ensure graph data is loaded in ArangoDB

Output:
    - ic_analysis_output/ic_report_*.md
    - ic_analysis_output/ic_report_*.html
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse


def _require_platform():
    try:
        from graph_analytics_ai.ai.llm import create_llm_provider  # type: ignore
        from graph_analytics_ai.db_connection import get_db_connection  # type: ignore

        from graph_analytics_ai.ai.agents import (  # type: ignore
            OrchestratorAgent,
            AgentNames,
            AgentDefaults,
            SchemaAnalysisAgent,
            RequirementsAgent,
            UseCaseAgent,
            TemplateAgent,
            ExecutionAgent,
            ReportingAgent,
        )

        from graph_analytics_ai.ai.reporting import ReportGenerator, ReportFormat  # type: ignore
        from graph_analytics_ai.catalog import (  # type: ignore
            AnalysisCatalog,
            ExecutionStatus,
            CatalogQueries,
            ExecutionFilter,
        )
        from graph_analytics_ai.catalog.storage import ArangoDBStorage  # type: ignore

        return (
            create_llm_provider,
            get_db_connection,
            OrchestratorAgent,
            AgentNames,
            AgentDefaults,
            SchemaAnalysisAgent,
            RequirementsAgent,
            UseCaseAgent,
            TemplateAgent,
            ExecutionAgent,
            ReportingAgent,
            ReportGenerator,
            ReportFormat,
            AnalysisCatalog,
            ExecutionStatus,
            CatalogQueries,
            ExecutionFilter,
            ArangoDBStorage,
        )
    except ImportError as e:
        print("ERROR: agentic-graph-analytics is not available.")
        print("\nFix: cd ~/code/agentic-graph-analytics && git pull && pip install -e .")
        raise SystemExit(1) from e


def _ensure_endpoint_has_port(url: str, default_port: int = 8529) -> str:
    """Append :8529 to endpoint if no port is present (cluster URLs often need it)."""
    if not url:
        return url
    try:
        u = urlparse(url)
        if u.port is not None:
            return url
        netloc = f"{u.hostname or u.netloc}:{default_port}"
        return urlunparse((u.scheme, netloc, u.path or "", u.params, u.query, u.fragment))
    except Exception:
        return url


def _load_dotenv() -> None:
    """Load .env from project root (no overwrite)."""
    dotenv_path = Path(__file__).resolve().parent / ".env"
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(dotenv_path=dotenv_path, override=False)
    except Exception:
        # Best-effort minimal fallback loader
        if not dotenv_path.exists():
            return
        for line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k:
                os.environ.setdefault(k, v)


def _apply_env_mapping() -> None:
    """
    Normalize env vars for the platform and keep compatibility with this repo's env.template.
    - Ensures ARANGO_ENDPOINT includes :8529 when missing.
    - Ensures ARANGO_USER is set when ARANGO_USERNAME is used.
    - Defaults to self-managed GAE when AMP keys are not present.
    """
    _load_dotenv()

    mode = (os.getenv("MODE") or os.getenv("ARANGO_MODE") or "LOCAL").strip().upper()
    if mode not in {"LOCAL", "REMOTE"}:
        mode = "LOCAL"
    os.environ["MODE"] = mode

    # Normalize endpoint naming + ensure port
    if mode == "LOCAL":
        local_endpoint = os.getenv("LOCAL_ARANGO_ENDPOINT") or os.getenv("LOCAL_ARANGO_URL") or ""
        if local_endpoint and not os.getenv("ARANGO_ENDPOINT"):
            os.environ["ARANGO_ENDPOINT"] = local_endpoint
        if os.getenv("LOCAL_ARANGO_USERNAME") and not os.getenv("ARANGO_USERNAME"):
            os.environ["ARANGO_USERNAME"] = os.environ["LOCAL_ARANGO_USERNAME"]
        if os.getenv("LOCAL_ARANGO_PASSWORD") and not os.getenv("ARANGO_PASSWORD"):
            os.environ["ARANGO_PASSWORD"] = os.environ["LOCAL_ARANGO_PASSWORD"]
        if os.getenv("LOCAL_ARANGO_DATABASE") and not os.getenv("ARANGO_DATABASE"):
            os.environ["ARANGO_DATABASE"] = os.environ["LOCAL_ARANGO_DATABASE"]

    endpoint = os.getenv("ARANGO_ENDPOINT") or os.getenv("ARANGO_URL") or ""
    if endpoint:
        endpoint = _ensure_endpoint_has_port(endpoint)
        os.environ["ARANGO_ENDPOINT"] = endpoint
        os.environ.setdefault("ARANGO_URL", endpoint)

    if os.getenv("ARANGO_USER") is None and os.getenv("ARANGO_USERNAME"):
        os.environ["ARANGO_USER"] = os.environ["ARANGO_USERNAME"]

    # Same behavior as risk-intelligence: use self-managed unless AMP keys are present
    dep_mode = (os.getenv("GAE_DEPLOYMENT_MODE") or "").strip().lower()
    api_key_id = os.getenv("ARANGO_GRAPH_API_KEY_ID")
    if (not dep_mode or dep_mode in ("amp", "managed", "arangograph")) and not api_key_id:
        os.environ["GAE_DEPLOYMENT_MODE"] = "self_managed"


async def main() -> None:
    print("=" * 70)
    print(" " * 10 + "IC KNOWLEDGE GRAPH — AGENTIC GRAPH ANALYTICS")
    print(" " * 14 + "OR1200 Traceability / Risk / Quality Insights")
    print("=" * 70)
    print()

    _apply_env_mapping()

    (
        create_llm_provider,
        get_db_connection,
        OrchestratorAgent,
        AgentNames,
        AgentDefaults,
        SchemaAnalysisAgent,
        RequirementsAgent,
        UseCaseAgent,
        TemplateAgent,
        ExecutionAgent,
        ReportingAgent,
        ReportGenerator,
        ReportFormat,
        AnalysisCatalog,
        ExecutionStatus,
        CatalogQueries,
        ExecutionFilter,
        ArangoDBStorage,
    ) = _require_platform()

    max_exec_raw = (os.getenv("IC_ANALYSIS_MAX_EXECUTIONS") or "").strip()
    if max_exec_raw:
        try:
            max_exec = int(max_exec_raw)
            if max_exec > 0:
                AgentDefaults.MAX_EXECUTIONS = max_exec
        except ValueError:
            pass

    output_dir = Path(os.getenv("IC_ANALYSIS_OUTPUT_DIR") or "ic_analysis_output")
    output_dir.mkdir(exist_ok=True)
    print(f"✓ Output directory: {output_dir.absolute()}")

    graph_name = os.getenv("IC_GRAPH_NAME") or "IC_Knowledge_Graph"
    industry = os.getenv("IC_ANALYSIS_INDUSTRY") or "technology"
    graphrag_prefix = os.getenv("GRAPHRAG_PREFIX") or "OR1200_"

    input_files: list[str] = []
    for fp in (
        "business-requirements.md",
        "README.md",
        "docs/README.md",
        "docs/DEMO_EXECUTIVE_SUMMARY.md",
        "docs/project/PRD.md",
        "docs/project/WALKTHROUGH.md",
    ):
        if Path(fp).exists():
            input_files.append(fp)

    if input_files:
        print(f"✓ Using {len(input_files)} input file(s) for context:")
        for f in input_files:
            print(f"    - {f}")
    else:
        print("⚠ No input documents found; workflow will rely on live schema only.")
    print()

    enable_parallelism = (os.getenv("IC_ANALYSIS_PARALLELISM") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    enable_catalog = (os.getenv("IC_ANALYSIS_ENABLE_CATALOG", "true") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    print("[1/5] Initializing workflow...")
    print(f"      Graph: {graph_name}")
    print(f"      Industry: {industry}")
    print(f"      Parallelism: {'ENABLED' if enable_parallelism else 'DISABLED'}")
    print()

    try:
        db = get_db_connection()
        llm_provider = create_llm_provider()

        catalog: Optional[Any] = None
        current_epoch: Optional[Any] = None
        storage: Optional[Any] = None

        if enable_catalog:
            try:
                storage = ArangoDBStorage(db)
                catalog = AnalysisCatalog(storage)
                epoch_name = f"ic-knowledge-graph-{datetime.now().strftime('%Y-%m')}"

                try:
                    existing_epochs = catalog.query_epochs(filter=None, limit=100)
                    current_epoch = next((e for e in existing_epochs if e.name == epoch_name), None)
                except Exception:
                    current_epoch = None

                if current_epoch:
                    print(f"✓ Using existing epoch: {epoch_name}")
                else:
                    current_epoch = catalog.create_epoch(
                        name=epoch_name,
                        description="Monthly IC knowledge graph analytics run",
                        tags=["ic_knowledge_graph", "hardware", "traceability", "monthly"],
                    )
                    print(f"✓ Created catalog epoch: {epoch_name}")
                print(f"  Epoch ID: {current_epoch.epoch_id}")
                print("  📊 Catalog tracking ENABLED")
            except Exception as e:
                print(f"⚠ Failed to initialize catalog: {e}")
                catalog = None
                current_epoch = None
                storage = None
        else:
            print("  📊 Catalog tracking DISABLED")

        core_collections = [
            "RTL_Module",
            "RTL_Port",
            "RTL_Signal",
            "RTL_LogicChunk",
            f"{graphrag_prefix}Golden_Entities",
        ]
        satellite_collections = [
            "GitCommit",
            "Author",
            f"{graphrag_prefix}Chunks",
            f"{graphrag_prefix}Documents",
            f"{graphrag_prefix}Communities",
        ]

        agents = {
            AgentNames.SCHEMA_ANALYST: SchemaAnalysisAgent(llm_provider=llm_provider, db_connection=db),
            AgentNames.REQUIREMENTS_ANALYST: RequirementsAgent(llm_provider=llm_provider, catalog=catalog),
            AgentNames.USE_CASE_EXPERT: UseCaseAgent(llm_provider=llm_provider, catalog=catalog),
            AgentNames.TEMPLATE_ENGINEER: TemplateAgent(
                llm_provider=llm_provider,
                graph_name=graph_name,
                core_collections=core_collections,
                satellite_collections=satellite_collections,
                catalog=catalog,
            ),
            AgentNames.EXECUTION_SPECIALIST: ExecutionAgent(llm_provider=llm_provider, catalog=catalog),
            AgentNames.REPORTING_SPECIALIST: ReportingAgent(llm_provider=llm_provider, industry=industry),
        }

        if catalog and current_epoch:
            agents[AgentNames.EXECUTION_SPECIALIST].executor.epoch_id = current_epoch.epoch_id

        orchestrator = OrchestratorAgent(llm_provider=llm_provider, agents=agents, catalog=catalog)
        report_generator = ReportGenerator(llm_provider=llm_provider, industry=industry)
        print("✓ Initialized agents")
    except Exception as e:
        print(f"✗ Failed to initialize: {e}")
        print("\nCheck: `.env` (ARANGO_ENDPOINT, ARANGO_USERNAME, ARANGO_PASSWORD), and agentic-graph-analytics installed.")
        raise SystemExit(1) from e

    print()
    print("[2/5] Running agentic workflow...")
    print("      Schema → Requirements → Use cases → Templates → Execution → Reports")
    print()

    try:
        if enable_parallelism:
            state = await orchestrator.run_workflow_async(
                input_documents=input_files,
                database_config=None,
                enable_parallelism=True,
            )
        else:
            state = orchestrator.run_workflow(
                input_documents=input_files,
                database_config=None,
            )
        print("✓ Workflow completed successfully")
    except Exception as e:
        print(f"✗ Workflow failed: {e}")
        raise SystemExit(1) from e

    print()
    print("[3/5] Processing results...")
    if not getattr(state, "reports", None):
        print("✗ No reports generated")
        raise SystemExit(1)
    print(f"✓ Generated {len(state.reports)} report(s)")
    total_insights = sum(len(getattr(r, "insights", []) or []) for r in state.reports)
    print(f"✓ Total insights: {total_insights}")
    print()

    if enable_catalog and storage and current_epoch:
        print("[4/5] Querying catalog...")
        try:
            queries = CatalogQueries(storage)
            recent_executions = queries.query_with_pagination(
                filter=ExecutionFilter(epoch_id=current_epoch.epoch_id, status=ExecutionStatus.COMPLETED),
                page=1,
                page_size=100,
            )
            print(f"✓ Tracked {recent_executions.total_count} executions in catalog")
        except Exception as e:
            print(f"⚠ Failed to query catalog: {e}")
    else:
        print("[4/5] Catalog disabled, skipping")
    print()

    print("[5/5] Saving reports...")
    for i, report in enumerate(state.reports, 1):
        report_name = f"ic_report_{i}"
        md_path = output_dir / f"{report_name}.md"
        html_path = output_dir / f"{report_name}.html"
        md_path.write_text(report_generator.format_report(report, ReportFormat.MARKDOWN))
        html_path.write_text(report_generator.format_report(report, ReportFormat.HTML))
        print(f"  ✓ {md_path.name}")
        print(f"  ✓ {html_path.name}")

    print()
    print("=" * 70)
    print(" " * 27 + "✓ ANALYSIS COMPLETE")
    print("=" * 70)
    print(f"📁 Reports: {output_dir.absolute()}")
    if enable_catalog and current_epoch:
        print(f"📊 Catalog: {current_epoch.name} ({current_epoch.epoch_id})")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠ Interrupted")
        raise SystemExit(130)
