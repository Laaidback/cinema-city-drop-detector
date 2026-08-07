from datetime import datetime
from zoneinfo import ZoneInfo

from ccdrop.models import Schedule

WARSAW = ZoneInfo("Europe/Warsaw")


def in_window(schedule: Schedule, moment: datetime) -> bool:
    local = moment.astimezone(WARSAW)
    if local.minute >= 60 - schedule.before:
        hour = (local.hour + 1) % 24
    elif local.minute <= schedule.after:
        hour = local.hour
    else:
        return False
    start, end = schedule.hours
    return start <= hour <= end
