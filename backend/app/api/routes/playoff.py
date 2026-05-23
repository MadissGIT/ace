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
        # Остальные раунды: стандартно, пары из current_participants
        round_size = len(current_participants)
        for i in range(0, round_size, 2):
            p1_id = current_participants[i]
            p2_id = current_participants[i + 1] if i + 1 < round_size else None
            # Не пропускаем даже если оба None — чтобы ячейка была пустой
            match = PlayoffMatch(
                round_id=round_model.id,
                participant1_id=p1_id,
                participant2_id=p2_id,
            )
            session.add(match)
            matches.append(match)
            if p1_id is not None and p2_id is None:
                next_round_participants.append(p1_id)
            elif p2_id is not None and p1_id is None:
                next_round_participants.append(p2_id)
            elif p1_id is not None and p2_id is not None:
                next_round_participants.append(None)
            else:
                next_round_participants.append(None)
        await session.flush()
        # Для следующего раунда снова заполняем current_participants до нужной длины (половина предыдущего)
        next_len = round_size // 2
        while len(next_round_participants) < next_len:
            next_round_participants.append(None)
        current_participants = next_round_participants
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


@router.post("/create", response_model=PlayoffStageSchema)
async def create_playoff(
    tournament_id: int,
    main_count: int,
    session: SessionDep,
    additional_count: Optional[int] = None,
):
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
    for group in groups:
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
            stats.append({
                "participant": p,
                "points": points,
                "scoreDiff": scoreDiff,
                "scored": scored,
                "id": p.id,
            })
        # Сортировка: очки → разница → забитые → id
        sorted_stats = sorted(
            stats, key=lambda x: (-x["points"], -x["scoreDiff"], -x["scored"], x["id"])
        )
        group_participants.append([x["participant"] for x in sorted_stats])
    # Формируем main и additional с чередованием из разных групп
    main_participants = []
    additional_participants = []
    if main_count:
        main_count_per_group = resolve_main_count_per_group(main_count, group_participants)
        for group, plist in zip(groups, group_participants):
            if main_count_per_group + (additional_count or 0) > len(plist):
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
        if standard_four_group_seeding:
            main_participants = standard_four_group_seeding
        elif n_groups == 2:
            group1, group2 = group_participants
            pairs = []
            for i in range(0, main_count_per_group, 2):
                # 1A-2B, 2A-1B, 3A-4B, 4A-3B, ...
                if i + 1 < main_count_per_group:
                    # Четная пара: iA-(i+1)B
                    pairs.append((i, i + 1))
                    # Следом нечетная: (i+1)A-iB
                    pairs.append((i + 1, i))
            for idx_a, idx_b in pairs:
                if idx_a < len(group1) and idx_b < len(group2):
                    main_participants.append(group1[idx_a])
                    main_participants.append(group2[idx_b])
        else:
            # Для большего числа групп: поочередно по местам
            for i in range(main_count_per_group):
                for plist in group_participants:
                    if i < len(plist):
                        main_participants.append(plist[i])
    if additional_count:
        # Для additional_participants — как раньше, с конца каждой группы
        for plist in group_participants:
            additional_participants.extend(plist[-additional_count:])
    stage = PlayoffStage(tournament_id=tournament_id)
    session.add(stage)
    await session.flush()
    stage_id = stage.id  # Extract id while session is open
    if main_participants:
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
                    name=get_round_name(num_participants),
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
            target_match_idx = match_index // 2
            if target_match_idx < len(next_matches):
                nm = next_matches[target_match_idx]
                if match_index % 2 == 0:
                    nm.participant1_id = winner_id
                else:
                    nm.participant2_id = winner_id
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
                    name=get_round_name(len(match_schemas) * 2),
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
                    name=get_round_name(len(match_schemas) * 2),
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