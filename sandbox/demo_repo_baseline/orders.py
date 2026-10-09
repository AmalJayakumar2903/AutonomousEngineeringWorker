def create_order(orders: list[dict], customer_id: int, product_id: int) -> dict:
    """Create an order for a customer."""

    order = {
        "customer_id": customer_id,
        "product_id": product_id,
    }

    orders.append(order)
    return order
