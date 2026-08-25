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


def test_a_yandex_pin_is_read_longitude_first() -> None:
    # `pt` is the marker Yandex draws for a shared point, also written lon,lat.
    coordinates = parse_coordinates_from_text("https://yandex.uz/maps/?pt=37.61,55.75&z=16")

    assert coordinates is not None
    assert (coordinates.latitude, coordinates.longitude) == (55.75, 37.61)


def test_a_yandex_whatshere_pin_outranks_the_viewport() -> None:
    # A resolved "what's here" link carries both the pin and the map centre.
    # The pin is the shared place; `ll` is only where the map was scrolled to.
    coordinates = parse_coordinates_from_text(
        "https://yandex.uz/maps/10335/tashkent/"
        "?ll=69.100000%2C41.100000&whatshere%5Bpoint%5D=69.240562%2C41.311081"
        "&whatshere%5Bzoom%5D=17&z=16"
    )

    assert coordinates is not None
    assert (coordinates.latitude, coordinates.longitude) == (41.311081, 69.240562)


def test_a_yandex_pt_outranks_the_viewport() -> None:
    coordinates = parse_coordinates_from_text(
        "https://yandex.ru/maps/?ll=37.000000%2C55.000000&pt=37.61,55.75&z=15"
    )

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
