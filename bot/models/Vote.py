from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship, backref

from bot.Base import Base, Session

session = Session()


class Vote(Base):
    __tablename__ = 'votes'

    id = Column(Integer(), primary_key=True)
    member_id = Column(Integer(), ForeignKey('members.id'), index=True)
    suggestion_id = Column(Integer(), ForeignKey('suggestions.id'), index=True)

    member = relationship("Member", uselist=False, backref=backref('votes'))
    suggestion = relationship("Suggestion", uselist=False, backref=backref('votes'))
