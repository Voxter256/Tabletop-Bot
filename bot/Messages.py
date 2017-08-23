from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship, backref

from .Base import Base, Session

session = Session()


class Message(Base):

    __tablename__ = 'messages'

    id = Column(Integer(), primary_key=True)
    message_id = Column(Integer())
