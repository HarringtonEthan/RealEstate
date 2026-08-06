"""Triangle geographic knowledge layer.

Market geography only — used to judge whether a signal is in Diane's service
area and how central it is. Never used as a demographic proxy of any kind.
"""

# tier: core = Diane's primary market, extended = takes the business, adjacent = case-by-case
AREAS = {
    "raleigh": ("Raleigh", "Wake", "core"),
    "north raleigh": ("North Raleigh", "Wake", "core"),
    "downtown raleigh": ("Downtown Raleigh", "Wake", "core"),
    "cary": ("Cary", "Wake", "core"),
    "apex": ("Apex", "Wake", "core"),
    "wake forest": ("Wake Forest", "Wake", "core"),
    "holly springs": ("Holly Springs", "Wake", "core"),
    "fuquay-varina": ("Fuquay-Varina", "Wake", "core"),
    "fuquay varina": ("Fuquay-Varina", "Wake", "core"),
    "fuquay": ("Fuquay-Varina", "Wake", "core"),
    "garner": ("Garner", "Wake", "core"),
    "knightdale": ("Knightdale", "Wake", "core"),
    "wendell": ("Wendell", "Wake", "core"),
    "rolesville": ("Rolesville", "Wake", "core"),
    "morrisville": ("Morrisville", "Wake", "core"),
    "zebulon": ("Zebulon", "Wake", "core"),
    "brier creek": ("Brier Creek (Raleigh)", "Wake", "core"),
    "five points": ("Five Points (Raleigh)", "Wake", "core"),
    "itb": ("Inside the Beltline (Raleigh)", "Wake", "core"),
    "durham": ("Durham", "Durham", "extended"),
    "chapel hill": ("Chapel Hill", "Orange", "extended"),
    "carrboro": ("Carrboro", "Orange", "extended"),
    "rtp": ("Research Triangle Park", "Durham", "extended"),
    "research triangle": ("Research Triangle Park", "Durham", "extended"),
    "clayton": ("Clayton", "Johnston", "extended"),
    "youngsville": ("Youngsville", "Franklin", "adjacent"),
    "franklinton": ("Franklinton", "Franklin", "adjacent"),
    "angier": ("Angier", "Harnett", "adjacent"),
    "hillsborough": ("Hillsborough", "Orange", "adjacent"),
    "pittsboro": ("Pittsboro", "Chatham", "adjacent"),
    "triangle": ("Triangle (general)", "Wake", "core"),
    "wake county": ("Wake County (general)", "Wake", "core"),
}

# Signals of an inbound relocation to the area even when no town is named yet.
RELOCATION_HINTS = ("moving to nc", "relocating to north carolina", "moving to north carolina")


def match_area(text: str):
    """Return (display_name, county, tier) for the best area mention in text, or None."""
    t = (text or "").lower()
    best = None
    for key, val in AREAS.items():
        if key in t:
            if best is None or _tier_rank(val[2]) > _tier_rank(best[2]):
                best = val
    if best is None and any(h in t for h in RELOCATION_HINTS):
        best = ("North Carolina (inbound, area TBD)", None, "adjacent")
    return best


def _tier_rank(tier: str) -> int:
    return {"core": 3, "extended": 2, "adjacent": 1}.get(tier, 0)


def location_points(tier: str | None) -> int:
    """Location relevance component of the lead score (0-15)."""
    return {"core": 15, "extended": 10, "adjacent": 8}.get(tier or "", 0)
