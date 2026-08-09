from typing import Callable, Protocol

from ccdrop.api import ApiClient, CinemaCityProvider
from ccdrop.models import Event


class Provider(Protocol):
    def fetch(self, cinema_id: str, today: str, horizon_days: int) -> list[Event] | None: ...

    def cinema_names(self, today: str, horizon_days: int) -> dict[str, str]: ...


PROVIDERS: dict[str, Callable[[], Provider]] = {
    CinemaCityProvider.chain: lambda: CinemaCityProvider(ApiClient()),
}

DEFAULT_CHAIN = CinemaCityProvider.chain


def build_providers() -> dict[str, Provider]:
    return {chain: build() for chain, build in PROVIDERS.items()}
