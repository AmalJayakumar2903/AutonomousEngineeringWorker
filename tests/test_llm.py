from backend.models.llm import get_llm


def test_llm_connection():
    llm = get_llm()

    response = llm.invoke(
        "Reply with exactly: WORKER_ONLINE"
    )

    assert "WORKER_ONLINE" in response.content