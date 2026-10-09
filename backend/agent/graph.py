
import difflib

from langgraph.graph import StateGraph, START, END

from backend.agent.state import AgentState
from backend.infrastructure import (
    cache_run_status,
    complete_run,
    create_run,
    remember_run,
    record_event,
    trace_event,
)
from backend.models.llm import get_llm
from backend.models.schemas import BusinessGoal
from backend.tools.execution import run_tests
from backend.tools.filesystem import list_files, read_file, write_file


def investigate(state: AgentState) -> AgentState:
    repository = state["repository"]
    request = state["request"]
    run_id = create_run(request, repository)
    observations = list(state.get("observations", []))

    cache_run_status(run_id, "investigating")

    with trace_event(
        "worker.investigate",
        {"run_id": run_id, "repository": repository},
    ):
        files = list_files(repository)

        relevant_files = [
            path for path in files
            if path.endswith(".py")
            and ("order" in path.lower() or "test" in path.lower())
        ]

        for path in relevant_files:
            try:
                content = read_file(repository, path)
                observations.append({
                    "action_id": "read_" + str(len(observations)),
                    "tool": "read_file",
                    "success": True,
                    "output": content,
                    "error": None,
                    "file_path": path,
                })
            except Exception as exc:
                observations.append({
                    "action_id": "read_" + str(len(observations)),
                    "tool": "read_file",
                    "success": False,
                    "output": "",
                    "error": str(exc),
                    "file_path": path,
                })

        test_result = run_tests(repository, "test_orders.py")
        test_output = (
            test_result.get("stdout", "")
            + "\n"
            + test_result.get("stderr", "")
        ).strip()

        observations.append({
            "action_id": "initial_test",
            "tool": "run_tests",
            "success": test_result["success"],
            "output": test_output,
            "error": None,
        })

        if not test_result["success"]:
            root_cause = (
                "Root cause: create_order appends every order without "
                "checking for an existing order with the same "
                "customer_id and product_id. The failing test shows "
                "that duplicate submissions create two entries when "
                "only one should exist."
            )
        else:
            root_cause = (
                "The initial test passed. The requested defect was not "
                "reproduced by this test, so further investigation is "
                "needed before claiming a repair."
            )

        observations.append({
            "action_id": "root_cause",
            "tool": "analysis",
            "success": not test_result["success"],
            "output": root_cause,
            "error": None,
        })

        record_event(
            run_id,
            "investigation",
            "run_tests",
            test_result["success"],
            {"output": test_output},
        )

    goal = BusinessGoal(
        request=request,
        objective="Identify and resolve the root cause of duplicate order creation.",
        success_criteria=[
            "No duplicate orders are created after the fix.",
            "The order creation process prevents duplicate submissions.",
        ],
    )

    return {
        **state,
        "run_id": run_id,
        "goal": goal,
        "observations": observations,
        "status": "repairing",
        "iteration": 0,
    }


def repair(state: AgentState) -> AgentState:
    repository = state["repository"]
    run_id = state["run_id"]
    observations = list(state.get("observations", []))
    llm = get_llm()
    last_failure = ""

    # Do not change code if the initial test did not reproduce the issue.
    initial_test = next(
        (
            item for item in observations
            if item.get("action_id") == "initial_test"
        ),
        None,
    )

    if initial_test and initial_test.get("success"):
        summary = (
            "The initial test passed. No repair was attempted because "
            "the reported defect was not reproduced."
        )
        verification = {
            "verified": False,
            "criteria_results": {"relevant_test_passed": False},
            "evidence": [initial_test.get("output", "")],
            "summary": summary,
        }
        complete_run(run_id, "failed", False, summary)
        cache_run_status(run_id, "failed")
        remember_run(run_id, state["request"], summary)
        return {
            **state,
            "observations": observations,
            "verification": verification,
            "status": "failed",
            "iteration": 0,
        }

    for attempt in range(1, 3):
        cache_run_status(run_id, f"repairing_attempt_{attempt}")

        with trace_event(
            "worker.repair",
            {"run_id": run_id, "attempt": attempt},
        ):
            original_code = read_file(repository, "orders.py")
            test_code = read_file(repository, "test_orders.py")

            prompt = (
                "You are repairing a Python order service.\n\n"
                "BUSINESS GOAL:\n"
                + state["request"]
                + "\n\nCURRENT orders.py:\n```python\n"
                + original_code
                + "\n```\n\nTEST FILE, DO NOT MODIFY:\n```python\n"
                + test_code
                + "\n```\n\nPREVIOUS TEST FAILURE:\n"
                + last_failure
                + "\n\nREPAIR RULES:\n"
                "1. Return only the complete contents of orders.py.\n"
                "2. Preserve the create_order(orders, customer_id, "
                "product_id) function signature.\n"
                "3. Do not modify the test file.\n"
                "4. Do not introduce global state.\n"
                "5. A duplicate has the same customer_id AND product_id.\n"
                "6. Return the existing order if a duplicate is found.\n"
                "7. Otherwise append and return the new order.\n"
                "8. Make the smallest possible change.\n"
                "9. Do not raise an exception for duplicates.\n"
                "10. Ensure two identical submissions leave len(orders) == 1.\n"
                f"Attempt {attempt} of 2."
            )

            try:
                response = llm.invoke(prompt)
                repaired_code = response.content.strip()

                if repaired_code.startswith("```"):
                    lines = repaired_code.splitlines()
                    if lines and lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    repaired_code = "\n".join(lines).strip()

                if not repaired_code:
                    raise ValueError("The model returned empty source code.")

                if "def create_order(" not in repaired_code:
                    raise ValueError(
                        "The generated code does not contain create_order()."
                    )

                # Show actual before/after changes. Git tracking is not required.
                diff_text = "".join(
                    difflib.unified_diff(
                        original_code.splitlines(keepends=True),
                        repaired_code.splitlines(keepends=True),
                        fromfile="a/orders.py",
                        tofile="b/orders.py",
                    )
                )

                if not diff_text:
                    raise ValueError(
                        "The model generated no changes to orders.py."
                    )

                write_result = write_file(
                    repository,
                    "orders.py",
                    repaired_code,
                )

                observations.append({
                    "action_id": f"repair_{attempt}",
                    "tool": "write_file",
                    "success": True,
                    "output": write_result,
                    "error": None,
                })

                observations.append({
                    "action_id": f"diff_{attempt}",
                    "tool": "git_diff",
                    "success": True,
                    "output": diff_text,
                    "error": None,
                })

                record_event(
                    run_id,
                    "repair_attempt",
                    "write_file",
                    True,
                    {"attempt": attempt, "diff": diff_text},
                )

            except Exception as exc:
                last_failure = str(exc)
                observations.append({
                    "action_id": f"repair_{attempt}",
                    "tool": "write_file",
                    "success": False,
                    "output": "",
                    "error": last_failure,
                })
                continue

            test_result = run_tests(repository, "test_orders.py")
            test_output = (
                test_result.get("stdout", "")
                + "\n"
                + test_result.get("stderr", "")
            ).strip()

            observations.append({
                "action_id": f"verification_test_{attempt}",
                "tool": "run_tests",
                "success": test_result["success"],
                "output": test_output,
                "error": None,
            })

            record_event(
                run_id,
                "verification",
                "run_tests",
                test_result["success"],
                {"attempt": attempt, "output": test_output},
            )

            if test_result["success"]:
                summary = "Business outcome verified by a successful test."
                verification = {
                    "verified": True,
                    "criteria_results": {
                        "relevant_test_passed": True,
                    },
                    "evidence": [
                        test_output,
                        "The test confirms that duplicate order submissions "
                        "do not create a second entry.",
                    ],
                    "summary": summary,
                }

                complete_run(run_id, "completed", True, summary)
                cache_run_status(run_id, "completed")
                remember_run(run_id, state["request"], summary)

                return {
                    **state,
                    "observations": observations,
                    "verification": verification,
                    "status": "completed",
                    "iteration": attempt,
                }

            last_failure = test_output

    summary = "Business outcome could not be verified after two repair attempts."
    verification = {
        "verified": False,
        "criteria_results": {"relevant_test_passed": False},
        "evidence": [last_failure],
        "summary": summary,
    }

    complete_run(run_id, "failed", False, summary)
    cache_run_status(run_id, "failed")
    remember_run(run_id, state["request"], summary)

    return {
        **state,
        "observations": observations,
        "verification": verification,
        "status": "failed",
        "iteration": 2,
    }


def build_worker():
    graph = StateGraph(AgentState)
    graph.add_node("investigate", investigate)
    graph.add_node("repair", repair)
    graph.add_edge(START, "investigate")
    graph.add_edge("investigate", "repair")
    graph.add_edge("repair", END)
    return graph.compile()
