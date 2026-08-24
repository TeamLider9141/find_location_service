from enum import Enum


class PlaceCategory(str, Enum):
    RESTAURANT = "restaurant"
    CAFE = "cafe"
    FUEL = "fuel"
    HOTEL = "hotel"
    PARKING = "parking"
    CAR_SERVICE = "car_service"
    MOSQUE = "mosque"
    # The two borders fold under one "Chegara hududlari" button on the
    # keyboards; storage stays flat, so search and counts treat them as
    # ordinary categories.
    BORDER_KZ = "border_kz"
    BORDER_RU = "border_ru"
    # Last on purpose: it is the fallback, and the keyboards draw the categories
    # in declaration order. Offered first it would invite a driver to skip
    # reading the real ones.
    OTHER = "other"
