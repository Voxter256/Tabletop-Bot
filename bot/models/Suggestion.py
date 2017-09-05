from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship, backref

from bot.Base import Base, Session

session = Session()


class Suggestion(Base):
    __tablename__ = 'suggestions'

    id = Column(Integer(), primary_key=True)
    author_id = Column(Integer(), ForeignKey('members.id'), index=True)
    vote_number = Column(Integer(), unique=True)
    game_id = Column(Integer(), ForeignKey('games.id'), index=True)
    number_lost = Column(Integer())

    game = relationship("Game", uselist=False, backref=backref('suggestions'))
    author = relationship("Member", uselist=False, backref=backref('suggestions'))
