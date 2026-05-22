from typing import List, Optional, TYPE_CHECKING
from sqlmodel import Field, Relationship, SQLModel
from sqlalchemy.orm import relationship as sa_relationship
import datetime

if TYPE_CHECKING:
    from .user import User
    from .region import Region
    from .sex import Sex
    from .category import Category
    from .participant import TournamentParticipant
    from .group import GroupStage


class TournamentBase(SQLModel):
    name: str
    type: str
    is_child: bool = Field(default=False)
    photo_path: str = Field(default=None, nullable=True)
    organizer_name_and_contacts: Optional[str] = None
    organizer_requisites: Optional[str] = None
    date: Optional[datetime.date] = None
    description: Optional[str] = None
    price: Optional[int] = None
    can_register: bool = Field(default=True)
    address: Optional[str] = None
    prize_fund: Optional[str] = None
    comment: Optional[str] = None
    is_grand: bool = Field(default=False, description="Гранд турнир")


class Tournament(TournamentBase, table=True):
    __tablename__ = "tournaments"
    id: Optional[int] = Field(primary_key=True, default=None)
    region_id: int = Field(foreign_key="regions.id")
    sex_id: Optional[int] = Field(default=None, foreign_key="sex.id", nullable=True)
    category_id: int = Field(foreign_key="categories.id")
    owner_id: int = Field(foreign_key="users.id")

    owner: "User" = Relationship(back_populates="tournaments")
    region: "Region" = Relationship(back_populates="tournaments")
    sex: Optional["Sex"] = Relationship(back_populates="tournaments")
    category: "Category" = Relationship(back_populates="tournaments")
    participants: List["TournamentParticipant"] = Relationship(
        back_populates="tournament",
        sa_relationship=sa_relationship(
            "TournamentParticipant",
            back_populates="tournament",
            cascade="all, delete, delete-orphan",
        ),
    )
    groups: List["GroupStage"] = Relationship(
        back_populates="tournament",
        sa_relationship=sa_relationship(
            "GroupStage",
            back_populates="tournament",
            passive_deletes=True,
        ),
    )


class TournamentUpdate(TournamentBase):
    owner_id: Optional[int]
    sex_id: Optional[int]
    category_id: Optional[int]
    region_id: Optional[int]
    is_grand: Optional[bool] = None


class TournamentCreate(TournamentBase):
    owner_id: int
    sex_id: Optional[int] = None
    category_id: int
    region_id: int
    is_grand: Optional[bool] = None


class TournamentPublic(TournamentBase):
    is_grand: bool = False
    id: int
    owner_id: int
    sex_id: Optional[int]
    category_id: int
    region_id: int


class TournamentsPublic(SQLModel):
    data: List[TournamentPublic]
    count: int


class TournamentCountResponse(SQLModel):
    count_of_tournament_last_52_weeks: int
