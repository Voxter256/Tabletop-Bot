from sqlalchemy import Column, Integer, String

from .Base import Base, Session

session = Session()


class Member(Base):
    __tablename__ = 'members'

    id = Column(Integer(), primary_key=True)
    name = Column(String(64), index=True)
    power = Column(Integer())
