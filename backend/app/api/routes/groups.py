from fastapi import APIRouter, Depends, HTTPException
from typing import Any, List

from common.db.models.group import (
    GroupMatch,
    GroupStage,
    GroupMatchUpdate,
    GroupStageCreate,
    GroupStagePublic,
    GroupMatchCreate,
    GroupMatchPublic,
    GroupParticipantCreate,
    GroupParticipantPublic,
    GroupPreviewRequest,
    GroupParticipant,
)
from common.db.models.tournament import Tournament
from common.db.models.participant import TournamentParticipant

from backend.app.crud import group_stage as crud_group_stage
from backend.app.crud import group_participant as crud_group_participant
from backend.app.crud import group_match as crud_group_match
from backend.app.crud import tournament as crud_tournament

from backend.app.api.deps import (
    CurrentUser,
    SessionDep,
    get_current_organizer_or_admin,
)


router = APIRouter()


RECOMMENDED_GROUP_CAPACITIES: dict[int, list[int]] = {
    6: [3, 3],
    7: [4, 3],
    8: [4, 4],
    9: [3, 3, 3],
    10: [4, 3, 3],
    11: [4, 4, 3],
    12: [4, 4, 4],
    13: [4, 3, 3, 3],
    14: [4, 4, 3, 3],
    15: [4, 4, 4, 3],
    16: [4, 4, 4, 4],
    17: [4, 4, 3, 3, 3],
    18: [3, 3, 3, 3, 3, 3],
}

# ---------------------
# GroupStage endscore
# ---------------------


@router.get(
    "/tournament/{tournament_id}",
    response_model=List[GroupStagePublic],
)
async def read_groups(
    tournament_id: int,
    session: SessionDep,
):
    tournament = await session.get(Tournament, tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    groups = await crud_group_stage.get_groups_by_tournament(tournament_id, session)
    return [GroupStagePublic(**g.model_dump()) for g in groups]


@router.delete(
    "/tournament/{tournament_id}",
    dependencies=[Depends(get_current_organizer_or_admin)],
)
async def delete_groups(
    tournament_id: int,
    session: SessionDep,
):
    tournament = await session.get(Tournament, tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    await crud_group_stage.delete_groups_by_tournament(tournament_id, session)
    return {"message": "Groups deleted successfully"}


@router.post(
    "/tournament/{tournament_id}",
    response_model=List[GroupStagePublic],
    dependencies=[Depends(get_current_organizer_or_admin)],
)
async def create_groups(
    tournament_id: int,
    groups_in: List[GroupStageCreate],
    session: SessionDep,
    current_user: CurrentUser,
):
    tournament = await session.get(Tournament, tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    created = []
    for gdata in groups_in:
        group = await crud_group_stage.create_group(gdata, session, tournament_id)
        created.append(group)
    return [GroupStagePublic(**g.model_dump()) for g in created]


@router.delete(
    "/{group_id}",
    dependencies=[Depends(get_current_organizer_or_admin)],
)
async def delete_group(
    group_id: int,
    session: SessionDep,
):
    group = await session.get(GroupStage, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    await crud_group_stage.delete_group(group, session)
    return {"message": "Group deleted successfully"}


@router.get(
    "/{group_id}/participants",
    response_model=List[GroupParticipantPublic],
)
async def read_group_participants(
    group_id: int,
    session: SessionDep,
):
    participants = await crud_group_participant.get_participants_by_group(group_id, session)
    return [GroupParticipantPublic(**p.model_dump()) for p in participants]


@router.post(
    "/{group_id}/participants",
    response_model=GroupParticipantPublic,
    dependencies=[Depends(get_current_organizer_or_admin)]
)
async def create_group_participant(
    group_id: int,
    participant_in: GroupParticipantCreate,
    session: SessionDep,
    current_user: CurrentUser,
):
    participant_in.group_id = group_id
    participant = await crud_group_participant.add_participant(participant_in, session)
    return GroupParticipantPublic(**participant.model_dump())


@router.delete(
    "/participants/{participant_id}",
    dependencies=[Depends(get_current_organizer_or_admin)]
)
async def delete_group_participant(
    participant_id: int,
    session: SessionDep,
):
    participant = await session.get(GroupParticipant, participant_id)
    if not participant:
        raise HTTPException(
            status_code=404, detail="Group participant not found")
    await session.delete(participant)
    await session.commit()
    return {"message": "Group participant deleted successfully"}


# ---------------------
# GroupMatch endscore
# ---------------------

@router.get(
    "/{group_id}/matches",
    response_model=List[GroupMatchPublic],
)
async def read_group_matches(
    group_id: int,
    session: SessionDep,
):
    matches = await crud_group_match.get_matches_by_group(group_id, session)
    return [GroupMatchPublic(**m.model_dump()) for m in matches]


@router.post(
    "/{group_id}/matches",
    response_model=GroupMatchPublic,
    dependencies=[Depends(get_current_organizer_or_admin)]
)
async def create_group_match(
    group_id: int,
    match_in: GroupMatchCreate,
    session: SessionDep,
    current_user: CurrentUser,
):
    match_in.group_id = group_id
    match = await crud_group_match.create_match(match_in, session)
    return GroupMatchPublic(**match.model_dump())


@router.put(
    "/matches/{match_id}",
    response_model=GroupMatchPublic,
    dependencies=[Depends(get_current_organizer_or_admin)]
)
async def update_group_match(
    match_id: int,
    match_in: GroupMatchUpdate,
    session: SessionDep,
    current_user: CurrentUser,
):
    match = await session.get(GroupMatch, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Group match not found")

    updated_match = await crud_group_match.update_match(
        session=session,
        match=match,
        match_in=match_in,
    )
    return GroupMatchPublic(**updated_match.model_dump())


def generate_groups_with_unassigned(
    participants: List[TournamentParticipant],
    group_size: int,
    tournament_id: int,
) -> dict[str, Any]:
    """
    Формирование групп по принципу "змеиного" распределения:
    - Сортировка по убыванию очков
    - Деление на 4 равные подгруппы (по силе)
    - Каждая итоговая группа — по одному игроку из каждой подгруппы
    - Остаток → unassigned
    """
    def participant_score(p: TournamentParticipant) -> int:
        user_score = getattr(p.user, "score", 0)
        partner_score = getattr(p.partner, "score", 0) if p.partner else 0
        return user_score + partner_score

    # 1. Сортируем по убыванию очков
    participants_sorted = sorted(participants, key=participant_score, reverse=True)
    total = len(participants_sorted)

    if total == 0:
        return {"groups": [], "unassigned": []}

    group_capacities = (
        RECOMMENDED_GROUP_CAPACITIES.get(total)
        if group_size == 4
        else None
    )
    if group_capacities:
        grouped_participants: list[list[TournamentParticipant]] = [
            [] for _ in group_capacities
        ]
        participant_index = 0
        row_index = 0

        while participant_index < total:
            group_order = list(range(len(group_capacities)))
            if row_index % 2 == 1:
                group_order.reverse()

            added_in_row = False
            for group_index in group_order:
                if participant_index >= total:
                    break
                if len(grouped_participants[group_index]) >= group_capacities[group_index]:
                    continue

                grouped_participants[group_index].append(participants_sorted[participant_index])
                participant_index += 1
                added_in_row = True

            if not added_in_row:
                break
            row_index += 1

        groups = [
            GroupStageCreate(
                name=f"Group {index + 1}",
                number=index + 1,
                tournament_id=tournament_id,
                participants_ids=[p.id for p in group_participants],
            )
            for index, group_participants in enumerate(grouped_participants)
        ]

        return {
            "groups": groups,
            "unassigned": [],
        }

    # 2. Определяем размер подгруппы (чанки по group_size)
    # group_size = 4 → 4 подгруппы по 4 игрока
    subgroup_size = total // group_size
    remainder = total % group_size

    # Если не хватает на полные подгруппы — всё в unassigned
    if subgroup_size == 0:
        return {
            "groups": [],
            "unassigned": [p.id for p in participants_sorted]
        }

    # 3. Делим на подгруппы (по силе)
    subgroups = []
    index = 0
    for _ in range(group_size):
        subgroup = participants_sorted[index:index + subgroup_size]
        subgroups.append(subgroup)
        index += subgroup_size

    # 4. Формируем итоговые группы: по одному из каждой подгруппы
    groups: List[GroupStageCreate] = []
    for i in range(subgroup_size):
        group_participants = []
        for subgroup in subgroups:
            if i < len(subgroup):
                group_participants.append(subgroup[i])
        
        groups.append(
            GroupStageCreate(
                name=f"Group {i + 1}",
                number=i + 1,
                tournament_id=tournament_id,
                participants_ids=[p.id for p in group_participants]
            )
        )

    # 5. Остаток (последние remainder игроков) → unassigned
    unassigned = []
    if remainder > 0:
        # Берём остаток из конца отсортированного списка
        unassigned = [p.id for p in participants_sorted[-remainder:]]

    return {
        "groups": groups,
        "unassigned": unassigned
    }


@router.post(
    "/tournaments/{tournament_id}/preview",
    dependencies=[Depends(get_current_organizer_or_admin)],
)
async def preview_groups(
    group: GroupPreviewRequest,
    session: SessionDep,
    tournament_id: int,
):
    # Получаем участников турнира
    _, participants = await crud_tournament.get_participants_by_tournament_id(
        session=session,
        tournament_id=tournament_id,
        skip=0,
        limit=100
    )
    if not participants:
        raise HTTPException(status_code=404, detail="No participants found")

    result = generate_groups_with_unassigned(
        participants=participants,
        group_size=group.group_size,
        tournament_id=tournament_id,
    )
    return result


@router.post(
    "/tournaments/{tournament_id}/confirm",
    dependencies=[Depends(get_current_organizer_or_admin)],
)
async def confirm_groups(
    tournament_id: int,
    groups_in: List[GroupStageCreate],
    session: SessionDep,
) -> List[GroupStagePublic]:
    # Проверка турнира
    tournament = await session.get(Tournament, tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    created_groups = []
    for gdata in groups_in:
        group = await crud_group_stage.create_group(gdata, session, tournament_id)

        for participant_id in gdata.participants_ids:
            gp_in = GroupParticipantCreate(
                group_id=group.id,
                participant_id=participant_id,
            )
            await crud_group_participant.add_participant(gp_in, session)

        # Генерация матчей round-robin
        for i in range(len(gdata.participants_ids)):
            for j in range(i + 1, len(gdata.participants_ids)):
                match_in = GroupMatchCreate(
                    group_id=group.id,
                    participant1_id=gdata.participants_ids[i],
                    participant2_id=gdata.participants_ids[j],
                )
                await crud_group_match.create_match(match_in, session)

        created_groups.append(group)

    return [GroupStagePublic(**g.model_dump()) for g in created_groups]
