from langchain_ollama import ChatOllama


def get_llm() -> ChatOllama:
    return ChatOllama(
        model="qwen2.5-coder:7b",
        base_url="http://localhost:11434",
        temperature=0,
        num_ctx=4096,
        num_predict=700,
        keep_alive="10m",
    )