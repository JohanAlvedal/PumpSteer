
def calculate_virtual_temperature(real_outdoor_temp, indoor_temp, target_temp, aggressiveness):
    """Calculate the virtual outdoor temperature based on indoor temp diff and aggressiveness."""
    diff = indoor_temp - target_temp
    scaling_factor = aggressiveness * 0.5
    fake_temp = real_outdoor_temp + (diff * scaling_factor)
    if diff < 0:
        return min(fake_temp, 20.0), "heating"
    elif abs(diff) < 0.5:
        return fake_temp, "neutral"
    else:
        return fake_temp, "braking"
