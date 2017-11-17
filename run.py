from bot.TabletopBot import TabletopBot
from bot.Base import Base, engine


if __name__ == '__main__':

    bot = TabletopBot()
    Base.metadata.create_all(engine)
    bot.run()

    # TODO Unit Tests
    # TODO Docker
