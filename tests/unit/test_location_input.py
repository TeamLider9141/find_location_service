from app.presentation.telegram.location_input import parse_coordinates_from_text


def test_a_typed_pair_is_read_as_coordinates() -> None:
    coordinates = parse_coordinates_from_text("55.75, 37.61")

    assert coordinates is not None
    assert (coordinates.latitude, coordinates.longitude) == (55.75, 37.61)


def test_signs_and_loose_spacing_are_accepted() -> None:
    coordinates = parse_coordinates_from_text("  -33.87 ,  +151.21 ")

    assert coordinates is not None
    assert (coordinates.latitude, coordinates.longitude) == (-33.87, 151.21)


def test_a_google_maps_link_is_read_as_coordinates() -> None:
    coordinates = parse_coordinates_from_text(
        "https://www.google.com/maps/search/?api=1&query=55.75,37.61"
    )

    assert coordinates is not None
    assert (coordinates.latitude, coordinates.longitude) == (55.75, 37.61)


def test_a_yandex_link_gives_longitude_first() -> None:
    # Yandex `ll` is lon,lat. Read in the written order it would file a Moscow
    # place at 37°N — in Turkey.
    coordinates = parse_coordinates_from_text("https://yandex.ru/maps/?ll=37.61,55.75&z=15")

    assert coordinates is not None
    assert (coordinates.latitude, coordinates.longitude) == (55.75, 37.61)


def test_coordinates_in_a_link_path_are_read() -> None:
    coordinates = parse_coordinates_from_text("https://maps.example.test/@55.75,37.61,15z")

    assert coordinates is not None
    assert (coordinates.latitude, coordinates.longitude) == (55.75, 37.61)


def test_an_address_with_numbers_is_not_a_location() -> None:
    # "Ленина 10, 25" reads as a lat/lon pair to a bare regex, which would file
    # the place in Sudan. A driver who types an address has to be asked again,
    # not silently sent 4000 km away.
    assert parse_coordinates_from_text("Ленина 10, 25") is None


def test_text_around_a_pair_is_not_a_location() -> None:
    assert parse_coordinates_from_text("shu yerda 55.75, 37.61 bo'ladi") is None


def test_out_of_range_values_are_refused() -> None:
    assert parse_coordinates_from_text("95.0, 37.61") is None
    assert parse_coordinates_from_text("55.75, 190.0") is None


def test_plain_words_are_not_a_location() -> None:
    assert parse_coordinates_from_text("Газпром") is None
