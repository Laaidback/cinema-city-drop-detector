CHAIN_SEPARATOR = ":"


def chain_of(cinema_id: str) -> str:
    return cinema_id.split(CHAIN_SEPARATOR, 1)[0]


def local_id(cinema_id: str) -> str:
    return cinema_id.split(CHAIN_SEPARATOR, 1)[-1]


def prefixed(chain: str, cinema_id: str) -> str:
    return f"{chain}{CHAIN_SEPARATOR}{cinema_id}"
