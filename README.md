## Synopsis

This is a bot for Discord written in Python made to manage tabletop game nights. It handles the events, RSVPs, game suggestions, and helps to balance votes so everyone can have an opportunity to play what they want. It also interfaces with the XML API of https://www.boardgamegeek.com to get details such as playtime and community suggested player counts.

## Code Example

!suggest https://boardgamegeek.com/boardgame/72125/eclipse
- Suggestions are given an ID
!start_event 2017-08-22 2000 Solar Eclipse Night
!rsvp 1
- events are given an ID which is printed
!start_voting 1 24
- allows voting on the event for [24] hours
!vote 1
- votes on a suggestion. Your power increases every time your vote loses

## Motivation

I desire to create a community of people who are interested in playing tabletop games on the regular, in small and larger group settings. Specifically, this is being used for Tabletop Simulator on steam, as most members of the server are not in the same metropolitan area as I am. This aids in me managing events in which people can attend whenever they are available.

## Installation

Copy the default_options.ini and complete it using the instructions inside
Copy default_sqlite.db to bot.db (it is an empty file)

This Bot currently uses SQLite and the following python plugins from pip:
SQLAlchemy
beautifulsoup4
boardgamegeek
discord.py
lxml
requests

## API Reference
###### All Users
!help
Displays the Command List

!events
Displays all future events

!rsvp [Event ID]
RSVP to a specific Event, also allows you to vote

!cancel [Event ID]
Cancels a RSVP to an Event

!suggest [suggestion]
Suggest a board game to play
[suggestion] can be a game title to search, a BoardGameGeek game url, or the numerical game ID from the url

!suggestions
View all current suggestions

!show
Display all the board games suggested so far

!vote
Vote on a game once voting has begun. If your game isn't picked, your voting power increases by one for next time, otherwise it reset to one

!power
Display your current voting power

!ping
Check if the bot is running, it responds with pong

###### Owner Commands
!create_event [YYYY-MM-DD] [2359] [Event Name]
Creates an event with a given date, time, and name

!cancel_event [Event ID]
Cancels the given event

!start_vote [Event ID] [Hours]
Begin voting on the selected event, ending in [Hours] hours

!end_vote
Immediately end voting

!clear_suggestions
Clear all Suggestions

!clear_messages
Delete the last 1000 messages in the channel that are not pinned
## Tests

Describe and show how to run the tests with code examples.

## Contributors

I'm currently tracking issues here in GitHub. I encourage feature suggestions as well as code improvement! There is plenty of work that needs done

## License

MIT License per LICENSE.txt