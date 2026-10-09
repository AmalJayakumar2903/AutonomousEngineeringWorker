
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st

from backend.agent.graph import build_worker
from backend.infrastructure import (
    DATABASE_PATH,
    CHROMA_PATH,
    get_recent_runs,
    get_redis,
)


DEMO_REPOSITORY = "sandbox/demo_repo"
BASELINE_DIRECTORY = ROOT / "sandbox" / "demo_repo_baseline"
DEMO_DIRECTORY = ROOT / DEMO_REPOSITORY

st.set_page_config(
    page_title="Autonomous Engineering Worker",
    page_icon="⚙️",
    layout="wide",
)

st.title("⚙️ Autonomous Engineering Worker")
st.caption(
    "Give the worker a business problem. It investigates, repairs, "
    "tests, and verifies the outcome."
)

with st.sidebar:
    st.header("Worker")

    repository = st.text_input(
        "Repository",
        value=DEMO_REPOSITORY,
    )

    request = st.text_area(
        "Business Goal",
        value=(
            "Customers are occasionally receiving duplicate orders. "
            "Investigate the cause, fix it, and verify that duplicate "
            "orders can no longer be created."
        ),
        height=150,
    )

    run = st.button(
        "▶ Run Autonomous Worker",
        type="primary",
        use_container_width=True,
    )

    st.divider()
    st.subheader("Infrastructure")
    st.write("🟢 SQLite" if DATABASE_PATH.exists() else "🔴 SQLite")
    st.write("🟢 ChromaDB" if CHROMA_PATH.exists() else "🟡 ChromaDB")
    st.write("🟢 Redis" if get_redis() is not None else "🟡 Redis unavailable")
    st.write("🟢 OpenTelemetry configured")


if run:
    if not request.strip():
        st.error("Enter a business goal before running the worker.")
        st.stop()

    normalized_repository = repository.replace("\\", "/").strip("/")

    if normalized_repository != DEMO_REPOSITORY:
        st.error(
            "This demo UI currently supports only sandbox/demo_repo. "
            "Choose that repository to run the controlled demonstration."
        )
        st.stop()

    if not BASELINE_DIRECTORY.is_dir():
        st.error(
            "Demo baseline is missing. Expected files in "
            "sandbox/demo_repo_baseline/."
        )
        st.stop()

    try:
        # Restore the controlled test case before every run.
        for filename in ("orders.py", "test_orders.py"):
            source = BASELINE_DIRECTORY / filename
            destination = DEMO_DIRECTORY / filename

            if not source.is_file():
                raise FileNotFoundError(
                    f"Missing baseline file: {source}"
                )

            shutil.copy2(source, destination)

        with st.spinner(
            "Investigating repository, repairing code, and verifying..."
        ):
            worker = build_worker()
            result = worker.invoke({
                "repository": DEMO_REPOSITORY,
                "request": request.strip(),
                "observations": [],
                "status": "pending",
                "iteration": 0,
            })

        st.session_state["last_result"] = result

    except Exception as exc:
        st.error("Worker execution failed.")
        st.exception(exc)


result = st.session_state.get("last_result")

if result:
    st.divider()

    status = result.get("status", "unknown")
    observations = result.get("observations", [])
    verification = result.get("verification") or {}

    if verification.get("verified"):
        st.success("✅ BUSINESS OUTCOME VERIFIED")
    else:
        st.error(f"❌ WORKER STATUS: {status.upper()}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Status", status.upper())
    col2.metric("Tool Actions", len(observations))
    col3.metric(
        "Verified",
        "YES" if verification.get("verified") else "NO",
    )

    # Show the diagnosis and real code diff first.
    root_cause = next(
        (
            item for item in observations
            if item.get("tool") == "analysis"
        ),
        None,
    )

    diffs = [
        item for item in observations
        if item.get("tool") == "git_diff"
    ]

    st.header("Engineering Report")

    st.subheader("1. Root Cause")

    if root_cause:
        if root_cause.get("success"):
            st.info(root_cause.get("output", "No explanation returned."))
        else:
            st.warning(root_cause.get("output", "Diagnosis was inconclusive."))
    else:
        st.warning("No root-cause explanation was recorded.")

    st.subheader("2. Actual Code Changes")

    if diffs:
        for index, item in enumerate(diffs, start=1):
            st.markdown(f"**Repair attempt {index}**")

            if item.get("output"):
                st.code(item["output"], language="diff")
            else:
                st.warning("No diff was generated.")

    else:
        st.warning(
            "No code diff was recorded. Check the repair action and its error."
        )

    st.subheader("3. Test Results")

    test_observations = [
        item for item in observations
        if item.get("tool") == "run_tests"
    ]

    for index, item in enumerate(test_observations, start=1):
        if item.get("success"):
            st.success(f"Test run {index}: PASSED")
        else:
            st.error(f"Test run {index}: FAILED")

        output = item.get("output", "")
        error = item.get("error")

        if output:
            with st.expander(
                f"Test run {index}: full output",
                expanded=not item.get("success"),
            ):
                st.code(output, language="text")

        if error:
            st.code(error, language="text")

    st.subheader("4. Execution Timeline")

    # Combine repeated file reads into one section.
    file_reads = [
        item for item in observations
        if item.get("tool") == "read_file"
    ]

    if file_reads:
        with st.expander(
            f"Inspected files ({len(file_reads)})",
            expanded=False,
        ):
            for item in file_reads:
                file_path = item.get("file_path", "Source file")
                st.markdown(f"**{file_path}**")

                if item.get("success"):
                    st.code(item.get("output", ""), language="python")
                else:
                    st.error(item.get("error", "File inspection failed."))

    # Keep the timeline focused on actions other than repetitive reads,
    # test output, and the already-prominent diff.
    for item in observations:
        tool = item.get("tool", "unknown")

        if tool in {"read_file", "run_tests", "git_diff", "analysis"}:
            continue

        success = item.get("success", False)
        icon = "✅" if success else "❌"
        label = tool.replace("_", " ").title()

        with st.expander(f"{icon} {label}", expanded=not success):
            if item.get("output"):
                st.code(item["output"], language="text")
            if item.get("error"):
                st.error(item["error"])

    st.subheader("5. Verification")

    if verification.get("verified"):
        st.success(verification.get("summary", "Outcome verified."))
    else:
        st.error(
            verification.get(
                "summary",
                "Business outcome could not be verified.",
            )
        )

    for criterion, passed in verification.get(
        "criteria_results", {}
    ).items():
        st.write(
            ("✅ " if passed else "❌ ")
            + criterion.replace("_", " ").title()
        )

    evidence = verification.get("evidence", [])
    if evidence:
        with st.expander("Verification evidence", expanded=True):
            for entry in evidence:
                st.write(f"• {entry}")


st.divider()
st.header("Recent Worker Runs")

try:
    runs = get_recent_runs(10)

    if runs:
        rows = [
            {
                "Status": item.get("status", "").upper(),
                "Verified": "YES" if item.get("verified") else "NO",
                "Repository": item.get("repository", ""),
                "Started": item.get("started_at", "").replace("T", " ")[:19],
                "Summary": item.get("summary") or "In progress",
                "Run ID": item.get("run_id", "")[:8],
            }
            for item in runs
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No worker runs recorded yet.")

except Exception as exc:
    st.warning(f"Could not load run history: {exc}")


st.divider()
st.header("How the Worker Operates")

st.code(
    """
BUSINESS GOAL
     ↓
INVESTIGATE SOURCE + TESTS
     ↓
OBSERVE INITIAL FAILURE
     ↓
IDENTIFY ROOT CAUSE
     ↓
REPAIR CODE
     ↓
DISPLAY ACTUAL SOURCE DIFF
     ↓
RERUN TESTS
     ↓
VERIFY BUSINESS OUTCOME
     ↓
COMPLETE OR REPORT FAILURE

SQLite        Run history and audit events
Redis         Cached run status
ChromaDB      Persistent execution memory
OpenTelemetry Execution traces
""",
    language="text",
)
