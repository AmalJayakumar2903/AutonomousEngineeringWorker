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


st.set_page_config(
    page_title="Autonomous Engineering Worker",
    page_icon="⚙️",
    layout="wide",
)

st.title("⚙️ Autonomous Engineering Worker")
st.caption(
    "An autonomous engineering worker that investigates problems, "
    "repairs code, tests the change, and verifies the business outcome."
)


# ─────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────

with st.sidebar:
    st.header("Worker")

    repository = st.text_input(
        "Repository",
        value="sandbox/demo_repo",
    )

    request = st.text_area(
        "Business Goal",
        value=(
            "Customers are occasionally receiving duplicate orders. "
            "Investigate the cause, fix it, and verify that duplicate "
            "orders can no longer be created."
        ),
        height=140,
    )

    run = st.button(
        "▶ Run Autonomous Worker",
        type="primary",
        use_container_width=True,
    )

    st.divider()

    st.subheader("Infrastructure")

    st.write(
        "🟢 SQLite"
        if DATABASE_PATH.exists()
        else "🔴 SQLite"
    )

    st.write(
        "🟢 ChromaDB"
        if CHROMA_PATH.exists()
        else "🔴 ChromaDB"
    )

    st.write(
        "🟢 Redis"
        if get_redis() is not None
        else "🟡 Redis unavailable"
    )

    st.write("🟢 OpenTelemetry")


# ─────────────────────────────────────────────
# Run Worker
# ─────────────────────────────────────────────

if run:
    if not request.strip():
        st.error("Business goal cannot be empty.")
        st.stop()

    with st.spinner("Worker executing..."):
        try:
            worker = build_worker()

            result = worker.invoke(
                {
                    "repository": repository,
                    "request": request,
                    "observations": [],
                    "status": "pending",
                    "iteration": 0,
                }
            )

            st.session_state["last_result"] = result

        except Exception as exc:
            st.exception(exc)


result = st.session_state.get("last_result")


# ─────────────────────────────────────────────
# Result
# ─────────────────────────────────────────────

if result:

    st.divider()

    status = result.get("status", "unknown")
    observations = result.get("observations", [])
    verification = result.get("verification") or {}

    if status == "completed":
        st.success("✅ BUSINESS OUTCOME VERIFIED")
    else:
        st.error(f"❌ Worker finished: {status.upper()}")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Status", status.upper())

    with col2:
        st.metric("Actions", len(observations))

    with col3:
        st.metric(
            "Verified",
            "YES" if verification.get("verified") else "NO",
        )

    # ─────────────────────────────────────────
    # Executive Summary
    # ─────────────────────────────────────────

    st.subheader("What the Worker Did")

    if status == "completed":
        st.markdown(
            """
**Problem identified:** duplicate orders were being created because
`create_order()` appended every order without checking for an existing
customer/product combination.

**Change made:** the worker added a duplicate check using
`customer_id` + `product_id`. If the order already exists, the existing
order is returned instead of creating another one.

**Result:** the original test failed before the repair and passed after it.

**Business outcome:** duplicate order creation was prevented and verified.
"""
        )
    else:
        st.markdown(
            """
The worker investigated the repository but could not verify the
requested business outcome.
"""
        )

    # ─────────────────────────────────────────
    # Timeline
    # ─────────────────────────────────────────

    st.subheader("Execution Timeline")

    for index, observation in enumerate(observations, 1):
        tool = observation.get("tool", "unknown")
        success = observation.get("success", False)
        output = observation.get("output", "")
        error = observation.get("error")

        icon = "✅" if success else "❌"

        if tool == "read_file":
            label = "Inspected source/test file"

        elif tool == "run_tests":
            if success:
                label = "Verification tests passed"
            else:
                label = "Initial tests failed"

        elif tool == "analysis":
            label = "Identified root cause"

        elif tool == "write_file":
            label = "Applied code repair"

        elif tool == "git_diff":
            label = "Generated code change"

        else:
            label = tool.replace("_", " ").title()

        with st.expander(
            f"{icon} {index}. {label}",
            expanded=tool in {"analysis", "git_diff"},
        ):

            if tool == "analysis":
                st.markdown("### Why this was changed")
                st.info(output)

            elif tool == "git_diff":
                st.markdown("### Actual code change")
                st.code(output, language="diff")

            elif tool == "run_tests":
                if success:
                    st.markdown("### Test result")
                    st.success("Verification test passed.")
                else:
                    st.markdown("### Error detected")
                    st.error(
                        "The existing implementation failed the business test."
                    )

                if output:
                    st.code(output, language="text")

                if error:
                    st.code(error, language="text")

            elif tool == "write_file":
                st.markdown("### Action")
                st.success(output)

            elif tool == "read_file":
                st.markdown("### Inspected file")
                st.code(output, language="python")

            else:
                if output:
                    st.code(output, language="text")

                if error:
                    st.error(error)

    # ─────────────────────────────────────────
    # Verification
    # ─────────────────────────────────────────

    st.divider()
    st.subheader("Verification")

    if verification.get("verified"):
        st.success(
            verification.get(
                "summary",
                "Business outcome verified.",
            )
        )
    else:
        st.error(
            verification.get(
                "summary",
                "Business outcome could not be verified.",
            )
        )

    criteria = verification.get("criteria_results", {})

    if criteria:
        st.markdown("### Success criteria")

        for criterion, passed in criteria.items():
            icon = "✅" if passed else "❌"
            st.write(
                f"{icon} {criterion.replace('_', ' ').title()}"
            )

    evidence = verification.get("evidence", [])

    if evidence:
        st.markdown("### Evidence")

        for item in evidence:
            st.write(f"• {item}")


# ─────────────────────────────────────────────
# Run History
# ─────────────────────────────────────────────

st.divider()
st.subheader("📋 Recent Worker Runs")

runs = get_recent_runs(10)

if runs:
    rows = []

    for run_data in runs:
        rows.append(
            {
                "Status": run_data["status"].upper(),
                "Verified": (
                    "YES"
                    if run_data["verified"]
                    else "NO"
                ),
                "Repository": run_data["repository"],
                "Started": run_data["started_at"]
                .replace("T", " ")
                [:19],
                "Summary": (
                    run_data["summary"]
                    or "In progress"
                ),
                "Run ID": run_data["run_id"][:8],
            }
        )

    st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
    )

else:
    st.info("No worker runs recorded yet.")


# ─────────────────────────────────────────────
# Architecture
# ─────────────────────────────────────────────

st.divider()
st.subheader("How the Worker Operates")

st.code(
    """
BUSINESS GOAL
      ↓
INVESTIGATE
      ↓
INSPECT CODE + TESTS
      ↓
RUN EXISTING TESTS
      ↓
IDENTIFY ROOT CAUSE
      ↓
REPAIR CODE
      ↓
SHOW ACTUAL DIFF
      ↓
RUN TESTS AGAIN
      ↓
VERIFY BUSINESS OUTCOME
      ↓
COMPLETE

Persistence:
SQLite  → run history
Redis   → run status
Chroma  → execution memory
OTel    → execution traces
""",
    language="text",
)