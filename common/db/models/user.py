from typing import List, Optional, TYPE_CHECKING
from pydantic import EmailStr, computed_field, field_serializer
from sqlalchemy import BigInteger, Column
from sqlmodel import Field, Relationship, SQLModel
import datetime


if TYPE_CHECKING:
    from .region import Region
    from .tournament import Tournament
    from .sex import Sex
    from .transaction import Transaction
    from .comment import Comment
    from .news import News


class UserBase(SQLModel):
    name: str = Field(max_length=255, nullable=True)
    surname: str = Field(max_length=255, nullable=True)
    patronymic: str = Field(max_length=255, nullable=True)
    score: int | None = Field(default=0, nullable=True)
    admin: bool = Field(default=False)
    telegram_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            nullable=True,
        )
    )
    max_user_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            nullable=True,
        )
    )
    max_chat_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            nullable=True,
        )
    )
    vk_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            nullable=True,
        )
    )
    organizer: bool | None = Field(default=False, nullable=True)
    end_of_subscription: Optional[datetime.datetime] = Field(default=None, nullable=True)
    updated_at: Optional[datetime.datetime] = Field(
        default_factory=datetime.datetime.now,
        nullable=True
    )
    created_at: Optional[datetime.datetime] = Field(
        default_factory=datetime.datetime.now,
        nullable=True
    )
    phone_number: Optional[str] = Field(default=None, nullable=True)
    email: EmailStr = Field(max_length=255, nullable=True)
    birth_date: Optional[datetime.date] = Field(default=None, nullable=True)

    @computed_field
    @property
    def subscriber(self) -> bool:
        if self.end_of_subscription is None:
            return False
        return (
            self.end_of_subscription.replace(tzinfo=datetime.timezone.utc)
            > datetime.datetime.now(datetime.timezone.utc)
        )
    
    @field_serializer
    def serialize_email(self, email: EmailStr) -> str:
        return email.lower()

    @computed_field
    @property
    def age(self) -> int:
        if self.birth_date is None:
            return 0
        today = datetime.datetime.now().date()
        return (
            today.year - self.birth_date.year - (
                (today.month, today.day) < (self.birth_date.month, self.birth_date.day)
            )
        )


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=40)
    region_id: int
    sex_id: int


class UserRegister(SQLModel):
    email: EmailStr
    password: str
    name: str
    surname: str
    patronymic: str
    phone_number: str
    telegram_id: Optional[int] = None
    max_registration_token: Optional[str] = None
    vk_registration_token: Optional[str] = None
    verification_provider: str = "max"
    birth_date: datetime.date
    sex_id: int
    region_id: int


class UserUpdate(UserBase):
    email: Optional[EmailStr] = Field(default=None, max_length=255)
    updated_at: datetime.datetime = Field(
        default_factory=datetime.datetime.now)
    sex_id: Optional[int]
    region_id: Optional[int]


class UserUpdateMe(UserBase):
    email: Optional[EmailStr] = Field(default=None, max_length=255)
    updated_at: datetime.datetime = Field(
        default_factory=datetime.datetime.now)
    sex_id: Optional[int]
    region_id: Optional[int]


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=40)
    new_password: str = Field(min_length=8, max_length=40)


class UserPublic(UserBase):
    id: int
    region_id: Optional[int]
    sex_id: Optional[int]


class UserFio(SQLModel):
    name: str
    surname: str
    patronymic: str


class User(UserBase, table=True):
    __tablename__ = 'users'
    id: Optional[int] = Field(primary_key=True, default=None)
    hashed_password: Optional[str] = Field(default=None, nullable=True)

    region_id: Optional[int] = Field(foreign_key="regions.id")
    sex_id: Optional[int] = Field(foreign_key="sex.id")

    region: "Region" = Relationship(back_populates="users")
    sex: "Sex" = Relationship(back_populates="users")
    tournaments: List["Tournament"] = Relationship(back_populates="owner")
    transactions: List["Transaction"] = Relationship(back_populates="user")
    comments: List["Comment"] = Relationship(back_populates="creator")
    news: List["News"] = Relationship(back_populates="creator")


class UsersPublic(SQLModel):
    data: List[UserPublic]
    count: int
