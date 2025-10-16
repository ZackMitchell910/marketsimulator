import pytest

from src.core.types import Order
from src.sim.orderbook import OrderBook


def make_limit(agent_id: str, side: str, qty: float, price: float) -> Order:
    return Order(
        agent_id=agent_id,
        side=side,
        qty=qty,
        price_limit=price,
        order_type="LMT",
    )


def make_market(agent_id: str, side: str, qty: float) -> Order:
    return Order(agent_id=agent_id, side=side, qty=qty, order_type="MKT")


def test_fifo_within_price_level():
    book = OrderBook()
    sellers = []
    for idx in range(5):
        qty = 1.0 + idx
        seller_id = f"maker-{idx}"
        book.submit(make_limit(seller_id, "SELL", qty, 100.0))
        sellers.append((seller_id, qty))

    taker_qty = sum(q for _, q in sellers)
    trades = book.submit(make_market("buyer", "BUY", taker_qty))

    maker_sequence = [trade.maker_id for trade in trades]
    assert maker_sequence == [sid for sid, _ in sellers]
    assert sum(trade.qty for trade in trades) == pytest.approx(taker_qty)


@pytest.mark.parametrize("demand_qty", [2.5, 7.0, 12.0])
def test_marketable_limit_orders_cross_available_liquidity(demand_qty: float):
    book = OrderBook()
    supply = [(100.0, 5.0), (101.0, 5.0), (102.0, 5.0)]
    for idx, (price, qty) in enumerate(supply):
        book.submit(make_limit(f"ask-{idx}", "SELL", qty, price))

    limit_price = 101.0
    executable = sum(qty for price, qty in supply if price <= limit_price)
    order = make_limit("buyer", "BUY", demand_qty, limit_price)
    trades = book.submit(order)

    traded_qty = sum(trade.qty for trade in trades)
    assert traded_qty == pytest.approx(min(demand_qty, executable))
    assert all(trade.price <= limit_price for trade in trades)

    depth = book.depth()
    bids = depth["bids"]
    expected_resting = max(demand_qty - executable, 0)
    if expected_resting > 0:
        assert bids and bids[0][1] == pytest.approx(expected_resting)
    else:
        assert bids == []
