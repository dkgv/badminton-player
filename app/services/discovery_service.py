import re
import time
from queue import Queue
from threading import Lock, Thread
from typing import Set

from app.badminton_player.models import Match
from app.services import player_service


class TokenBucket:
    def __init__(self, rate: float):
        self.rate = rate
        self.last = time.time()
        self.lock = Lock()

    def acquire(self):
        with self.lock:
            now = time.time()
            elapsed = now - self.last
            if elapsed < 1/self.rate:
                time.sleep(1/self.rate - elapsed)
            self.last = time.time()


class DiscoveryQueue:
    def __init__(self, num_workers: int = 1, requests_per_second: float = 0.5):
        self.job_queue = Queue()
        self.queued_jobs: Set = set()
        self.lock = Lock()
        self.rate_limiter = TokenBucket(requests_per_second)
        self.pending_jobs: dict = {}

        for _ in range(num_workers):
            Thread(target=self._worker, daemon=True).start()

    def enqueue_match(self, match: Match):
        home_team = clean_team_name(match.home_team)
        away_team = clean_team_name(match.away_team)
        for game in match.games:
            for player in game.home_players():
                self.enqueue_player(player, home_team)
            for player in game.away_players():
                self.enqueue_player(player, away_team)

    def enqueue_player(self, name: str, club: str) -> bool:
        job_key = (name, club)
        with self.lock:
            if job_key in self.queued_jobs:
                return False
            self.queued_jobs.add(job_key)
            self.pending_jobs[job_key] = self.job_queue.qsize()
        self.job_queue.put((name, club))
        return True

    def dequeue_player(self, name: str, club: str) -> bool:
        job_key = (name, club)
        with self.lock:
            if job_key not in self.queued_jobs:
                return False

            # Remove from queued_jobs set
            self.queued_jobs.remove(job_key)

            # Remove from pending_jobs if present
            if job_key in self.pending_jobs:
                del self.pending_jobs[job_key]

            # Note: We can't directly remove items from Queue,
            # but we can filter them out in the worker
        return True

    def _worker(self) -> None:
        while True:
            try:
                name, club = self.job_queue.get(block=True)
                job_key = (name, club)

                # Skip processing if job was dequeued
                with self.lock:
                    if job_key not in self.queued_jobs:
                        print(f"Job {job_key} was dequeued")
                        self.job_queue.task_done()
                        continue

                    if job_key in self.pending_jobs:
                        del self.pending_jobs[job_key]

                if "Ikke fremmødt" not in name:
                    self.rate_limiter.acquire()
                    player_service.search_player(name, club)
                    print(f"Discovered player: {name} ({club})")

                with self.lock:
                    self.queued_jobs.remove(job_key)

                self.job_queue.task_done()
            except Exception as e:
                print(f"Worker error: {e}")


_queue = DiscoveryQueue()


def enqueue_match(match: Match, exclude: Set[str] = set()):
    for game in match.games:
        for player in game.home_players():
            if player not in exclude:
                _queue.enqueue_player(player, match.home_team)
        for player in game.away_players():
            if player not in exclude:
                _queue.enqueue_player(player, match.away_team)


def dequeue_player(name: str, club: str):
    _queue.dequeue_player(name, club)


def clean_team_name(team: str | None) -> str | None:
    if not team:
        return None
    match = re.match(r"^(.*?)(?:\s\d+)?$", team)
    return match.group(1) if match else team
