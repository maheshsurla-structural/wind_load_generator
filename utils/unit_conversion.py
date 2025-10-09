def convert_distance_from_ft(value_ft, current_unit):
    conversion_factors = {
        "M": 0.3048,
        "CM": 30.48,
        "MM": 304.8,
        "IN": 12,
        "FT": 1
    }
    return value_ft * conversion_factors.get(current_unit.upper(), 1)