import calendar
from datetime import datetime, timedelta


def _days_in_month(year, month):
    return calendar.monthrange(year, month)[1]


def next_occurrence_search(
    now,
    hour,
    minute,
    recurrence,
    selected_days,
    selected_weekdays,
    selected_months,
    selected_years,
    tz,
    max_days=365 * 5,
):
    """
    Find the next scheduled occurrence.

    A selected day that exceeds the number of days in a month
    maps to the first day of the following month.
    """
    start_dt = now
    start_date = now.date()

    for offset in range(0, max_days + 1):
        candidate_date = start_date + timedelta(days=offset)
        y, m, d = candidate_date.year, candidate_date.month, candidate_date.day

        if selected_years and y not in selected_years:
            continue

        if selected_months and m not in selected_months:
            continue

        match = False

        if recurrence == "weekly":
            if selected_weekdays:
                if candidate_date.weekday() in selected_weekdays:
                    match = True
            else:
                match = True
        else:
            if selected_days:
                if d in selected_days:
                    match = True
                elif d == 1:
                    prev_m = m - 1
                    prev_y = y

                    if prev_m == 0:
                        prev_m = 12
                        prev_y -= 1

                    prev_dim = _days_in_month(prev_y, prev_m)

                    for selected_day in selected_days:
                        if selected_day > prev_dim:
                            match = True
                            break
            else:
                match = True

        if not match:
            continue

        try:
            candidate_naive = datetime(y, m, d, hour, minute)
        except ValueError:
            continue

        try:
            candidate_dt = tz.localize(candidate_naive)
        except Exception:
            candidate_dt = candidate_naive.replace(tzinfo=tz)

        if candidate_dt > start_dt:
            return candidate_dt

    return None


def prepare_recurrence_settings(
    recurrence_mode,
    daily_days,
    weekly_days,
    months,
    years,
):
    """Normalize a schedule block's recurrence settings for date searching."""
    if recurrence_mode == "daily":
        recurrence = "daily"
        selected_days = set(daily_days)
        selected_weekdays = set()
    elif recurrence_mode == "weekly":
        recurrence = "weekly"
        selected_days = set()
        selected_weekdays = set(weekly_days)
    else:
        recurrence = "daily"
        selected_days = set()
        selected_weekdays = set()

    return (
        recurrence,
        selected_days,
        selected_weekdays,
        set(months) if months else set(),
        set(years) if years else set(),
    )
