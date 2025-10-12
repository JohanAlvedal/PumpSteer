"""Tests for the cheap boost functionality."""


def find_cheapest_hours(price_list, num_hours=1):
    """
    Find the indices (positions) of the `num_hours` cheapest prices in the list.
    The indices correspond to the original position in the `price_list`.
    (Copied from electricity_price.py for testing)
    """
    if not price_list or num_hours <= 0:
        return []

    # Pair each price with its original index
    indexed_prices = [(i, price) for i, price in enumerate(price_list)]
    # Sort by price in ascending order
    indexed_prices.sort(key=lambda x: x[1])
    # Return the indices of the cheapest hours
    return [i for i, _ in indexed_prices[:min(num_hours, len(indexed_prices))]]


def test_find_cheapest_hours_basic():
    """Test finding cheapest hours in a simple price list."""
    prices = [1.5, 0.5, 2.0, 0.3, 1.0]
    
    # Find 1 cheapest hour
    result = find_cheapest_hours(prices, 1)
    assert result == [3], f"Expected [3], got {result}"
    
    # Find 2 cheapest hours
    result = find_cheapest_hours(prices, 2)
    assert set(result) == {1, 3}, f"Expected {{1, 3}}, got {set(result)}"
    
    # Find 3 cheapest hours
    result = find_cheapest_hours(prices, 3)
    assert set(result) == {1, 3, 4}, f"Expected {{1, 3, 4}}, got {set(result)}"
    
    print("✓ test_find_cheapest_hours_basic passed")


def test_find_cheapest_hours_edge_cases():
    """Test edge cases for finding cheapest hours."""
    # Empty list
    result = find_cheapest_hours([], 1)
    assert result == [], f"Expected [], got {result}"
    
    # Num hours is 0
    result = find_cheapest_hours([1, 2, 3], 0)
    assert result == [], f"Expected [], got {result}"
    
    # Num hours greater than list length
    prices = [1.0, 2.0, 3.0]
    result = find_cheapest_hours(prices, 5)
    assert len(result) == 3, f"Expected 3 items, got {len(result)}"
    
    print("✓ test_find_cheapest_hours_edge_cases passed")


def test_cheap_boost_current_hour():
    """Test cheap boost logic for current hour detection."""
    # Simulate 24 hours of prices
    prices = [
        0.5,   # Hour 0 - CHEAP
        1.5,   # Hour 1
        2.0,   # Hour 2
        1.8,   # Hour 3
        1.2,   # Hour 4
        0.8,   # Hour 5 - CHEAP
        1.0,   # Hour 6
        1.1,   # Hour 7
        1.3,   # Hour 8
        1.4,   # Hour 9
        1.6,   # Hour 10
        1.7,   # Hour 11
        1.9,   # Hour 12
        2.1,   # Hour 13
        2.0,   # Hour 14
        1.8,   # Hour 15
        1.5,   # Hour 16
        1.2,   # Hour 17
        0.9,   # Hour 18 - CHEAP
        1.0,   # Hour 19
        1.1,   # Hour 20
        1.3,   # Hour 21
        1.4,   # Hour 22
        1.5,   # Hour 23
    ]
    
    # Find 3 cheapest hours
    cheap_hours = find_cheapest_hours(prices, 3)
    
    # Should be hours 0, 5, 18 (prices 0.5, 0.8, 0.9)
    assert set(cheap_hours) == {0, 5, 18}, f"Expected {{0, 5, 18}}, got {set(cheap_hours)}"
    
    # Check if current hour (0) is cheap
    assert 0 in cheap_hours, "Current hour should be in cheap hours"
    
    print("✓ test_cheap_boost_current_hour passed")


def test_cheap_boost_realistic_scenario():
    """Test a realistic scenario with typical price patterns."""
    # Night cheap, morning expensive, afternoon normal, evening expensive
    prices = [
        0.3,   # 00:00 - Very cheap
        0.4,   # 01:00 - Cheap
        0.35,  # 02:00 - Very cheap
        0.5,   # 03:00
        0.6,   # 04:00
        0.8,   # 05:00
        1.2,   # 06:00
        1.5,   # 07:00
        2.0,   # 08:00 - Expensive
        1.8,   # 09:00
        1.6,   # 10:00
        1.4,   # 11:00
        1.2,   # 12:00
        1.0,   # 13:00
        0.9,   # 14:00
        0.85,  # 15:00
        1.0,   # 16:00
        1.3,   # 17:00
        1.8,   # 18:00
        2.2,   # 19:00 - Very expensive
        2.0,   # 20:00 - Expensive
        1.5,   # 21:00
        1.0,   # 22:00
        0.6,   # 23:00
    ]
    
    # Find 5 cheapest hours for boosting
    cheap_hours = find_cheapest_hours(prices, 5)
    
    # Should include early morning hours (0, 1, 2) and possibly 3, 23
    assert 0 in cheap_hours, "Hour 0 should be cheap"
    assert 2 in cheap_hours, "Hour 2 should be cheap"
    assert 8 not in cheap_hours, "Hour 8 should not be cheap (expensive)"
    assert 19 not in cheap_hours, "Hour 19 should not be cheap (very expensive)"
    
    print("✓ test_cheap_boost_realistic_scenario passed")
    print(f"  Cheap hours for boosting: {sorted(cheap_hours)}")


if __name__ == "__main__":
    print("Running cheap boost tests...\n")
    test_find_cheapest_hours_basic()
    test_find_cheapest_hours_edge_cases()
    test_cheap_boost_current_hour()
    test_cheap_boost_realistic_scenario()
    print("\n✅ All tests passed!")
