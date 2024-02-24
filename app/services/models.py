from dataclasses import dataclass
from typing import Dict, List

from app.badminton_player.models import Game, Match, Player, PlayerMeta, Standing


@dataclass
class PlayerProfile:
    metadata: PlayerMeta
    player: Player
    games: List[Game]
    matches: List[Match]
    standings: List[Standing]
