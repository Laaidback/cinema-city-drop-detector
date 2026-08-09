from dataclasses import dataclass, field


@dataclass(frozen=True)
class Event:
    id: str
    film_id: str
    film_name: str
    cinema_id: str
    business_day: str
    date_time: str
    auditorium: str
    booking_link: str
    attribute_ids: tuple[str, ...]


@dataclass(frozen=True)
class WatchEntry:
    match: str
    cinemas: tuple[str, ...] | None = None
    attributes: tuple[str, ...] | None = None
    notify: bool = True


@dataclass(frozen=True)
class Schedule:
    hours: tuple[int, int]
    before: int = 0
    after: int = 0


@dataclass(frozen=True)
class Config:
    horizon_days: int
    cinemas: tuple[str, ...]
    watch: tuple[WatchEntry, ...]
    schedule: Schedule | None = None


@dataclass(frozen=True)
class Drop:
    watch_key: str
    film_name: str
    cinema_id: str
    events: tuple[Event, ...]
    notify: bool = True


@dataclass
class WatchState:
    warm: bool = False
    seen_events: dict[str, str] = field(default_factory=dict)


@dataclass
class State:
    watch_state: dict[str, WatchState] = field(default_factory=dict)
    cinema_names: dict[str, str] = field(default_factory=dict)
    drop_log: list[dict] = field(default_factory=list)
