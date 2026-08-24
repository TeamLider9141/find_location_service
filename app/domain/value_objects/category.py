from enum import Enum


class PlaceCategory(str, Enum):
    RESTAURANT = "restaurant"
    CAFE = "cafe"
    FUEL = "fuel"
    HOTEL = "hotel"
    PARKING = "parking"
    CAR_SERVICE = "car_service"
    # Last on purpose: it is the fallback, and the keyboards draw the categories
    # in declaration order. Offered first it would invite a driver to skip
    # reading the real ones.
    OTHER = "other"
