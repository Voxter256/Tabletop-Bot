from sqlalchemy import Column, Integer, DateTime, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship, backref

from .Base import Base, Session

session = Session()


class Event(Base):
    __tablename__ = 'events'

    id = Column(Integer(), primary_key=True)
    date = Column(DateTime())
    name = Column(String(64))
    game_decided = Column(Boolean(), default=0)
    winning_game_id = Column(Integer(), ForeignKey('games.id'), default=1)

    winning_game = relationship("Game", uselist=False, backref=backref('events'))
