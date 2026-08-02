from dataclasses import FrozenInstanceError

import pytest

from ccdrop.models import Event


def test_event_is_immutable():
    event = Event(
        id="1600867",
        film_id="8099d2r",
        film_name="Backrooms",
        cinema_id="1090",
        business_day="2026-08-15",
        date_time="2026-08-15T18:30:00",
        auditorium="Sala 4",
        booking_link="https://tickets.cinema-city.pl/api/order/1600867",
        attribute_ids=("imax",),
    )

    with pytest.raises(FrozenInstanceError):
        event.id = "inny"
