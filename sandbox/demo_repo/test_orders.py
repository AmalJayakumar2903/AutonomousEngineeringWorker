from orders import create_order


def test_duplicate_orders_are_rejected():
    orders = []

    create_order(orders, customer_id=101, product_id=5001)
    create_order(orders, customer_id=101, product_id=5001)

    assert len(orders) == 1
