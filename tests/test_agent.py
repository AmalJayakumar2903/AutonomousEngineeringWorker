from backend.agent.graph import build_worker


def test_worker_graph():
    worker = build_worker()

    result = worker.invoke({
        "repository": "sandbox/demo_repo",
        "request": (
            "Customers are occasionally receiving duplicate orders. "
            "Investigate the cause, fix it, and verify that duplicate "
            "orders can no longer be created."
        ),
        "observations": [],
        "status": "pending",
        "iteration": 0,
    })

    assert result["status"] in {"completed", "failed"}
    assert "goal" in result
    assert "verification" in result