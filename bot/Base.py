from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

engine = create_engine('sqlite:///bot.db')
Session = sessionmaker(bind=engine)
Base = declarative_base()
