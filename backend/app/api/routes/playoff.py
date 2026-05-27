from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from typing import Optional

from backend.app.api.deps import SessionDep
from backend.app.crud.group_participant import get_participants_by_group
from backend.app.crud.group_stage import get_groups_by_tournament
from sqlalchemy import select
from common.db.models import (
    PlayoffStage,
    PlayoffBracket,
    PlayoffRound,
    PlayoffMatch,
    BracketType,
    Tournament,
    TournamentParticipant,
    User,
)
from common.db.models.category import Category
from common.schemas import (
    PlayoffStageSchema,
    PlayoffBracketSchema,
    PlayoffRoundSchema,
    PlayoffMatchSchema,
)


# --- Pydantic schema for match result input ---
class MatchResultInput(BaseModel):
    score1: int
    score2: int


router = APIRouter()


# Utility: round names by number of participants
ROUND_NAMES = {
    2: "Финал",
    4: "1/2 финала",
    8: "1/4 финала",
    16: "1/8 финала",
    32: "1/16 финала",
    64: "1/32 финала",
}


import math


def get_round_name(n):
    # Если n — степень двойки, используем стандартные названия
    if n in ROUND_NAMES:
        return ROUND_NAMES[n]
    # Иначе ищем ближайшую большую степень двойки
    if n > 2:
        pow2 = 2 ** math.ceil(math.log2(n))
        return ROUND_NAMES.get(pow2, f"{n}-player round")
    return f"{n}-player round"


COMPRESSED_PRELIMINARY_ROUND_NAME = "ОЭ"


def is_compressed_bracket_match_counts(match_counts: list[int]) -> bool:
    if len(match_counts) < 3:
        return False

    base_match_count = match_counts[1]
    if base_match_count < 2 or match_counts[0] < 1 or match_counts[0] >= base_match_count * 2:
        return False

    expected = []
    while base_match_count >= 1:
        expected.append(base_match_count)
        base_match_count //= 2

    return match_counts[1:] == expected


def get_playoff_round_name(
    round_number: int,
    match_count: int,
    bracket_match_counts: list[int],
) -> str:
    if is_compressed_bracket_match_counts(bracket_match_counts) and round_number == 1:
        return COMPRESSED_PRELIMINARY_ROUND_NAME

    return get_round_name(match_count * 2)


# Удалено использование bracketool.knockout, строим сетку вручную
async def generate_bracket(session, participants, bracket_type, stage_id):
    """
    Generate bracket, rounds, and matches for given participants (без bracketool).
    В первом раунде назначаются реальные участники, в остальных — participant_id = None.
    """
    import math

    n = len(participants)
    pow2 = 1 << (n - 1).bit_length()
    byes = pow2 - n
    ids = [p.id if hasattr(p, "id") else p for p in participants]
    bracket = PlayoffBracket(type=bracket_type, stage_id=stage_id)
    session.add(bracket)
    await session.flush()
    rounds = int(math.log2(pow2))
    # Топ-сиды получают байи, нижние сиды играют в первом раунде.
    # Чередование pair/bye гарантирует, что победитель пары встретит нужный топ-сид в следующем раунде.
    bye_ids = ids[:byes]   # топ-сиды → автовыход
    play_ids = ids[byes:]  # нижние сиды → играют в 1-м раунде
    pairs = []
    for i in range(0, len(play_ids), 2):
        pairs.append((play_ids[i], play_ids[i + 1]))
    current_participants = []
    for r in range(rounds):
        round_model = PlayoffRound(number=r + 1, bracket_id=bracket.id)
        session.add(round_model)
        await session.flush()
        matches = []
        next_round_participants = []
        if r == 0:
            # Чередуем: пара → бай → пара → бай ...
            # Это гарантирует, что в следующем раунде победитель пары встречает топ-сид рядом с ним
            pair_idx = 0
            bye_idx = 0
            while pair_idx < len(pairs) or bye_idx < len(bye_ids):
                if pair_idx < len(pairs):
                    p1_id, p2_id = pairs[pair_idx]
                    match = PlayoffMatch(
                        round_id=round_model.id, participant1_id=p1_id, participant2_id=p2_id
                    )
                    session.add(match)
                    matches.append(match)
                    next_round_participants.append(None)
                    pair_idx += 1
                if bye_idx < len(bye_ids):
                    p1_id = bye_ids[bye_idx]
                    match = PlayoffMatch(
                        round_id=round_model.id,
                        participant1_id=p1_id,
                        participant2_id=None,
                        score1=0,
                        score2=0,
                        played=True,
                        winner_id=p1_id,
                    )
                    session.add(match)
                    matches.append(match)
                    next_round_participants.append(p1_id)
                    bye_idx += 1
            current_participants = next_round_participants
            continue
        # Остальные раунды: пары из current_participants.
        # В r > 0 None означает "победитель ещё не определён" (ждёт матч предыдущего раунда),
        # поэтому НЕ протаскиваем известного игрока в следующий раунд — это сделает
        # enter_match_result, когда реальный матч будет сыгран.
        round_size = len(current_participants)
        for i in range(0, round_size, 2):
            p1_id = current_participants[i]
            p2_id = current_participants[i + 1] if i + 1 < round_size else None
            match = PlayoffMatch(
                round_id=round_model.id,
                participant1_id=p1_id,
                participant2_id=p2_id,
            )
            session.add(match)
            matches.append(match)
            next_round_participants.append(None)
        await session.flush()
        # Для следующего раунда снова заполняем current_participants до нужной длины (половина предыдущего)
        next_len = round_size // 2
        while len(next_round_participants) < next_len:
            next_round_participants.append(None)
        current_participants = next_round_participants
    return bracket


COMPRESSED_16_PRELIMINARY_SLOTS = [
    (4, 13, 1, "participant1_id"),
    (5, 12, 1, "participant2_id"),
    (3, 14, 2, "participant1_id"),
    (6, 11, 2, "participant2_id"),
    (7, 10, 3, "participant2_id"),
    (2, 15, 3, "participant1_id"),
    (8, 9, 0, "participant2_id"),
]


def get_standard_seed_slots(bracket_size: int) -> list[int]:
    if bracket_size == 2:
        return [1, 2]

    previous = get_standard_seed_slots(bracket_size // 2)
    slots = []
    for seed in previous:
        slots.extend([seed, bracket_size + 1 - seed])
    return slots


def get_compressed_16_routes(participants_count: int) -> list[tuple[int, str]]:
    return [
        (quarterfinal_index, target_slot)
        for _, high_seed, quarterfinal_index, target_slot in COMPRESSED_16_PRELIMINARY_SLOTS
        if high_seed <= participants_count
    ]


def get_generic_compressed_routes(
    participants_count: int,
    base_size: int,
) -> list[tuple[int, str]]:
    seed_slots = get_standard_seed_slots(base_size * 2)
    routes = []

    for pair_index in range(base_size):
        seed1 = seed_slots[pair_index * 2]
        seed2 = seed_slots[pair_index * 2 + 1]
        if seed1 <= participants_count and seed2 <= participants_count:
            routes.append((
                pair_index // 2,
                "participant1_id" if pair_index % 2 == 0 else "participant2_id",
            ))

    return routes


def get_compressed_routes(
    participants_count: int,
    base_size: int,
) -> list[tuple[int, str]]:
    if base_size == 8:
        return get_compressed_16_routes(participants_count)

    return get_generic_compressed_routes(participants_count, base_size)


def get_seed_meeting_rounds(bracket_size: int) -> dict[tuple[int, int], int]:
    seed_slots = get_standard_seed_slots(bracket_size)
    leaf_by_seed = {
        seed: leaf_index
        for leaf_index, seed in enumerate(seed_slots)
    }
    meeting_rounds = {}

    for seed1 in range(1, bracket_size + 1):
        for seed2 in range(seed1 + 1, bracket_size + 1):
            leaf1 = leaf_by_seed[seed1]
            leaf2 = leaf_by_seed[seed2]
            round_number = 1

            while leaf1 // 2 != leaf2 // 2:
                leaf1 //= 2
                leaf2 //= 2
                round_number += 1

            meeting_rounds[(seed1, seed2)] = round_number

    return meeting_rounds


def get_seed_optimization_bracket_size(participants_count: int) -> int | None:
    if 8 < participants_count < 16:
        return 16
    if 16 < participants_count < 32:
        return 32

    return None


def group_separation_objective(
    entries_by_seed: list[dict],
    meeting_rounds: dict[tuple[int, int], int],
    rounds_count: int,
) -> tuple:
    """
    Lexicographic score: first minimize same-group pairs that can meet in the
    earliest round, then the next round, and so on. Seed movement is only a
    tie-breaker, so group separation wins over cosmetic ordering.
    """
    same_group_meeting_counts = [0] * rounds_count

    for left_seed, left_entry in enumerate(entries_by_seed, start=1):
        right_entries = entries_by_seed[left_seed:]
        for right_seed, right_entry in enumerate(right_entries, start=left_seed + 1):
            if left_entry["group_index"] != right_entry["group_index"]:
                continue

            meeting_round = meeting_rounds[(left_seed, right_seed)]
            same_group_meeting_counts[meeting_round - 1] += 1

    seed_movement_penalty = 0
    top_seed_movement_penalty = 0
    for seed, entry in enumerate(entries_by_seed, start=1):
        ideal_seed = entry["ideal_seed"]
        seed_distance = abs(seed - ideal_seed)
        seed_movement_penalty += seed_distance
        top_seed_movement_penalty += (
            seed_distance * (len(entries_by_seed) - ideal_seed + 1)
        )

    return (
        *same_group_meeting_counts,
        top_seed_movement_penalty,
        seed_movement_penalty,
    )


def optimize_entries_for_group_separation(
    ordered_entries: list[dict],
    bracket_size: int,
) -> list[dict]:
    if len(ordered_entries) < 3:
        return ordered_entries

    entries_by_seed = [
        {
            **entry,
            "ideal_seed": seed,
        }
        for seed, entry in enumerate(ordered_entries, start=1)
    ]
    rounds_count = int(math.log2(bracket_size))
    meeting_rounds = get_seed_meeting_rounds(bracket_size)
    best_objective = group_separation_objective(
        entries_by_seed,
        meeting_rounds,
        rounds_count,
    )

    improved = True
    while improved:
        improved = False
        best_swap = None
        best_swap_entries = entries_by_seed
        best_swap_objective = best_objective

        for left_index in range(len(entries_by_seed)):
            for right_index in range(left_index + 1, len(entries_by_seed)):
                candidate_entries = entries_by_seed[:]
                candidate_entries[left_index], candidate_entries[right_index] = (
                    candidate_entries[right_index],
                    candidate_entries[left_index],
                )
                candidate_objective = group_separation_objective(
                    candidate_entries,
                    meeting_rounds,
                    rounds_count,
                )

                if candidate_objective < best_swap_objective:
                    best_swap = (left_index, right_index)
                    best_swap_entries = candidate_entries
                    best_swap_objective = candidate_objective

        if best_swap is not None:
            entries_by_seed = best_swap_entries
            best_objective = best_swap_objective
            improved = True

    return entries_by_seed


def build_cross_group_seed_order(entries: list[dict]):
    ordered_entries = sorted(
        entries,
        key=lambda entry: (
            entry["place_index"],
            -entry["points_per_match"],
            -entry["score_diff_per_match"],
            -entry["scored_per_match"],
            entry["participant"].id,
        ),
    )

    bracket_size = get_seed_optimization_bracket_size(len(ordered_entries))
    if bracket_size:
        ordered_entries = optimize_entries_for_group_separation(
            ordered_entries,
            bracket_size,
        )

    return [entry["participant"] for entry in ordered_entries]


def build_per_group_cross_group_seed_order(
    group_entries: list[list[dict]],
    count_per_group: int,
):
    selected = [
        entry
        for entries in group_entries
        for entry in entries[:count_per_group]
    ]

    return build_cross_group_seed_order(selected)


async def generate_compressed_16_seeded_bracket(session, participants, bracket_type, stage_id):
    """
    Seed 9-15 participants into a 16-player bracket without showing bye matches.
    The preliminary round reduces the field to eight quarterfinalists.
    """
    if not 8 < len(participants) < 16:
        raise ValueError("generate_compressed_16_seeded_bracket expects 9-15 participants")

    ids = [p.id if hasattr(p, "id") else p for p in participants]
    participants_by_seed = {
        seed: participant_id
        for seed, participant_id in enumerate(ids, start=1)
    }
    bracket = PlayoffBracket(type=bracket_type, stage_id=stage_id)
    session.add(bracket)
    await session.flush()

    def add_match(round_id, participant1_id=None, participant2_id=None):
        session.add(
            PlayoffMatch(
                round_id=round_id,
                participant1_id=participant1_id,
                participant2_id=participant2_id,
            )
        )

    preliminary_sources = set()
    round_model = PlayoffRound(number=1, bracket_id=bracket.id)
    session.add(round_model)
    await session.flush()
    for low_seed, high_seed, quarterfinal_index, target_slot in COMPRESSED_16_PRELIMINARY_SLOTS:
        if high_seed not in participants_by_seed:
            continue

        add_match(
            round_model.id,
            participants_by_seed[low_seed],
            participants_by_seed[high_seed],
        )
        preliminary_sources.add((quarterfinal_index, target_slot))

    round_model = PlayoffRound(number=2, bracket_id=bracket.id)
    session.add(round_model)
    await session.flush()

    def quarterfinal_slot(seed, quarterfinal_index, target_slot):
        if (quarterfinal_index, target_slot) in preliminary_sources:
            return None
        return participants_by_seed.get(seed)

    add_match(round_model.id, participants_by_seed[1], quarterfinal_slot(8, 0, "participant2_id"))
    add_match(
        round_model.id,
        quarterfinal_slot(4, 1, "participant1_id"),
        quarterfinal_slot(5, 1, "participant2_id"),
    )
    add_match(
        round_model.id,
        quarterfinal_slot(3, 2, "participant1_id"),
        quarterfinal_slot(6, 2, "participant2_id"),
    )
    add_match(
        round_model.id,
        quarterfinal_slot(2, 3, "participant1_id"),
        quarterfinal_slot(7, 3, "participant2_id"),
    )

    round_model = PlayoffRound(number=3, bracket_id=bracket.id)
    session.add(round_model)
    await session.flush()
    add_match(round_model.id)
    add_match(round_model.id)

    round_model = PlayoffRound(number=4, bracket_id=bracket.id)
    session.add(round_model)
    await session.flush()
    add_match(round_model.id)

    return bracket


async def generate_compressed_32_seeded_bracket(session, participants, bracket_type, stage_id):
    """
    Seed 17-31 participants into a 32-player bracket without showing bye matches.
    The preliminary round reduces the field to sixteen players.
    """
    if not 16 < len(participants) < 32:
        raise ValueError("generate_compressed_32_seeded_bracket expects 17-31 participants")

    ids = [p.id if hasattr(p, "id") else p for p in participants]
    participants_by_seed = {
        seed: participant_id
        for seed, participant_id in enumerate(ids, start=1)
    }
    bracket = PlayoffBracket(type=bracket_type, stage_id=stage_id)
    session.add(bracket)
    await session.flush()

    seed_slots = get_standard_seed_slots(32)
    round_two_slots = []

    def add_match(round_id, participant1_id=None, participant2_id=None):
        session.add(
            PlayoffMatch(
                round_id=round_id,
                participant1_id=participant1_id,
                participant2_id=participant2_id,
            )
        )

    round_model = PlayoffRound(number=1, bracket_id=bracket.id)
    session.add(round_model)
    await session.flush()
    for pair_index in range(16):
        seed1 = seed_slots[pair_index * 2]
        seed2 = seed_slots[pair_index * 2 + 1]
        participant1_id = participants_by_seed.get(seed1)
        participant2_id = participants_by_seed.get(seed2)

        if participant1_id and participant2_id:
            add_match(round_model.id, participant1_id, participant2_id)
            round_two_slots.append(None)
        else:
            round_two_slots.append(participant1_id or participant2_id)

    round_model = PlayoffRound(number=2, bracket_id=bracket.id)
    session.add(round_model)
    await session.flush()
    for slot_index in range(0, len(round_two_slots), 2):
        add_match(
            round_model.id,
            round_two_slots[slot_index],
            round_two_slots[slot_index + 1],
        )

    match_count = 4
    round_number = 3
    while match_count >= 1:
        round_model = PlayoffRound(number=round_number, bracket_id=bracket.id)
        session.add(round_model)
        await session.flush()
        for _ in range(match_count):
            add_match(round_model.id)
        match_count //= 2
        round_number += 1

    return bracket


FOUR_GROUP_MAIN_SEEDING = [
    (0, 0),  # 1A
    (3, 3),  # 4D
    (1, 1),  # 2B
    (2, 2),  # 3C
    (1, 0),  # 1B
    (2, 3),  # 4C
    (0, 1),  # 2A
    (3, 2),  # 3D
    (2, 0),  # 1C
    (1, 3),  # 4B
    (3, 1),  # 2D
    (0, 2),  # 3A
    (3, 0),  # 1D
    (0, 3),  # 4A
    (2, 1),  # 2C
    (1, 2),  # 3B
]


THREE_GROUP_TWO_QUALIFIER_MAIN_SEEDING = [
    (0, 0),  # 1A -> bye
    (1, 0),  # 1B -> bye
    (1, 1),  # 2B vs 1C
    (2, 0),
    (0, 1),  # 2A vs 2C
    (2, 1),
]


def build_three_group_two_qualifier_main_seeding(group_participants):
    """
    Six-player playoff seeding for three groups with two qualifiers each.
    With the current bracket generator the first two entries receive byes, then
    entries 3-4 and 5-6 play the first round. This layout prevents same-group
    pairings in the first playable round and in the matches after byes.
    """
    if len(group_participants) != 3 or any(len(plist) < 2 for plist in group_participants):
        return None

    return [
        group_participants[group_index][place_index]
        for group_index, place_index in THREE_GROUP_TWO_QUALIFIER_MAIN_SEEDING
    ]


def build_four_group_main_seeding(group_participants):
    """
    Standard 16-player playoff seeding for four groups with four qualifiers each.
    Groups are expected in A/B/C/D order, participants inside each group by place.
    """
    if len(group_participants) != 4 or any(len(plist) < 4 for plist in group_participants):
        return None

    return [
        group_participants[group_index][place_index]
        for group_index, place_index in FOUR_GROUP_MAIN_SEEDING
    ]


def sort_same_place_entries(entries: list[dict]) -> list[dict]:
    return sorted(
        entries,
        key=lambda entry: (
            -entry["points_per_match"],
            -entry["score_diff_per_match"],
            -entry["scored_per_match"],
            -entry["points"],
            entry["participant"].id,
        ),
    )


def build_three_group_433_ten_player_main_seeding(group_entries: list[list[dict]]):
    """
    Global seeding for three groups sized 4/3/3:
    all group winners first, then all second places, all third places, then A4.
    Entries with the same group place are ranked by per-match group stats,
    then seed positions are adjusted to push same-group meetings later.
    """
    if len(group_entries) != 3 or [len(entries) for entries in group_entries] != [4, 3, 3]:
        return None

    seeded_entries = []
    max_places = max(len(entries) for entries in group_entries)
    for place_index in range(max_places):
        same_place_entries = [
            entries[place_index]
            for entries in group_entries
            if place_index < len(entries)
        ]
        seeded_entries.extend(sort_same_place_entries(same_place_entries))

    if len(seeded_entries) != 10:
        return None

    seeded_entries = optimize_entries_for_group_separation(seeded_entries, 16)

    return [entry["participant"] for entry in seeded_entries]


def resolve_main_count_per_group(main_count: int, group_participants: list[list]) -> int:
    """
    The API historically accepts main_count as "qualifiers per group".
    Some clients/users pass 16 for a full four-group playoff; normalize that
    to four qualifiers per group when groups are too small to contain 16 each.
    """
    if (
        len(group_participants) == 4
        and main_count == len(FOUR_GROUP_MAIN_SEEDING)
        and min(len(plist) for plist in group_participants) < main_count
    ):
        return 4

    return main_count


def normalize_main_count_mode(main_count_mode: str) -> str:
    if main_count_mode not in {"per_group", "total"}:
        raise HTTPException(
            status_code=400,
            detail="main_count_mode должен быть 'per_group' или 'total'",
        )

    return main_count_mode


def build_total_main_seeding(group_entries: list[list[dict]], total_count: int):
    """
    Build a playoff from a total number of qualifiers.
    Selection goes place by place across groups: all first places, then the best
    second places, and so on. Cross-group comparisons use per-match stats so a
    4-player group does not automatically beat a 3-player group by raw points.
    """
    selected = []
    max_places = max((len(entries) for entries in group_entries), default=0)

    for place_index in range(max_places):
        same_place_entries = [
            entries[place_index]
            for entries in group_entries
            if place_index < len(entries)
        ]
        same_place_entries = sort_same_place_entries(same_place_entries)

        for entry in same_place_entries:
            selected.append(entry)
            if len(selected) == total_count:
                return seed_selected_entries(selected)

    return seed_selected_entries(selected)


def build_total_main_seed_order(group_entries: list[list[dict]], total_count: int):
    """
    Build the strict global seed order: 1, 2, 3, ...
    Used by compressed 16-player brackets where pairings are derived from seed numbers.
    """
    selected = []
    max_places = max((len(entries) for entries in group_entries), default=0)

    for place_index in range(max_places):
        same_place_entries = [
            entries[place_index]
            for entries in group_entries
            if place_index < len(entries)
        ]
        same_place_entries = sort_same_place_entries(same_place_entries)

        for entry in same_place_entries:
            selected.append(entry)
            if len(selected) == total_count:
                return build_cross_group_seed_order(selected)

    return build_cross_group_seed_order(selected)


def seed_selected_entries(entries: list[dict]):
    if len(entries) < 2:
        return [entry["participant"] for entry in entries]

    ordered = sorted(
        entries,
        key=lambda entry: (
            entry["place_index"],
            -entry["points_per_match"],
            -entry["score_diff_per_match"],
            -entry["scored_per_match"],
            entry["participant"].id,
        ),
    )

    pairs = []
    used = set()
    for left_index, left_entry in enumerate(ordered):
        if left_index in used:
            continue

        partner_index = None
        for right_index in range(len(ordered) - 1, left_index, -1):
            if (
                right_index not in used
                and ordered[right_index]["group_index"] != left_entry["group_index"]
            ):
                partner_index = right_index
                break

        if partner_index is None:
            for right_index in range(len(ordered) - 1, left_index, -1):
                if right_index not in used:
                    partner_index = right_index
                    break

        if partner_index is None:
            pairs.append((left_entry,))
            used.add(left_index)
            continue

        pairs.append((left_entry, ordered[partner_index]))
        used.add(left_index)
        used.add(partner_index)

    seeded = []
    for pair in pairs:
        seeded.extend(entry["participant"] for entry in pair)
    return seeded


def resolve_next_round_slot(prev_matches, next_matches, match_index: int):
    """
    Default playoff propagation is pair-based: matches 0/1 feed next match 0,
    matches 2/3 feed next match 1, and so on.

    Compressed brackets hide bye matches, so preliminary matches may feed
    non-adjacent slots in the next visible round.
    """
    base_size = len(next_matches) * 2
    if len(prev_matches) < base_size and base_size in {8, 16}:
        compressed_route = get_compressed_routes(len(prev_matches) + base_size, base_size)
        if compressed_route and match_index < len(compressed_route):
            return compressed_route[match_index]

    return (
        match_index // 2,
        "participant1_id" if match_index % 2 == 0 else "participant2_id",
    )


@router.post("/create", response_model=PlayoffStageSchema)
async def create_playoff(
    tournament_id: int,
    main_count: int,
    session: SessionDep,
    additional_count: Optional[int] = None,
    main_count_mode: str = "per_group",
):
    main_count_mode = normalize_main_count_mode(main_count_mode)
    # Проверка: если уже есть сетка для турнира — не создавать новую
    existing_stage = await session.execute(
        select(PlayoffStage).where(PlayoffStage.tournament_id == tournament_id)
    )
    existing_stage = existing_stage.scalars().first()
    if existing_stage:
        raise HTTPException(
            status_code=400, detail="Олимпийская сетка для этого турнира уже существует"
        )

    # Получаем все группы турнира
    groups = await get_groups_by_tournament(tournament_id, session)
    if not groups:
        raise HTTPException(status_code=400, detail="No groups found for tournament")
    groups = sorted(groups, key=lambda group: group.number)
    # Собираем участников по результатам групп
    group_participants = []
    group_entries = []
    for group_index, group in enumerate(groups):
        participants = await get_participants_by_group(group.id, session)
        # Собираем статистику по каждому участнику
        stats = []
        for gp in participants:
            p = gp.participant
            # Матчи участника в этой группе
            matches = [
                m
                for m in p.matches_as_p1 + p.matches_as_p2
                if getattr(m, "group_id", None) == group.id and m.played
            ]
            points = 0
            scored = 0
            conceded = 0
            for m in matches:
                if m.participant1_id == p.id:
                    scored += m.score1 or 0
                    conceded += m.score2 or 0
                    if m.score1 is not None and m.score2 is not None:
                        if m.score1 > m.score2:
                            points += 3
                        elif m.score1 == m.score2:
                            points += 1
                elif m.participant2_id == p.id:
                    scored += m.score2 or 0
                    conceded += m.score1 or 0
                    if m.score1 is not None and m.score2 is not None:
                        if m.score2 > m.score1:
                            points += 3
                        elif m.score1 == m.score2:
                            points += 1
            scoreDiff = scored - conceded
            matches_count = len(matches)
            stats.append({
                "participant": p,
                "points": points,
                "scoreDiff": scoreDiff,
                "scored": scored,
                "id": p.id,
                "matches_count": matches_count,
            })
        # Сортировка: очки → разница → забитые → id
        sorted_stats = sorted(
            stats, key=lambda x: (-x["points"], -x["scoreDiff"], -x["scored"], x["id"])
        )
        group_entries.append([
            {
                "participant": entry["participant"],
                "points": entry["points"],
                "scoreDiff": entry["scoreDiff"],
                "scored": entry["scored"],
                "matches_count": entry["matches_count"],
                "points_per_match": (
                    entry["points"] / entry["matches_count"] if entry["matches_count"] else 0
                ),
                "score_diff_per_match": (
                    entry["scoreDiff"] / entry["matches_count"] if entry["matches_count"] else 0
                ),
                "scored_per_match": (
                    entry["scored"] / entry["matches_count"] if entry["matches_count"] else 0
                ),
                "group_index": group_index,
                "place_index": place_index,
            }
            for place_index, entry in enumerate(sorted_stats)
        ])
        group_participants.append([x["participant"] for x in sorted_stats])
    # Формируем main и additional с чередованием из разных групп
    main_participants = []
    additional_participants = []
    if main_count:
        if main_count_mode == "total":
            total_participants = sum(len(plist) for plist in group_participants)
            if main_count > total_participants:
                raise HTTPException(
                    status_code=400,
                    detail="main_count превышает общее число участников в группах",
                )
            if additional_count:
                for group, plist in zip(groups, group_participants):
                    if additional_count > len(plist):
                        raise HTTPException(
                            status_code=400,
                            detail=f"additional_count превышает число участников в группе (group_id={group.id})",
                        )
            ten_player_seeding = (
                build_three_group_433_ten_player_main_seeding(group_entries)
                if main_count == 10
                else None
            )
            if 8 < main_count < 32:
                main_participants = ten_player_seeding or build_total_main_seed_order(
                    group_entries,
                    main_count,
                )
            else:
                main_participants = build_total_main_seeding(
                    group_entries,
                    main_count,
                )
        else:
            main_count_per_group = resolve_main_count_per_group(main_count, group_participants)
            for group, plist in zip(groups, group_participants):
                main_selected_count = min(main_count_per_group, len(plist))
                if main_selected_count + (additional_count or 0) > len(plist):
                    raise HTTPException(
                        status_code=400,
                        detail=f"main_count + additional_count превышает число участников в группе (group_id={group.id})",
                    )

            n_groups = len(group_participants)
            standard_four_group_seeding = (
                build_four_group_main_seeding(group_participants)
                if n_groups == 4 and main_count_per_group == 4
                else None
            )
            three_group_two_qualifier_seeding = (
                build_three_group_two_qualifier_main_seeding(group_participants)
                if n_groups == 3 and main_count_per_group == 2
                else None
            )
            three_group_433_ten_player_seeding = (
                build_three_group_433_ten_player_main_seeding(group_entries)
                if n_groups == 3
                and main_count_per_group >= 4
                and [len(plist) for plist in group_participants] == [4, 3, 3]
                else None
            )
            if standard_four_group_seeding:
                main_participants = standard_four_group_seeding
            elif three_group_two_qualifier_seeding:
                main_participants = three_group_two_qualifier_seeding
            elif three_group_433_ten_player_seeding:
                main_participants = three_group_433_ten_player_seeding
            elif n_groups == 2:
                group1, group2 = group_participants
                total_players = min(main_count_per_group, len(group1)) + min(
                    main_count_per_group, len(group2)
                )
                pow2 = 1 << (total_players - 1).bit_length() if total_players > 0 else 1
                has_byes = pow2 > total_players

                if has_byes:
                    # Будут байи: используем порядок по местам (1A, 1B, 2A, 2B, ...).
                    # Тогда generate_bracket даст байи реальным топ-сидам (1A, 1B),
                    # а одинаковые места из разных групп встретятся в 1/4 финала.
                    for i in range(main_count_per_group):
                        if i < len(group1):
                            main_participants.append(group1[i])
                        if i < len(group2):
                            main_participants.append(group2[i])
                else:
                    # Без байев: кросс-групповая разводка (1A vs 2B, 2A vs 1B, ...),
                    # чтобы 1-е места не встречались в 1-м раунде.
                    pairs = []
                    i = 0
                    while i + 1 < main_count_per_group:
                        pairs.append((i, i + 1))
                        pairs.append((i + 1, i))
                        i += 2
                    for idx_a, idx_b in pairs:
                        if idx_a < len(group1) and idx_b < len(group2):
                            main_participants.append(group1[idx_a])
                            main_participants.append(group2[idx_b])
                    # Защита от нечётного main_count_per_group — забирать
                    # оставшиеся места из обеих групп, иначе они теряются
                    if i < main_count_per_group:
                        if i < len(group1):
                            main_participants.append(group1[i])
                        if i < len(group2):
                            main_participants.append(group2[i])
            else:
                main_participants = build_per_group_cross_group_seed_order(
                    group_entries,
                    main_count_per_group,
                )
    if additional_count:
        # Для additional_participants — как раньше, с конца каждой группы
        for plist in group_participants:
            additional_participants.extend(plist[-additional_count:])
    stage = PlayoffStage(tournament_id=tournament_id)
    session.add(stage)
    await session.flush()
    stage_id = stage.id  # Extract id while session is open
    if main_participants:
        if 8 < len(main_participants) < 16:
            await generate_compressed_16_seeded_bracket(
                session,
                main_participants,
                BracketType.MAIN,
                stage_id,
            )
        elif 16 < len(main_participants) < 32:
            await generate_compressed_32_seeded_bracket(
                session,
                main_participants,
                BracketType.MAIN,
                stage_id,
            )
        else:
            await generate_bracket(session, main_participants, BracketType.MAIN, stage_id)
    if additional_participants:
        await generate_bracket(session, additional_participants, BracketType.ADDITIONAL, stage_id)
    await session.commit()
    # Формируем PlayoffStageSchema для ответа
    # Re-query stage_id and use it directly, do not access ORM object after session
    brackets = await session.execute(
        select(PlayoffBracket).where(PlayoffBracket.stage_id == stage_id)
    )
    brackets = brackets.scalars().all()
    bracket_schemas = []
    for bracket in brackets:
        rounds = await session.execute(
            select(PlayoffRound)
            .where(PlayoffRound.bracket_id == bracket.id)
            .order_by(PlayoffRound.number)
        )
        rounds = rounds.scalars().all()
        bracket_match_counts = []
        for round_obj in rounds:
            matches_count = await session.execute(
                select(PlayoffMatch).where(PlayoffMatch.round_id == round_obj.id)
            )
            bracket_match_counts.append(len(matches_count.scalars().all()))
        round_schemas = []
        for round_obj in rounds:
            matches = await session.execute(
                select(PlayoffMatch)
                .where(PlayoffMatch.round_id == round_obj.id)
                .order_by(PlayoffMatch.id)
            )
            matches = matches.scalars().all()
            match_schemas = [
                PlayoffMatchSchema(
                    match_id=m.id,
                    participant1_id=m.participant1_id,
                    participant2_id=m.participant2_id,
                    score1=m.score1,
                    score2=m.score2,
                    winner_id=m.winner_id,
                    played=m.played,
                    order=idx,
                )
                for idx, m in enumerate(matches)
            ]
            # Количество участников в начале этого раунда:
            # Для первого раунда — это сумма участников, далее — предыдущий раунд победители
            if round_obj.number == 1:
                # Первый раунд: считаем всех участников (включая byes)
                num_participants = sum(
                    1
                    for m in match_schemas
                    for pid in [m.participant1_id, m.participant2_id]
                    if pid is not None
                )
            else:
                # Для остальных — просто len(match_schemas) * 2, но если есть byes, их меньше
                num_participants = sum(
                    1
                    for m in match_schemas
                    for pid in [m.participant1_id, m.participant2_id]
                    if pid is not None
                )
            round_schemas.append(
                PlayoffRoundSchema(
                    round_id=round_obj.id,
                    number=round_obj.number,
                    name=get_playoff_round_name(
                        round_obj.number,
                        len(match_schemas),
                        bracket_match_counts,
                    ),
                    matches=match_schemas,
                )
            )
        bracket_schemas.append(
            PlayoffBracketSchema(
                bracket_id=bracket.id,
                type=bracket.type,
                rounds=round_schemas,
            )
        )
    return PlayoffStageSchema(stage_id=stage_id, brackets=bracket_schemas)


# 2. Enter match results and auto-advance
@router.post("/match/{match_id}/result")
async def enter_match_result(
    match_id: int,
    result: MatchResultInput,
    session: SessionDep,
):
    match = await session.get(PlayoffMatch, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    match.score1 = result.score1
    match.score2 = result.score2
    match.played = True
    # Determine winner
    if result.score1 > result.score2:
        match.winner_id = match.participant1_id
    elif result.score2 > result.score1:
        match.winner_id = match.participant2_id
    else:
        match.winner_id = None  # Draw or error
    round_id = match.round_id
    winner_id = match.winner_id
    await session.commit()

    # Auto-advance winner to next round
    round_obj = await session.get(PlayoffRound, round_id)
    bracket = await session.get(PlayoffBracket, round_obj.bracket_id)
    next_round_number = round_obj.number + 1
    next_round = await session.execute(
        select(PlayoffRound).where(
            PlayoffRound.bracket_id == bracket.id, PlayoffRound.number == next_round_number
        )
    )
    next_round = next_round.scalars().first()
    if next_round and winner_id:
        next_matches = await session.execute(
            select(PlayoffMatch)
            .where(PlayoffMatch.round_id == next_round.id)
            .order_by(PlayoffMatch.id)
        )
        next_matches = next_matches.scalars().all()
        prev_matches = await session.execute(
            select(PlayoffMatch).where(PlayoffMatch.round_id == round_id).order_by(PlayoffMatch.id)
        )
        prev_matches = prev_matches.scalars().all()
        match_index = None
        for idx, m in enumerate(prev_matches):
            if m.id == match.id:
                match_index = idx
                break
        if match_index is not None:
            target_match_idx, target_slot = resolve_next_round_slot(
                prev_matches,
                next_matches,
                match_index,
            )
            if target_match_idx < len(next_matches):
                nm = next_matches[target_match_idx]
                setattr(nm, target_slot, winner_id)
                session.add(nm)
                await session.commit()

    # === НАЧИСЛЕНИЕ ОЧКОВ ПОСЛЕ ФИНАЛА ===
    # Если это финал (нет следующего раунда)
    if not next_round:
        print("POINTS BLOCK REACHED")
        from backend.app.core.config import tournament_categories_map

        stage_id = bracket.stage_id
        print(f"bracket.stage_id={stage_id}")
        playoff_stage = await session.get(PlayoffStage, stage_id)
        tournament_id = playoff_stage.tournament_id
        print(f"tournament_id={tournament_id}")
        tournament_obj = await session.get(Tournament, tournament_id)
        category_id = tournament_obj.category_id
        print(f"category_id={category_id}")
        category_obj = await session.get(Category, category_id)
        category_name = category_obj.name
        print(f"category_name={category_name}")
        points_map = tournament_categories_map.get(category_name)
        print(f"points_map={points_map}")
        if points_map:
            brackets_result = await session.execute(
                select(PlayoffBracket).where(PlayoffBracket.stage_id == stage_id)
            )
            brackets = brackets_result.scalars().all()
            bracket_id_type = [(b.id, b.type) for b in brackets]
            for bracket_id, bracket_type in bracket_id_type:
                rounds_result = await session.execute(
                    select(PlayoffRound)
                    .where(PlayoffRound.bracket_id == bracket_id)
                    .order_by(PlayoffRound.number)
                )
                rounds = rounds_result.scalars().all()
                if not rounds:
                    continue
                final_round = rounds[-1]
                matches_result = await session.execute(
                    select(PlayoffMatch).where(PlayoffMatch.round_id == final_round.id)
                )
                matches = matches_result.scalars().all()
                # Собираем всех участников по местам: победитель, финалист, полуфиналисты и т.д.
                places = []
                # 1. Победитель и финалист(ы)
                for m in matches:
                    if m.winner_id:
                        places.append(m.winner_id)
                    if m.participant1_id and m.participant1_id != m.winner_id:
                        places.append(m.participant1_id)
                    if m.participant2_id and m.participant2_id != m.winner_id:
                        places.append(m.participant2_id)
                # 2. Добавляем проигравших в предыдущем раунде (например, полуфиналистов, если нет матча за 3 место)
                prev_rounds = rounds[:-1]
                for prev_round in reversed(prev_rounds):
                    prev_matches_result = await session.execute(
                        select(PlayoffMatch).where(PlayoffMatch.round_id == prev_round.id)
                    )
                    prev_matches = prev_matches_result.scalars().all()
                    for m in prev_matches:
                        # Если участник не попал в places, значит он проиграл в этом раунде и не прошёл дальше
                        if m.participant1_id and m.participant1_id not in places:
                            places.append(m.participant1_id)
                        if m.participant2_id and m.participant2_id not in places:
                            places.append(m.participant2_id)
                # 3. Убираем дубликаты, сохраняем порядок
                places = list(dict.fromkeys(places))
                for idx, participant_id in enumerate(places):
                    participant = await session.get(TournamentParticipant, participant_id)
                    user = await session.get(User, participant.user_id)
                    points = 0
                    multiplier = 2 if getattr(tournament_obj, "is_grand", False) else 1
                    if bracket_type == "main":
                        for rng, pts in points_map.items():
                            if isinstance(rng, range) and idx + 1 in rng:
                                points = pts * multiplier
                                break
                        print(
                            f"MAIN: место {idx + 1}, user_id={user.id}, participant_id={participant_id}, points={points}"
                        )
                    elif bracket_type == "additional":
                        points = points_map.get("additional", 0)
                        print(
                            f"ADDITIONAL: user_id={user.id}, participant_id={participant_id}, points={points}"
                        )
                    if points:
                        user.score = (user.score or 0) + points
                        session.add(user)
                await session.commit()

    return {
        "status": "Result entered",
        "winner_id": winner_id if winner_id else None,
    }


# 3. Get playoff bracket with stages/rounds/matches
@router.get("/stage/{stage_id}")
async def get_playoff_stage(
    stage_id: int,
    session: SessionDep,
):
    stage = await session.get(PlayoffStage, stage_id)
    if not stage:
        raise HTTPException(status_code=404, detail="Playoff stage not found")
    brackets = await session.execute(
        select(PlayoffBracket).where(PlayoffBracket.stage_id == stage_id)
    )
    brackets = brackets.scalars().all()
    bracket_schemas = []
    for bracket in brackets:
        rounds = await session.execute(
            select(PlayoffRound)
            .where(PlayoffRound.bracket_id == bracket.id)
            .order_by(PlayoffRound.number)
        )
        rounds = rounds.scalars().all()
        bracket_match_counts = []
        for round_obj in rounds:
            matches_count = await session.execute(
                select(PlayoffMatch).where(PlayoffMatch.round_id == round_obj.id)
            )
            bracket_match_counts.append(len(matches_count.scalars().all()))
        round_schemas = []
        for round_obj in rounds:
            matches = await session.execute(
                select(PlayoffMatch)
                .where(PlayoffMatch.round_id == round_obj.id)
                .order_by(PlayoffMatch.id)
            )
            matches = matches.scalars().all()
            match_schemas = [
                PlayoffMatchSchema(
                    match_id=m.id,
                    participant1_id=m.participant1_id,
                    participant2_id=m.participant2_id,
                    score1=m.score1,
                    score2=m.score2,
                    winner_id=m.winner_id,
                    played=m.played,
                    order=idx,
                )
                for idx, m in enumerate(matches)
            ]
            round_schemas.append(
                PlayoffRoundSchema(
                    round_id=round_obj.id,
                    number=round_obj.number,
                    name=get_playoff_round_name(
                        round_obj.number,
                        len(match_schemas),
                        bracket_match_counts,
                    ),
                    matches=match_schemas,
                )
            )
        bracket_schemas.append(
            PlayoffBracketSchema(
                bracket_id=bracket.id,
                type=bracket.type,
                rounds=round_schemas,
            )
        )
    return PlayoffStageSchema(stage_id=stage.id, brackets=bracket_schemas)


@router.get("/tournament/{tournament_id}", response_model=PlayoffStageSchema)
async def get_playoff_stage_by_tournament(
    tournament_id: int,
    session: SessionDep,
):
    stage = await session.execute(
        select(PlayoffStage).where(PlayoffStage.tournament_id == tournament_id)
    )
    stage = stage.scalars().first()
    if not stage:
        raise HTTPException(status_code=404, detail="Playoff stage not found")
    brackets = await session.execute(
        select(PlayoffBracket).where(PlayoffBracket.stage_id == stage.id)
    )
    brackets = brackets.scalars().all()
    bracket_schemas = []
    for bracket in brackets:
        rounds = await session.execute(
            select(PlayoffRound)
            .where(PlayoffRound.bracket_id == bracket.id)
            .order_by(PlayoffRound.number)
        )
        rounds = rounds.scalars().all()
        bracket_match_counts = []
        for round_obj in rounds:
            matches_count = await session.execute(
                select(PlayoffMatch).where(PlayoffMatch.round_id == round_obj.id)
            )
            bracket_match_counts.append(len(matches_count.scalars().all()))
        round_schemas = []
        for round_obj in rounds:
            matches = await session.execute(
                select(PlayoffMatch)
                .where(PlayoffMatch.round_id == round_obj.id)
                .order_by(PlayoffMatch.id)
            )
            matches = matches.scalars().all()
            match_schemas = [
                PlayoffMatchSchema(
                    match_id=m.id,
                    participant1_id=m.participant1_id,
                    participant2_id=m.participant2_id,
                    score1=m.score1,
                    score2=m.score2,
                    winner_id=m.winner_id,
                    played=m.played,
                    order=idx,
                )
                for idx, m in enumerate(matches)
            ]
            round_schemas.append(
                PlayoffRoundSchema(
                    round_id=round_obj.id,
                    number=round_obj.number,
                    name=get_playoff_round_name(
                        round_obj.number,
                        len(match_schemas),
                        bracket_match_counts,
                    ),
                    matches=match_schemas,
                )
            )
        bracket_schemas.append(
            PlayoffBracketSchema(
                bracket_id=bracket.id,
                type=bracket.type,
                rounds=round_schemas,
            )
        )
    return PlayoffStageSchema(stage_id=stage.id, brackets=bracket_schemas)


from fastapi import Depends
from backend.app.api.deps import get_current_user


@router.delete("/stage/{stage_id}")
async def delete_playoff_stage(
    stage_id: int,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    stage = await session.get(PlayoffStage, stage_id)
    if not stage:
        raise HTTPException(status_code=404, detail="Playoff stage not found")
    # Получаем турнир
    tournament = await session.get(Tournament, stage.tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    # Проверка: только организатор турнира или админ
    if not (getattr(current_user, "admin", False) or getattr(current_user, "organizer", False)):
        raise HTTPException(
            status_code=403, detail="Only organizer or admin can delete playoff grid"
        )
    # Проверка: финал не сыгран.
    # Если сетки/раунда/матча ещё нет (например, создан пустой stage без участников) —
    # удаление разрешено, удалять-то нечего.
    bracket = await session.execute(
        select(PlayoffBracket).where(PlayoffBracket.stage_id == stage_id)
    )
    bracket = bracket.scalars().first()
    if bracket:
        final_round = await session.execute(
            select(PlayoffRound)
            .where(PlayoffRound.bracket_id == bracket.id)
            .order_by(PlayoffRound.number.desc())
        )
        final_round = final_round.scalars().first()
        if final_round:
            final_match = await session.execute(
                select(PlayoffMatch).where(PlayoffMatch.round_id == final_round.id)
            )
            final_match = final_match.scalars().first()
            if final_match and final_match.played:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot delete playoff grid: final already played",
                )
    await session.delete(stage)
    await session.commit()
    return {"status": "Playoff stage deleted"}
