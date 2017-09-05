from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship, backref

from bot.Base import Base, Session

session = Session()


class GamePoll(Base):
    __tablename__ = 'game_polls'

    id = Column(Integer(), primary_key=True)
    event_id = Column(Integer(), ForeignKey('events.id'), index=True)
    active = Column(Boolean())
    finish_time = Column(DateTime())

    event = relationship("Event", uselist=False, backref=backref('game_polls'))
