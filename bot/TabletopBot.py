import asyncio
import configparser
import discord
import html
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from sqlalchemy import func, desc
from aiohttp.errors import ClientOSError

from .Base import Session
from .Event import Event
from .Game import Game
from .GamePoll import GamePoll
from .Member import Member
from .Messages import Message
from .RSVP import RSVP
from .Suggestion import Suggestion
from .Vote import Vote


class TabletopBot(discord.Client):
    def __init__(self):
        self.session = Session()

        self.config = self.open_config()
        self.bound_channel = None

        self.available_commands = {
            "help": self.help,
            "events": self.events,
            "rsvp": self.rsvp,
            "cancel": self.cancel,
            "suggest": self.suggest,
            "suggestions": self.suggestions,
            "vote": self.vote,
            "power": self.power,
            "ping": self.ping,
            # admin commands
            'create_event': self.create_event,
            'cancel_event': self.cancel_event,
            "start_vote": self.start_vote,
            "clear_suggestions": self.clear_suggestions,
            "clear_messages": self.clear_messages,
            "end_vote": self.end_vote
        }

        super().__init__()

    def run(self):
        try:
            self.loop.run_until_complete(self.start(self.config["_login_token"]))
        except ClientOSError:
            asyncio.sleep(60)
            self.run()
            
    @staticmethod
    def open_config():
        config_parser = configparser.ConfigParser()
        config_parser.read("config\\options.ini")

        # TODO Fall-backs
        config = {
            "_login_token": config_parser.get('Credentials', 'Token'),
            "owner_id": config_parser.get('Permissions', 'OwnerID'),
            "command_prefix": config_parser.get('Chat', 'CommandPrefix'),
            "bound_channels": config_parser.get('Chat', 'BindToChannels')
        }
        return config

    async def on_ready(self):
        print('Logged in as ' + self.user.name)

        self.bound_channel = self.get_channel(self.config['bound_channels'])
        print("Bound to: " + self.bound_channel.name)

        poll = self.session.query(GamePoll).first()
        if poll is not None and poll.active:
            time_left = (poll.finish_time - datetime.now()).total_seconds()
            if time_left > 0:
                end_time = datetime.now() + timedelta(seconds=time_left)
                print("Voting over at: " + end_time.strftime("%c"))
                await asyncio.sleep(time_left)
            await self.finalize_vote()

    async def on_message(self, message):
        if message.channel.id != self.config['bound_channels']:
            return
        if len(message.content) < 1:
            return
        if message.content[0] != self.config["command_prefix"]:
            return

        print(str(message.author) + ": " + message.content)
        command = message.content[1:].split(" ")

        command_title = command[0].lower()

        try:
            await self.available_commands[command_title](message, command)
        except KeyError:
            await self.send_message_safe(self.bound_channel, "Not a valid command", 0, delete=False)

    async def ping(self, message, command):
        await self.send_message_safe(self.bound_channel, 'Pong!', 0, delete=False)

    async def events(self, message, command):
        all_events = self.session \
            .query(Event.id, Event.name, Event.date, Event.game_decided, Event.winning_game_id,
                   func.count(RSVP.id).label("count")) \
            .outerjoin(RSVP) \
            .filter(Event.date > datetime.now()) \
            .group_by(Event.id) \
            .all()
        if not all_events:
            message_to_send = "There are no events planned!"
            await self.send_message_safe(self.bound_channel, message_to_send, 30)
            return
        message_to_send = "Upcoming Events:"
        for event in all_events:
            event_datetime = event.date.strftime("%c")
            if event.game_decided:
                winning_game = self.session.query(Game).filter(Game.id == event.winning_game_id).first()
                message_to_send += "\n{0.id}) {0.name} at {1} with {0.count} attending ".format(event, event_datetime)
                message_to_send += "playing " + winning_game.title + " | <" + winning_game.url + ">"
            else:
                message_to_send += "\n{0.id}) {0.name} at {1} with {0.count} attending.".format(event, event_datetime)
        await self.send_message_safe(self.bound_channel, message_to_send, 0, delete=False)

    async def suggest(self, message, command):
        try:
            bgg_query = command[1]
            bgg_query_long = command[1:]
        except IndexError:
            message_to_send = "The format needs to be !suggest [Suggestion]"
            await self.send_message_safe(self.bound_channel, message_to_send, 30)
            return

        poll_active = self.session.query(GamePoll.active).first()
        if poll_active:
            output_string = "Voting is active, no more suggestions until it is finished!"
            await self.send_message_safe(self.bound_channel, output_string, 10)
            return

        game_id = await self.get_game_id(bgg_query, bgg_query_long)
        game_database_entry = self.session.query(Game).filter(Game.bgg_id == game_id).first()
        if game_database_entry is None:
            game_info = self.generate_suggestion(game_id)
            game_database_entry = Game(
                bgg_id=game_info["id"],
                url=game_info["url"],
                title=game_info["game_title"],
                playtime=game_info["playtime"],
                description=game_info["description"],
                image_url=game_info["image_url"],
                best_players=game_info["best"],
                recommended_players=game_info["recommended"]
            )
            self.session.add(game_database_entry)
            self.session.commit()
        else:
            game_info = game_database_entry.get_game_info()
        previous_suggestion = self.session.query(Suggestion.id, Member.name).join(Member).filter(
            Suggestion.game_id == game_database_entry.id).first()
        if previous_suggestion is not None:
            message_to_send = "This game has already been suggested by " + previous_suggestion.name
            print(message_to_send)
            await self.send_message_safe(self.bound_channel, message_to_send, 30)
            return

        # make lowest possible vote_number
        results = self.session.query(Suggestion.vote_number).order_by(Suggestion.vote_number).all()
        open_vote_number = 1
        current_vote_numbers = []
        for result in results:
            current_vote_numbers.append(result.vote_number)

        while True:
            if open_vote_number in current_vote_numbers:
                open_vote_number += 1
                continue
            else:
                break

        member = self.get_member(message)

        self.session.add(Suggestion(
            author_id=member.id,
            vote_number=open_vote_number,
            game_id=game_database_entry.id,
            number_lost=0
        ))
        self.session.commit()

        await self.output_suggestion_game_info(game_info)

    async def help(self, message, command):
        string_list = [
            "---Command List---\n",
            "!help",
            "Displays the Command List\n",

            "!events",
            "Displays all future events\n",

            "!rsvp [Event ID]",
            "RSVP to a specific Event, also allows you to vote\n",

            "!cancel [Event ID]",
            "Cancels a RSVP to an Event\n",

            "!suggest [suggestion]",
            "Suggest a board game to play",
            "[suggestion] can be a game title to search, a BoardGameGeek game url, " +
            "or the numerical game ID from the url\n",

            "!suggestions",
            "View all current suggestions\n",

            "!show",
            "Display all the board games suggested so far\n",

            "!vote",
            "Vote on a game once voting has begun. If your game isn't picked, your voting power increases by one for" +
            " next time, otherwise it reset to one\n",

            "!power",
            "Display your current voting power\n",

            "!ping",
            "Check if the bot is running, it responds with pong\n",

            "---Owner Commands---",
            "!create_event [YYYY-MM-DD] [2359] [Event Name]",
            "Creates an event with a given date, time, and name\n",

            "!cancel_event [Event ID]",
            "Cancels the given event\n",

            "!start_vote [Event ID] [Hours]",
            "Begin voting on the selected event, ending in [Hours] hours\n",

            "!end_vote",
            "Immediately end voting\n",

            "!clear_suggestions",
            "Clear all Suggestions\n",

            "!clear_messages",
            "Delete the last 1000 messages in the channel that are not pinned"
        ]

        message_to_send = "\n".join(string_list)
        await self.send_message_safe(self.bound_channel, message_to_send, 0, delete=False)
        return

    async def rsvp(self, message, command):
        try:
            event_id = command[1]
        except IndexError:
            message_to_send = "You need to event an Event ID"
            await self.send_message_safe(self.bound_channel, message_to_send, 30)
            return

        # check if it is a real event
        this_event = self.session.query(Event).filter(Event.id == event_id).first()
        if this_event is None:
            message_to_send = "This is not a valid Event ID"
            await self.send_message_safe(self.bound_channel, message_to_send, 30)
            return
        # check if already rsvp'd
        member = self.get_member(message)
        previous_rsvp = self.session.query(RSVP).filter(RSVP.member_id == member.id, RSVP.event_id == event_id).first()
        if previous_rsvp is not None:
            message_to_send = "You already RSVP'd, but now you can be sure!"
            await self.send_message_safe(self.bound_channel, message_to_send, 30)
            return
        new_rsvp = RSVP(member_id=member.id, event_id=event_id)
        self.session.add(new_rsvp)
        self.session.commit()

        current_player_count = len(self.session.query(RSVP).filter(RSVP.event_id == event_id).all())
        if current_player_count == 1:
            message_to_send = "Ok I've got you down! There is currently 1 person attending"
        else:
            message_to_send = "Ok I've got you down! There are currently {0} people attending".format(
                current_player_count)
        await self.send_message_safe(self.bound_channel, message_to_send, 0, delete=False)
        return

    async def cancel(self, message, command):
        try:
            event_id = command[1]
        except IndexError:
            message_to_send = "You need to event an Event ID"
            await self.send_message_safe(self.bound_channel, message_to_send, 30)
            return

        # check if it is a real event
        this_event = self.session.query(Event).filter(Event.id == event_id).first()
        if this_event is None:
            message_to_send = "This is not a valid Event ID"
            await self.send_message_safe(self.bound_channel, message_to_send, 30)
            return

        # check if rsvp'd
        member = self.get_member(message)
        previous_rsvp = self.session.query(RSVP).filter(RSVP.member_id == member.id,
                                                        RSVP.event_id == event_id).first()
        if previous_rsvp is None:
            message_to_send = "You never RSVP'd, so we know your aren't coming!"
            await self.send_message_safe(self.bound_channel, message_to_send, 30)
            return

        self.session.delete(previous_rsvp)
        self.session.commit()

        current_player_count = len(self.session.query(RSVP).filter(RSVP.event_id == event_id).all())
        if current_player_count == 1:
            message_to_send = "Sorry to hear you have to cancel! There is now 1 person attending"
        else:
            message_to_send = "Sorry to hear you have to cancel! There is now {0} people attending".format(
                current_player_count)
        await self.send_message_safe(self.bound_channel, message_to_send, 0, delete=False)
        return

    async def suggestions(self, message, command):
        current_suggestions = self.session.query(Game).join(Suggestion).all()
        if not current_suggestions:
            message_to_send = "There are currently no suggestions!"
            await self.send_message_safe(self.bound_channel, message_to_send, 60)
            return
        for suggestion in current_suggestions:
            await self.output_suggestion_game_info(suggestion.get_game_info())

    async def vote(self, message, command):
        this_poll = self.session.query(GamePoll).first()
        if not this_poll:
            message_to_send = "Voting has not yet begun!"
            await self.send_message_safe(self.bound_channel, message_to_send, 10)
            return

        # check if rsvp
        this_member = self.get_member(message)
        this_rsvp = self.session.query(GamePoll).join(Event).join(RSVP).join(Member).filter(
            Member.id == this_member.id).first()
        if not this_rsvp:
            message_to_send = "You can't vote if you didn't RSVP!"
            await self.send_message_safe(self.bound_channel, message_to_send, 10)
            return

        try:
            game_vote = command[1]
        except IndexError:
            message_to_send = "You didn't pick anything!"
            await self.send_message_safe(self.bound_channel, message_to_send, 30)
            return

        if not game_vote.isdigit():
            message_to_send = "You need to vote using a number!"
            await self.send_message_safe(self.bound_channel, message_to_send, 10)
            return
        if self.session.query(Suggestion).filter(Suggestion.vote_number == command[1]).first() is None:
            message_to_send = "Not a valid vote!"
            await self.send_message_safe(self.bound_channel, message_to_send, 10)
            return

        # check if already voted, delete old vote
        old_vote = self.session.query(Vote).join(Member).filter(Vote.member_id == this_member.id).first()
        if old_vote is not None:
            self.session.delete(old_vote)
            self.session.commit()

        # add new vote
        suggestion = self.session.query(Suggestion).filter(Suggestion.vote_number == int(game_vote)).first()
        new_vote = Vote(member_id=this_member.id, suggestion_id=suggestion.id)
        self.session.add(new_vote)
        self.session.commit()

        # get current totals
        current_vote_totals = self.get_current_vote_totals()

        # display current totals
        message_list = []
        for this_vote_total in current_vote_totals:
            message_list.append(str(this_vote_total.vote_number) + ") " + this_vote_total.title + " votes: " + str(
                this_vote_total.vote_quantity))
        message_to_send = "\n".join(message_list)
        this_message = await self.send_message_safe(self.bound_channel, message_to_send, 0, delete=False)
        self.session.add(Message(message_id=this_message.id))

        self.session.commit()

    async def power(self, message, command):
        member = self.get_member(message)
        member_power = member.power
        if member_power == 1:
            message_to_send = "Your vote currently counts as 1 vote"
        else:
            message_to_send = "Your vote currently counts as " + str(member_power) + " votes"
        await self.send_message_safe(self.bound_channel, message_to_send, 60)
        return

    async def start_vote(self, message, command):
        if message.author.id != self.config["owner_id"]:
            message_to_send = "You don't have permission to start_vote"
            await self.send_message_safe(self.bound_channel, message_to_send, 10)
            return

        poll_active = self.session.query(GamePoll.active).first()
        if poll_active:
            message_to_send = "Voting has already begun!"
            await self.send_message_safe(self.bound_channel, message_to_send, 10)
            await self.delete_message(message)
            return

        try:
            event_id = command[1]
            hours_string = command[2]
        except IndexError:
            message_to_send = "Needs to use the format !start_vote [Event ID] [Hours]"
            await self.send_message_safe(self.bound_channel, message_to_send, 30)
            return

        if hours_string.isdigit() is False:
            message_to_send = "Need a numerical parameter for hours!"
            await self.send_message_safe(self.bound_channel, message_to_send, 30)
            await self.delete_message(message)
            return

        if self.session.query(Suggestion).first() is None:
            message_to_send = "There are no suggestions!"
            await self.send_message_safe(self.bound_channel, message_to_send, 30)
            await self.delete_message(message)
            return

        this_event = self.session.query(Event).filter(Event.id == event_id).first()
        if this_event is None:
            message_to_send = "Event with that ID not found!"
            await self.send_message_safe(self.bound_channel, message_to_send, 30)
            await self.delete_message(message)
            return

        if this_event.game_decided:
            message_to_send = "This event has already selected a game!"
            await self.send_message_safe(self.bound_channel, message_to_send, 30)
            await self.delete_message(message)
            return

        voting_duration = int(command[1])
        voting_over = datetime.now() + timedelta(hours=voting_duration)

        self.session.add(GamePoll(active=True, finish_time=voting_over, event_id=event_id))

        event_rsvps = self.session \
            .query(Event.id, func.count(RSVP.id).label("count")) \
            .outerjoin(RSVP) \
            .filter(Event.id == event_id) \
            .group_by(Event.id) \
            .first()
        rsvp_count = event_rsvps.count

        directions_string = "@Meeples\n It's time to vote on games for " + this_event.name + "!" + \
                            " Use the !vote command followed by the game's id below (e.g. !vote 1).\n" + \
                            " Voting ends at " + voting_over.strftime("%H:%M %Z on %m/%d") + "\n" + \
                            " There are currently " + str(rsvp_count) + " attendees, so keep player counts in mind." + \
                            " There will be multiple groups if there are enough players to do so." + \
                            " RSVP count isn't finalized, as anyone can cancel or join last minute."
        directions_message = await self.send_message_safe(self.bound_channel, directions_string, 0, delete=False)
        self.session.add(Message(message_id=directions_message.id))

        for suggestion in self.session.query(Suggestion.vote_number, Game.title, Game.url).join(Game).all():
            message_to_send = str(suggestion.vote_number) + ") " + suggestion.title + " | <" + \
                              suggestion.url + ">"
            this_message = await self.send_message_safe(self.bound_channel, message_to_send, 0, delete=False)
            self.session.add(Message(message_id=this_message.id))

        self.session.commit()

        await self.delete_message(message)
        await asyncio.sleep((voting_duration * 60 * 60) - (5 * 60))

        message_to_send = "@Meeples 5 minutes left to vote!"
        this_message = await self.send_message_safe(self.bound_channel, message_to_send, 0, delete=False)
        self.session.add(Message(message_id=this_message.id))
        self.session.commit()

        await asyncio.sleep(5 * 60)
        await self.finalize_vote()

    async def end_vote(self, message, command):
        if message.author.id != self.config["owner_id"]:
            message_to_send = "You don't have permission to delete_all"
            await self.send_message_safe(self.bound_channel, message_to_send, 10)
            return

        await self.finalize_vote()

    async def create_event(self, message, command):
        if message.author.id != self.config["owner_id"]:
            message_to_send = "You don't have permission to delete_all"
            await self.send_message_safe(self.bound_channel, message_to_send, 10)
            return
        try:
            date_string = command[1]
            time_string = command[2]
            name_string = " ".join(command[3:])
        except IndexError:
            message_to_send = "Not the correct format: !create_event YYYY-MM-DD 2359 event_name"
            await self.send_message_safe(self.bound_channel, message_to_send, 30)
            return

        datetime_string = date_string + " " + time_string
        try:
            event_date_time = datetime.strptime(datetime_string, "%Y-%m-%d %H%M")  # YYYY-MM-DD 2359
        except ValueError:
            print(datetime_string)
            message_to_send = "Not a valid date and time format (YYYY-MM-DD 2359)"
            await self.send_message_safe(self.bound_channel, message_to_send, 30)
            return

        if event_date_time < datetime.now():
            message_to_send = "Event can't be in the past!"
            await self.send_message_safe(self.bound_channel, message_to_send, 30)
            return

        new_event = Event(date=event_date_time, name=name_string)
        self.session.add(new_event)
        self.session.commit()

        event_time_delta = new_event.date - datetime.now()
        delta_days = event_time_delta.days
        days_string = "1 day" if delta_days == 1 else str(delta_days) + " days"
        delta_hours = int(event_time_delta.seconds / 3600)
        if delta_hours == 0:
            hours_string = ""
        elif delta_hours == 1:
            hours_string = " 1 hour"
        else:
            hours_string = " " + str(delta_hours) + " hours"
        if delta_days == 0 and delta_hours == 0:
            time_till_event_string = " less than an hour"
        else:
            time_till_event_string = days_string + hours_string
        message_to_send = "@Meeples\nNew Event Created!\n{0.id}) {0.name} in {1}.".format(new_event,
                                                                                          time_till_event_string)
        await self.send_message_safe(self.bound_channel, message_to_send, 0, delete=False)
        return

    async def cancel_event(self, message, command):
        if message.author.id != self.config["owner_id"]:
            message_to_send = "You don't have permission to cancel_event"
            await self.send_message_safe(self.bound_channel, message_to_send, 10)
            return
        try:
            event_id = command[1]
        except IndexError:
            message_to_send = "You need to enter an event id!"
            await self.send_message_safe(self.bound_channel, message_to_send, 30)
            return
        result = self.session.query(Event).filter(Event.id == event_id).first()
        self.session.delete(result)

        # delete associated GamePoll, Votes, Messages, and RSVPs
        game_poll = self.session.query(GamePoll).filter(GamePoll.event_id == event_id).first()
        if game_poll is not None:
            self.session.delete(game_poll)
            votes = self.session.query(Vote).all()
            for item in votes:
                self.session.delete(item)
            await self.delete_saved_messages()
        event_rsvps = self.session.query(RSVP).filter(RSVP.event_id == event_id).all()
        if event_rsvps is not None:
            for item in event_rsvps:
                self.session.delete(item)

        self.session.commit()
        message_to_send = "Done"
        await self.send_message_safe(self.bound_channel, message_to_send, 10)
        return

    async def clear_suggestions(self, message, command):
        if message.author.id != self.config["owner_id"]:
            message_to_send = "You don't have permission to delete_all"
            await self.send_message_safe(self.bound_channel, message_to_send, 10)
            return
        for suggestion in self.session.query(Suggestion).all():
            self.session.delete(suggestion)
        self.session.commit()
        message_to_send = "Done"
        await self.send_message_safe(self.bound_channel, message_to_send, 10)
        return

    async def clear_messages(self, message, command):
        if message.author.id != self.config["owner_id"]:
            message_to_send = "You don't have permission to delete_all"
            await self.send_message_safe(self.bound_channel, message_to_send, 10)
            return

        def is_pinned(m):
            for this_pinned_message in pinned_messages:
                if m.id == this_pinned_message.id:
                    return False
            return True

        pinned_messages = await self.pins_from(self.bound_channel)
        await self.purge_from(self.bound_channel, limit=1000, check=is_pinned)
        for item in self.session.query(Message).all():
            self.session.delete(item)
        self.session.commit()

    async def finalize_vote(self):
        current_vote_totals = self.get_current_vote_totals()
        if current_vote_totals is None:
            print("No vote totals")
            game_poll = self.session.query(GamePoll).first()
            if game_poll is None or game_poll.active is False:
                return
            self.session.delete(game_poll)
            for vote in self.session.query(Vote).all():
                self.session.delete(vote)
            # delete all messages related to this poll
            await self.delete_saved_messages()
            message_to_send = "Voting ended with no winner."
            await self.send_message_safe(self.bound_channel, message_to_send, 30)
            return
        winner = current_vote_totals[0]

        # announce winner
        if winner.vote_quantity == 1:
            message_to_send = winner.title + " won with " + str(winner.vote_quantity) + " vote!"
        else:
            message_to_send = winner.title + " won with " + str(winner.vote_quantity) + " votes!"
        await self.send_message_safe(self.bound_channel, message_to_send, 0, delete=False)

        # delete all messages related to this poll
        await self.delete_saved_messages()

        # if your vote lost, increase vote power
        losing_voters = self.session.query(Member).join(Vote).filter(
            Vote.suggestion_id != winner.id).all()
        for voter in losing_voters:
            voter.power += 1

        # if suggestion won, reset vote power
        winning_voters = self.session.query(Member).join(Vote).filter(
            Vote.suggestion_id == winner.id).all()
        for item in winning_voters:
            item.power = 1

        # delete all votes
        for vote in self.session.query(Vote).all():
            self.session.delete(vote)
        self.session.commit()

        # delete suggestion if it has lost 5 or more times in a row
        for losing_suggestion in current_vote_totals[1:]:
            this_suggestion = self.session.query(Suggestion).filter(Suggestion.id == losing_suggestion.id).first()
            new_number_lost = this_suggestion.number_lost + 1
            if new_number_lost >= 5:
                self.session.delete(this_suggestion)
            else:
                this_suggestion.number_lost = new_number_lost
        self.session.commit()

        # update number_lost on winning suggestion
        winning_suggestion = self.session.query(Suggestion).filter(Suggestion.id == current_vote_totals[0].id).first()
        winning_suggestion.number_lost = 0
        self.session.commit()

        game_poll = self.session.query(GamePoll).first()
        if game_poll is None or game_poll.active is False:
            return

        # Update the event: The game has been decided
        this_event = self.session.query(Event).filter(Event.id == game_poll.event_id).first()
        if this_event is None:
            print("Missing event in finalize_vote")
        this_event.game_decided = True
        this_event.winning_game_id = winning_suggestion.game_id

        self.session.delete(game_poll)
        self.session.commit()

    def get_current_vote_totals(self):
        if self.session.query(Vote).first() is None:
            return None
        result = self.session.query(
            Suggestion.id,
            Suggestion.vote_number,
            Game.bgg_id.label("game_id"),
            Game.title,
            func.sum(Member.power).label('vote_quantity')) \
            .join(Game) \
            .outerjoin(Vote).outerjoin(Member) \
            .group_by(Suggestion.id) \
            .order_by(desc('vote_quantity')) \
            .all()
        return result

    # gets member or creates one if they don't exist
    def get_member(self, message):
        member = self.session.query(Member).filter(Member.name == str(message.author)).first()
        if member is None:
            member = Member(name=str(message.author), power=1)
            self.session.add(member)
            self.session.commit()
        return member

    async def output_suggestion_game_info(self, game_info):
        if len(game_info["description"]) > 2044:
            output_description = game_info["description"][0:2043] + "..."
        else:
            output_description = game_info["description"]

        embed = discord.Embed(title=game_info["game_title"], type="rich", url=game_info["url"])
        embed.set_image(url=game_info["image_url"])
        embed.add_field(name="Playtime", value=game_info["playtime"])
        embed.add_field(name="Recommended", value=game_info["recommended"])
        embed.add_field(name="Best with", value=game_info["best"] + " players")
        embed.set_footer(text=output_description)

        await self.send_message(self.bound_channel, content=None, embed=embed)

    @staticmethod
    def generate_suggestion(game_id):
        url_xml = "https://boardgamegeek.com/xmlapi/boardgame/" + game_id
        page = requests.get(url_xml)
        soup = BeautifulSoup(page.content, 'xml')
        # print(soup.prettify())

        description = html.unescape(soup.find("description").text).replace("<br/>", "\n")
        image_url = soup.find("image").text

        suggested_players_poll = soup.find("poll", {"name": "suggested_numplayers"})
        results = suggested_players_poll.find_all("results")
        result_dictionary = {}
        for result in results:
            result_dictionary[result.attrs["numplayers"]] = {
                "Best": int(result.find("result", {"value": "Best"}).attrs["numvotes"]),
                "Recommended": int(result.find("result", {"value": "Recommended"}).attrs["numvotes"]),
                "Not Recommended": int(result.find("result", {"value": "Not Recommended"}).attrs["numvotes"]),
            }

        result_conclusions = {
            "Best": {
                "number of players": None,
                "votes": 0
            },
            "Recommended": {
                "min-title": None,
                "min-value": 1000,
                "max-title": None,
                "max-value": -1
            }
        }
        for number_of_players, suggestions in result_dictionary.items():
            # best first
            if suggestions["Best"] > result_conclusions["Best"]["votes"]:
                result_conclusions["Best"] = {
                    "number of players": number_of_players,
                    "votes": suggestions["Best"]
                }
            if suggestions["Best"] + suggestions["Recommended"] > suggestions["Not Recommended"]:
                if number_of_players.find("+") != -1:
                    result_conclusions["Recommended"]["max-title"] = number_of_players
                    result_conclusions["Recommended"]["max-value"] = int(number_of_players[:-1]) + 1
                else:
                    int_players = int(number_of_players)
                    if int_players > result_conclusions["Recommended"]["max-value"]:
                        result_conclusions["Recommended"]["max-value"] = int_players
                        result_conclusions["Recommended"]["max-title"] = number_of_players
                    if int_players < result_conclusions["Recommended"]["min-value"]:
                        result_conclusions["Recommended"]["min-value"] = int_players
                        result_conclusions["Recommended"]["min-title"] = number_of_players

        recommended_string = str(result_conclusions["Recommended"]["min-title"]) + "-" + str(
            result_conclusions["Recommended"]["max-title"]) + " Players"

        min_playtime = soup.find("minplaytime").text
        max_playtime = soup.find("maxplaytime").text
        if min_playtime == max_playtime:
            playtime = min_playtime + " minutes"
        else:
            playtime = min_playtime + "-" + max_playtime + " minutes"

        game_info = {
            "id": game_id,
            "url": "https://www.boardgamegeek.com/boardgame/" + game_id,
            "game_title": soup.find("name", {"primary": "true"}).text,
            "playtime": playtime,
            "description": description,
            "image_url": image_url,
            "best": result_conclusions["Best"]["number of players"],
            "recommended": recommended_string
        }

        return game_info

    async def send_message_safe(self, channel, output_string, timeout, delete=True):
        response_message = await self.send_message(channel, output_string)
        if delete:
            await asyncio.sleep(timeout)
            try:
                await self.delete_message(response_message)
            except discord.errors.NotFound:
                print("message already deleted")
            return
        else:
            return response_message

    async def get_game_id(self, bgg_query, bgg_query_long):
        regex_url = re.fullmatch('^(https://)(www.)*(boardgamegeek.com/boardgame/)[\d]+/[\w\d-]*', bgg_query)
        if regex_url is not None:
            game_id_match = re.search('/[\d]+/', regex_url.string)
            if game_id_match is None:
                # TODO real exception?
                print("Error: URL inconsistent")
                return
            else:
                game_id = game_id_match.group(0)[1:-1]
        else:
            regex_game_id = re.fullmatch('[\d]*', bgg_query)
            if regex_game_id is not None:
                game_id = bgg_query
            else:
                search_string = ""
                for part in bgg_query_long:
                    if search_string != "":
                        search_string += "%20"
                    search_string += part
                url_xml = "https://www.boardgamegeek.com/xmlapi/search?search=" + search_string
                page = requests.get(url_xml)
                soup = BeautifulSoup(page.content, 'xml')
                this_game = soup.boardgame
                if this_game is None:
                    message_to_send = "No game found!"
                    print(message_to_send)
                    await self.send_message_safe(self.bound_channel, message_to_send, 30)
                    return
                game_id = this_game.attrs["objectid"]
        return game_id

    async def delete_saved_messages(self):
        message_objects_to_delete = self.session.query(Message).all()
        messages_to_delete = []
        for item in message_objects_to_delete:
            try:
                this_message = await self.get_message(self.bound_channel, item.message_id)
            except discord.errors.NotFound:
                continue
            messages_to_delete.append(this_message)
            self.session.delete(item)

        number_messages_to_delete = len(messages_to_delete)
        if number_messages_to_delete > 1:
            await self.delete_messages(messages_to_delete)
        elif number_messages_to_delete == 1:
            await self.delete_message(self.messages_to_delete_after_vote[0])
