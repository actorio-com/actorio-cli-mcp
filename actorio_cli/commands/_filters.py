"""Shared advanced-filter plumbing for the search commands.

Flag names map 1:1 to the webapp filterset query params
(ecommercer/filters.py ProductFilter and friends), so anything the web UI
can filter on, the CLI can too. Range filters use <name>_min/<name>_max;
boolean toggles send 'true'; multi-value flags repeat the param.
"""

# (flag kwargs are declared in each command; this module holds the shared
# mapping/normalisation so products/favorites/amazon stay consistent)

_BOOL_PARAMS = (
    "missing_fba",
    "multipack",
    "variations",
    "hazmat",
    "suppressed_buybox",
    "actorio_only",
)


def build_params(**values) -> dict:
    """Convert collected option values into webapp query params.

    Drops None/empty; True booleans become 'true'; lists pass through so
    httpx repeats the param (store, size, category).
    """
    params: dict = {}
    for key, value in values.items():
        if value is None:
            continue
        if key in _BOOL_PARAMS:
            if value:
                params[key] = "true"
            continue
        if isinstance(value, (list, tuple)):
            if value:
                params[key] = list(value)
            continue
        if value == "":
            continue
        params[key] = value
    return params


RANGE_HELP = "Webapp-equivalent filter; combine _min/_max as needed"
LOGIC_HELP = "Blank = ANY marketplace, 'all' = ALL marketplaces"
