from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship, backref

from .Base import Base, Session

session = Session()


class RSVP(Base):
    __tablename__ = 'rsvps'

    id = Column(Integer(), primary_key=True)
    event_id = Column(Integer(), ForeignKey('events.id'), index=True)
    member_id = Column(Integer(), ForeignKey('members.id'), index=True)

    member = relationship("Member", uselist=False, backref=backref('rsvp'))
    event = relationship("Event", uselist=False, backref=backref('rsvp'))
