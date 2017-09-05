from sqlalchemy import Column, Integer, String

from bot.Base import Base, Session

session = Session()


class Game(Base):
    __tablename__ = 'games'

    id = Column(Integer(), primary_key=True)
    bgg_id = Column(Integer(), index=True, unique=True)
    url = Column(String(128), nullable=False)
    title = Column(String(64), nullable=False)
    playtime = Column(String(16))
    description = Column(String(4096))
    image_url = Column(String(256))
    best_players = Column(String(16))
    recommended_players = Column(String(16))

    def get_game_info(self):
        output_dictionary = {
            "id": self.bgg_id,
            "url": self.url,
            "game_title": self.title,
            "playtime": self.playtime,
            "description": self.description,
            "image_url": self.image_url,
            "best": self.best_players,
            "recommended": self.recommended_players
        }
        return output_dictionary
