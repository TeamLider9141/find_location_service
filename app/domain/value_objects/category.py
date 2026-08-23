from enum import Enum


class PlaceCategory(str, Enum):
    RESTAURANT = "restaurant"
    CAFE = "cafe"
    FUEL = "fuel"
    HOTEL = "hotel"
    PARKING = "parking"
    CAR_SERVICE = "car_service"
