"""
Tests for the simplified boost functionality.
Boost mode activates during the cheapest hours of the day.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))

import ha_test_stubs  # noqa: F401 - sets up Home Assistant stubs

from custom_components.pumpsteer.pre_boost import check_combined_preboost
import pytest


def test_boost_activates_in_cheapest_hour():
    """Test that boost activates when current hour is the cheapest."""
    # Prices where hour 0 (current) is the cheapest
    prices = [0.5, 1.0, 1.2, 1.5, 1.3, 1.1, 0.9, 0.8, 1.4, 1.6, 
              1.7, 1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6,
              2.7, 2.8, 2.9, 3.0]
    
    # With aggressiveness 3, we target 5 cheapest hours (2 + 3)
    result = check_combined_preboost(
        temp_csv="",  # Not used in simplified mode
        prices=prices,
        aggressiveness=3.0
    )
    
    assert result == "preboost", "Should activate boost in cheapest hour"


def test_boost_does_not_activate_in_expensive_hour():
    """Test that boost does not activate when current hour is expensive."""
    # Prices where hour 0 (current) is the most expensive
    prices = [3.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3,
              1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.1, 2.2, 2.3,
              2.4, 2.5, 2.6, 2.7]
    
    result = check_combined_preboost(
        temp_csv="",
        prices=prices,
        aggressiveness=3.0
    )
    
    assert result is None, "Should not activate boost in expensive hour"


def test_boost_hours_scale_with_aggressiveness():
    """Test that higher aggressiveness means more boost hours."""
    # Prices where hour 0 is the 3rd cheapest
    prices = [0.7, 0.5, 0.6, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6,
              1.7, 1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6,
              2.7, 2.8, 2.9, 3.0]
    
    # With aggressiveness 0, we target 2 cheapest hours (2 + 0)
    # Current hour (0.7) is 3rd cheapest, so should not boost
    result_low = check_combined_preboost(
        temp_csv="",
        prices=prices,
        aggressiveness=0.0
    )
    assert result_low is None, "Should not boost with low aggressiveness"
    
    # With aggressiveness 3, we target 5 cheapest hours (2 + 3)
    # Current hour (0.7) is 3rd cheapest, so should boost
    result_high = check_combined_preboost(
        temp_csv="",
        prices=prices,
        aggressiveness=3.0
    )
    assert result_high == "preboost", "Should boost with higher aggressiveness"


def test_boost_with_aggressiveness_5():
    """Test that aggressiveness 5 targets 7 cheapest hours."""
    # Prices where hour 0 is the 6th cheapest
    prices = [0.9, 0.5, 0.6, 0.7, 0.8, 0.85, 1.0, 1.1, 1.2, 1.3,
              1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.1, 2.2, 2.3,
              2.4, 2.5, 2.6, 2.7]
    
    # With aggressiveness 5, we target 7 cheapest hours (2 + 5)
    # Current hour (0.9) is 6th cheapest, so should boost
    result = check_combined_preboost(
        temp_csv="",
        prices=prices,
        aggressiveness=5.0
    )
    assert result == "preboost", "Should boost at 6th cheapest with aggressiveness 5"


def test_boost_handles_short_price_list():
    """Test that boost handles price lists shorter than 24 hours."""
    # Only 12 hours of prices
    prices = [0.5, 1.0, 1.2, 1.5, 1.3, 1.1, 0.9, 0.8, 1.4, 1.6, 1.7, 1.8]
    
    result = check_combined_preboost(
        temp_csv="",
        prices=prices,
        aggressiveness=3.0
    )
    
    assert result == "preboost", "Should work with shorter price lists"


def test_boost_handles_insufficient_data():
    """Test that boost returns None when there's not enough price data."""
    # Only 1 hour of prices - insufficient for meaningful boost calculation
    prices = [0.5]
    
    result = check_combined_preboost(
        temp_csv="",
        prices=prices,
        aggressiveness=3.0
    )
    
    # With only 1 price, we should still activate if it's the cheapest
    # But the logic checks if we have enough data for boost_hours
    # Since boost_hours = 5 and we only have 1 price, it should return None
    assert result is None, "Should return None with insufficient data"


def test_boost_handles_empty_prices():
    """Test that boost returns None when price list is empty."""
    prices = []
    
    result = check_combined_preboost(
        temp_csv="",
        prices=prices,
        aggressiveness=3.0
    )
    
    assert result is None, "Should return None with empty prices"


def test_boost_with_all_same_prices():
    """Test boost behavior when all prices are the same."""
    # All prices equal
    prices = [1.0] * 24
    
    # With all prices equal, current hour should be in the cheapest set
    result = check_combined_preboost(
        temp_csv="",
        prices=prices,
        aggressiveness=3.0
    )
    
    assert result == "preboost", "Should boost when all prices are equal"


def test_boost_marginal_case():
    """Test boost behavior at the boundary of cheapest hours."""
    # Create prices where hour 0 is exactly at the threshold
    # With aggressiveness 3, we want 5 cheapest hours
    # Make hour 0 the 5th cheapest (should boost)
    prices = [0.8, 0.5, 0.6, 0.7, 0.75, 1.0, 1.1, 1.2, 1.3, 1.4,
              1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4,
              2.5, 2.6, 2.7, 2.8]
    
    result = check_combined_preboost(
        temp_csv="",
        prices=prices,
        aggressiveness=3.0
    )
    
    assert result == "preboost", "Should boost at boundary of cheapest hours"
    
    # Make hour 0 the 6th cheapest (should not boost)
    prices = [0.85, 0.5, 0.6, 0.7, 0.75, 0.8, 1.0, 1.1, 1.2, 1.3,
              1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.1, 2.2, 2.3,
              2.4, 2.5, 2.6, 2.7]
    
    result = check_combined_preboost(
        temp_csv="",
        prices=prices,
        aggressiveness=3.0
    )
    
    assert result is None, "Should not boost just outside cheapest hours"
