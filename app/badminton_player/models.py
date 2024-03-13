from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from markupsafe import Markup


@dataclass
class Standing:
    # e.g. Rangliste, Rangliste Single
    category: str
    # e.g. U15 B
    tier: str
    num_points: int
    num_matches: int
    ranking: int

    def to_dict(self, player_id: int) -> dict:
        return {
            "category": self.category,
            "tier": self.tier,
            "num_points": self.num_points,
            "num_matches": self.num_matches,
            "ranking": self.ranking,
            "bp_player_id": player_id,
        }

    @staticmethod
    def from_json(d: dict) -> "Standing":
        return Standing(
            category=d["category"],
            tier=d["tier"],
            num_points=d["num_points"],
            num_matches=d["num_matches"],
            ranking=d["ranking"],
        )


@dataclass
class Set:
    number: int
    home_points: int
    away_points: int

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "home_points": self.home_points,
            "away_points": self.away_points,
        }

    def to_html(self, winner: str) -> Markup:
        if winner == "home":
            html = f"<b>{self.home_points}</b> - {self.away_points}"
        else:
            html = f"{self.home_points} - <b>{self.away_points}</b>"
        return Markup(html)


@dataclass
class Game:
    date: datetime
    category: str
    sets: List[Set]
    home_player1: Optional[str]
    home_player2: Optional[str]
    away_player1: Optional[str]
    away_player2: Optional[str]

    def contains(self, player_name: str) -> bool:
        return player_name in self.players()

    def home_players(self) -> List[str]:
        home_players = []
        if self.home_player1:
            home_players.append(self.home_player1)
        if self.home_player2:
            home_players.append(self.home_player2)
        return home_players

    def away_players(self) -> List[str]:
        away_players = []
        if self.away_player1:
            away_players.append(self.away_player1)
        if self.away_player2:
            away_players.append(self.away_player2)
        return away_players

    def players(self) -> List[str]:
        return self.home_players() + self.away_players()

    def get_winner(self) -> str:
        mod = lambda x: x if x and "Ikke fremmødt" not in x else None
        home1, home2 = mod(self.home_player1), mod(self.home_player2)
        away1, away2 = mod(self.away_player1), mod(self.away_player2)
        if not home1 and not home2:
            # home did not show up
            return "away"
        if not away1 and not away2:
            # away did not show up
            return "home"
        if home1 and home2 and ((away1 and not away2) or (away2 and not away1)):
            # away missing a player
            return "home"
        if away1 and away2 and ((home1 and not home2) or (home2 and not home1)):
            # home missing a player
            return "away"
        home = sum([1 for s in self.sets if s.home_points > s.away_points])
        away = sum([1 for s in self.sets if s.home_points < s.away_points])
        return "home" if home > away else "away"

    def won_by(self, player_name: str) -> bool:
        if self.get_winner() == "home":
            return player_name in [self.home_player1, self.home_player2]
        else:
            return player_name in [self.away_player1, self.away_player2]

    def to_dict(self) -> dict:
        return {
            "date": self.date.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "category": self.category,
            "sets": [s.to_dict() for s in self.sets],
            "home_player1": self.home_player1,
            "home_player2": self.home_player2,
            "away_player1": self.away_player1,
            "away_player2": self.away_player2,
        }

    @staticmethod
    def from_json(d: dict) -> "Game":
        sets = []
        for s in d["sets"]:
            sets.append(
                Set(
                    number=s["number"],
                    home_points=s["home_points"],
                    away_points=s["away_points"],
                )
            )

        return Game(
            category=d["category"],
            date=datetime.strptime(d["date"], "%Y-%m-%dT%H:%M:%S%z"),
            sets=sets,
            home_player1=d["home_player1"] if "home_player1" in d else None,
            home_player2=d["home_player2"] if "home_player2" in d else None,
            away_player1=d["away_player1"] if "away_player1" in d else None,
            away_player2=d["away_player2"] if "away_player2" in d else None,
        )


@dataclass
class MatchMeta:
    id: int
    sort: int
    date: datetime
    group: str
    team1: Optional[str]
    team2: Optional[str]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "date": self.date,
            "group": self.group,
            "team1": self.team1,
            "team2": self.team2,
        }


@dataclass
class Match:
    id: int
    date: datetime
    group: str
    games: List[Game]
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    home_club: Optional[str] = None
    away_club: Optional[str] = None

    @property
    def home_points(self) -> int:
        return sum([1 for g in self.games if g.get_winner() == "home"])

    @property
    def away_points(self) -> int:
        return sum([1 for g in self.games if g.get_winner() == "away"])

    def get_winner(self) -> str:
        return "home" if self.home_points > self.away_points else "away"

    def on_winning_team(self, player_name: str) -> bool:
        home_players = []
        away_players = []
        for g in self.games:
            home_players.append(g.home_player1)
            if g.home_player2:
                home_players.append(g.home_player2)

            away_players.append(g.away_player1)
            if g.away_player2:
                away_players.append(g.away_player2)

        home_players = [p for p in home_players if p]
        away_players = [p for p in away_players if p]

        if not self.date:
            players = home_players if home_players else away_players
            return player_name in players

        winner = self.get_winner()
        return (
            player_name in home_players
            if winner == "home"
            else player_name in away_players
        )


@dataclass
class Player:
    id: int
    name: str
    club_name: str
    club_id: int
    birth_date: datetime

    def get_age(self) -> int:
        today = datetime.today()
        return abs(
            today.year
            - self.birth_date.year
            - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))
        )

    def to_dict(self) -> dict:
        return {
            "bp_id": self.id,
            "bp_name": self.name,
            "bp_club_id": self.club_id,
            "birthdate": (
                self.birth_date.isoformat()
                if self.birth_date
                else "1970-01-01T00:00:00+00:00"
            ),
        }

    @staticmethod
    def from_json(d: dict) -> "Player":
        return Player(
            id=d["bp_id"],
            name=d["bp_name"],
            club_name=d["clubs"]["name"] if "clubs" in d else "",
            club_id=d["bp_club_id"],
            birth_date=datetime.strptime(d["birthdate"], "%Y-%m-%dT%H:%M:%S%z"),
        )


@dataclass
class PlayerMeta:
    season_start_points: int
    standings: List[Standing]
    match_metadata: List[MatchMeta]
