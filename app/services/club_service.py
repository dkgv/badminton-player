from dataclasses import dataclass
from typing import List

from app.services import supabase_client
from app.utils import supabase_utils


@dataclass
class Club:
    id: int
    name: str

    @staticmethod
    def from_json(d: dict) -> "Club":
        return Club(id=d["bp_id"], name=d["name"])


def search_club(name: str) -> List[Club]:
    query = " | ".join(name.split(" "))
    fuzzy_clubs = supabase_utils.from_resp(
        supabase_client.from_("clubs").select("*").text_search("name", query).execute(),
        Club,
    )
    if not fuzzy_clubs:
        return []

    return fuzzy_clubs


def get_club(club_id: int) -> Club:
    club = supabase_utils.from_resp(
        supabase_client.from_("clubs").select("*").eq("bp_id", club_id).execute(), Club
    )
    if not club:
        return None

    return club[0]
