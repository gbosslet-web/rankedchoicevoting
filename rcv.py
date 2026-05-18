from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import floor
from typing import Any


EPSILON = 1e-9


@dataclass
class WeightedBallot:
    preferences: list[str]
    weight: float = 1.0


def _candidate_name(candidate_id: str, candidates: dict[str, str]) -> str:
    return candidates.get(candidate_id, candidate_id)


def _next_active_preference(ballot: WeightedBallot, active: set[str]) -> str | None:
    for candidate_id in ballot.preferences:
        if candidate_id in active:
            return candidate_id
    return None


def _tally(ballots: list[WeightedBallot], active: set[str]) -> tuple[dict[str, float], dict[str, list[int]]]:
    totals = {candidate_id: 0.0 for candidate_id in active}
    assignments = {candidate_id: [] for candidate_id in active}

    for index, ballot in enumerate(ballots):
        candidate_id = _next_active_preference(ballot, active)
        if candidate_id is None:
            continue
        totals[candidate_id] += ballot.weight
        assignments[candidate_id].append(index)

    return totals, assignments


def _round_snapshot(
    round_number: int,
    totals: dict[str, float],
    candidates: dict[str, str],
    action: str,
    elected: list[str],
    eliminated: list[str],
    continuing: set[str],
) -> dict[str, Any]:
    ordered_totals = sorted(
        [
            {
                "candidate_id": candidate_id,
                "candidate": _candidate_name(candidate_id, candidates),
                "votes": round(votes, 4),
                "status": (
                    "elected"
                    if candidate_id in elected
                    else "eliminated"
                    if candidate_id in eliminated
                    else "continuing"
                    if candidate_id in continuing
                    else "inactive"
                ),
            }
            for candidate_id, votes in totals.items()
        ],
        key=lambda row: (-row["votes"], row["candidate"].lower()),
    )

    return {
        "round": round_number,
        "action": action,
        "totals": ordered_totals,
        "elected": [
            {"candidate_id": candidate_id, "candidate": _candidate_name(candidate_id, candidates)}
            for candidate_id in elected
        ],
        "eliminated": [
            {"candidate_id": candidate_id, "candidate": _candidate_name(candidate_id, candidates)}
            for candidate_id in eliminated
        ],
    }


def tabulate_stv(
    rankings: list[list[str]],
    candidates: dict[str, str],
    seats_available: int,
) -> dict[str, Any]:
    """Tabulate a multi-seat ranked-choice election with a Droop quota.

    This implements a practical STV flow for board elections:
    first preferences are counted, candidates at or above quota are elected,
    their surplus is transferred fractionally, and the lowest continuing
    candidate is eliminated when no one reaches quota.
    """
    candidate_ids = list(candidates.keys())
    seats = max(1, int(seats_available or 1))
    cleaned_rankings = [
        [candidate_id for candidate_id in ranking if candidate_id in candidates]
        for ranking in rankings
        if ranking
    ]
    ballots = [WeightedBallot(preferences=ranking) for ranking in cleaned_rankings]
    total_ballots = len(ballots)
    quota = floor(total_ballots / (seats + 1)) + 1 if total_ballots else 0

    active = set(candidate_ids)
    elected: list[str] = []
    eliminated: list[str] = []
    rounds: list[dict[str, Any]] = []
    round_number = 1

    if not candidate_ids:
        return {
            "quota": quota,
            "total_ballots": total_ballots,
            "winners": [],
            "rounds": [],
        }

    while active and len(elected) < seats:
        totals, assignments = _tally(ballots, active)

        remaining_seats = seats - len(elected)
        if len(active) <= remaining_seats:
            for candidate_id in sorted(active, key=lambda cid: (-totals.get(cid, 0.0), candidates[cid].lower())):
                if candidate_id not in elected:
                    elected.append(candidate_id)
            rounds.append(
                _round_snapshot(
                    round_number,
                    totals,
                    candidates,
                    "Remaining continuing candidates fill the remaining seats.",
                    elected,
                    eliminated,
                    active,
                )
            )
            break

        newly_elected = sorted(
            [
                candidate_id
                for candidate_id, votes in totals.items()
                if votes + EPSILON >= quota and candidate_id not in elected
            ],
            key=lambda candidate_id: (-totals[candidate_id], candidates[candidate_id].lower()),
        )

        if newly_elected:
            candidate_id = newly_elected[0]
            total_votes = totals.get(candidate_id, 0.0)
            elected.append(candidate_id)
            active.discard(candidate_id)

            surplus = max(0.0, total_votes - quota)
            transfer_value = surplus / total_votes if total_votes > EPSILON else 0.0
            for ballot_index in assignments.get(candidate_id, []):
                ballots[ballot_index].weight *= transfer_value

            action = (
                f"{_candidate_name(candidate_id, candidates)} elected with "
                f"{total_votes:.2f} votes. Surplus transfer value: {transfer_value:.4f}."
            )
            rounds.append(
                _round_snapshot(
                    round_number,
                    totals,
                    candidates,
                    action,
                    deepcopy(elected),
                    deepcopy(eliminated),
                    set(active),
                )
            )
            round_number += 1
            continue

        lowest_candidate = min(totals, key=lambda cid: (totals[cid], candidates[cid].lower()))
        active.discard(lowest_candidate)
        eliminated.append(lowest_candidate)
        rounds.append(
            _round_snapshot(
                round_number,
                totals,
                candidates,
                f"{_candidate_name(lowest_candidate, candidates)} eliminated and ballots transferred.",
                deepcopy(elected),
                deepcopy(eliminated),
                set(active),
            )
        )
        round_number += 1

    winners = [
        {"candidate_id": candidate_id, "candidate": _candidate_name(candidate_id, candidates)}
        for candidate_id in elected[:seats]
    ]

    return {
        "quota": quota,
        "total_ballots": total_ballots,
        "winners": winners,
        "rounds": rounds,
    }
