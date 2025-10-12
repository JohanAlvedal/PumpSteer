"""Tests for cheap_boost module."""
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import just the cheap_boost module without triggering __init__.py
import importlib.util
spec = importlib.util.spec_from_file_location(
    "cheap_boost",
    os.path.join(os.path.dirname(__file__), '../custom_components/pumpsteer/cheap_boost.py')
)
cheap_boost = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cheap_boost)

check_cheap_boost = cheap_boost.check_cheap_boost


def test_cheap_boost_activates_when_current_hour_is_cheapest():
    """Test that cheap boost activates when current hour is among cheapest."""
    # Current hour (index 0) has price 0.5, which is the cheapest
    prices = [0.5, 1.0, 1.2, 0.8, 1.5, 1.3]
    result = check_cheap_boost(prices, boost_hours=3)
    assert result == "cheap_boost", "Should activate when current hour is among 3 cheapest"


def test_cheap_boost_does_not_activate_when_current_hour_is_expensive():
    """Test that cheap boost does not activate when current hour is not among cheapest."""
    # Current hour (index 0) has price 1.5, which is the most expensive
    prices = [1.5, 1.0, 0.8, 0.5, 0.6, 0.7]
    result = check_cheap_boost(prices, boost_hours=3)
    assert result is None, "Should not activate when current hour is expensive"


def test_cheap_boost_with_single_boost_hour():
    """Test cheap boost with only 1 boost hour."""
    # Current hour must be THE cheapest
    prices = [0.5, 1.0, 1.2, 0.8]
    result = check_cheap_boost(prices, boost_hours=1)
    assert result == "cheap_boost", "Should activate when current hour is the cheapest"
    
    # Current hour is second cheapest, should not activate
    prices = [0.8, 1.0, 1.2, 0.5]
    result = check_cheap_boost(prices, boost_hours=1)
    assert result is None, "Should not activate when current hour is not the cheapest"


def test_cheap_boost_with_zero_boost_hours():
    """Test that cheap boost is disabled when boost_hours is 0."""
    prices = [0.5, 1.0, 1.2, 0.8]
    result = check_cheap_boost(prices, boost_hours=0)
    assert result is None, "Should not activate when boost_hours is 0"


def test_cheap_boost_with_empty_prices():
    """Test that cheap boost handles empty price list."""
    prices = []
    result = check_cheap_boost(prices, boost_hours=3)
    assert result is None, "Should not activate with empty prices"


def test_cheap_boost_with_insufficient_data():
    """Test that cheap boost handles insufficient price data."""
    prices = [0.5]  # Only 1 hour of data
    result = check_cheap_boost(prices, boost_hours=3)
    assert result is None, "Should not activate with insufficient data"


def test_cheap_boost_lookahead_limits_window():
    """Test that lookahead parameter limits the price window."""
    # Current hour is cheapest in first 4 hours but not overall
    prices = [0.5, 1.0, 1.2, 0.8, 0.3, 0.2, 0.1]
    result = check_cheap_boost(prices, boost_hours=2, lookahead_hours=4)
    assert result == "cheap_boost", "Should only consider first 4 hours"
    
    # With full lookahead, current hour is not among 2 cheapest
    result = check_cheap_boost(prices, boost_hours=2, lookahead_hours=24)
    assert result is None, "Should consider all hours when lookahead is high"


def test_cheap_boost_boundary_case():
    """Test cheap boost at the boundary of cheapest hours."""
    # Current hour is exactly the 3rd cheapest
    prices = [0.8, 1.0, 0.5, 0.6, 1.5]
    result = check_cheap_boost(prices, boost_hours=3)
    assert result == "cheap_boost", "Should activate when current hour is exactly at boundary"


if __name__ == "__main__":
    # Run all tests
    test_cheap_boost_activates_when_current_hour_is_cheapest()
    test_cheap_boost_does_not_activate_when_current_hour_is_expensive()
    test_cheap_boost_with_single_boost_hour()
    test_cheap_boost_with_zero_boost_hours()
    test_cheap_boost_with_empty_prices()
    test_cheap_boost_with_insufficient_data()
    test_cheap_boost_lookahead_limits_window()
    test_cheap_boost_boundary_case()
    print("All tests passed!")
