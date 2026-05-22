import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .tournament import Tournament


class PlayoffStageBase(SQLModel):
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)


class PlayoffStage(PlayoffStageBase, table=True):
    __tablename__ = "playoff_stages"

    id: int = Field(primary_key=True)
    tournament_id: int = Field(
        foreign_key="tournaments.id",
        ondelete="CASCADE",
    )

    tournament: "Tournament" = Relationship(back_populates="playoff_stages")
    brackets: list["PlayoffBracket"] = Relationship(
        back_populates="stage",
        passive_deletes="all",
    )


class BracketType(str, Enum):
    MAIN = "main"
    ADDITIONAL = "additional"


class PlayoffBracketBase(SQLModel):
    type: BracketType


class PlayoffBracket(PlayoffBracketBase, table=True):
    __tablename__ = "playoff_brackets"

    id: int = Field(primary_key=True)
    stage_id: int = Field(
        foreign_key="playoff_stages.id",
        ondelete="CASCADE",
    )

    stage: PlayoffStage = Relationship(back_populates="brackets")
    rounds: list["PlayoffRound"] = Relationship(
        back_populates="bracket",
        passive_deletes="all",
    )


class PlayoffRoundBase(SQLModel):
    number: int  # 1, 2, 3 ...


class PlayoffRound(PlayoffRoundBase, table=True):
    __tablename__ = "playoff_rounds"

    id: int = Field(primary_key=True)
    bracket_id: int = Field(
        foreign_key="playoff_brackets.id",
        ondelete="CASCADE",
    )

    bracket: PlayoffBracket = Relationship(back_populates="rounds")
    matches: list["PlayoffMatch"] = Relationship(
        back_populates="round",
        passive_deletes="all",
    )


class PlayoffMatchBase(SQLModel):
    score1: int | None = None
    score2: int | None = None
    played: bool = False


class PlayoffMatch(PlayoffMatchBase, table=True):
    __tablename__ = "playoff_matches"

    id: int = Field(primary_key=True)

    round_id: int = Field(
        foreign_key="playoff_rounds.id",
        ondelete="CASCADE",
    )

    participant1_id: int | None = Field(
        foreign_key="tournament_participants.id",
        ondelete="SET NULL",
        default=None,
    )
    participant2_id: int | None = Field(
        foreign_key="tournament_participants.id",
        ondelete="SET NULL",
        default=None,
    )

    winner_id: int | None = Field(
        foreign_key="tournament_participants.id",
        ondelete="SET NULL",
        default=None,
    )

    round: PlayoffRound = Relationship(back_populates="matches")
