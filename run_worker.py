from backend.agent.graph import build_worker

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

print("\nSTATUS:", result.get("status"))
print("\nGOAL:", result.get("goal"))
print("\nOBSERVATIONS:")

for observation in result.get("observations", []):
    print("\n---")
    print("TOOL:", observation.get("tool"))
    print("SUCCESS:", observation.get("success"))
    print("OUTPUT:", observation.get("output"))
    print("ERROR:", observation.get("error"))

print("\nVERIFICATION:")
print(result.get("verification"))
