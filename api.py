# -*- coding: utf-8 -*-`
"""api.py - Create and configure the Game API exposing the resources.
api.py also contains the hangman game logic. For more complex games it would be wise to
move game logic to another file. Ideally the API will be simple, concerned
primarily with communication to/from the API's users."""


import logging
import endpoints
from protorpc import remote, messages
from google.appengine.api import memcache
from google.appengine.api import taskqueue

from models import User, Game, Score
from models import StringMessage, NewGameForm, GameForm, GuessForm,\
    ScoreForms
from utils import get_by_urlsafe

NEW_GAME_REQUEST = endpoints.ResourceContainer(NewGameForm)
GET_GAME_REQUEST = endpoints.ResourceContainer(
        urlsafe_game_key=messages.StringField(1),)
GUESS_REQUEST = endpoints.ResourceContainer(
    GuessForm,
    urlsafe_game_key=messages.StringField(1),)
USER_REQUEST = endpoints.ResourceContainer(user_name=messages.StringField(1),
                                           email=messages.StringField(2))

MEMCACHE_GUESSES_REMAINING = 'GUESSES_REMAINING'

@endpoints.api(name='hangman', version='v1')
class HangmanApi(remote.Service):
    """Game API"""
    @endpoints.method(request_message=USER_REQUEST,
                      response_message=StringMessage,
                      path='user',
                      name='create_user',
                      http_method='POST')
    def create_user(self, request):
        """Create a User. Requires a unique username"""
        if User.query(User.name == request.user_name).get():
            raise endpoints.ConflictException(
                    'A User with that name already exists!')
        user = User(name=request.user_name, email=request.email)
        user.put()
        return StringMessage(message='User {} created!'.format(
                request.user_name))

    @endpoints.method(request_message=NEW_GAME_REQUEST,
                      response_message=GameForm,
                      path='game',
                      name='new_game',
                      http_method='POST')
    def new_game(self, request):
        """Creates new game"""
        user = User.query(User.name == request.user_name).get()
        if not user:
            raise endpoints.NotFoundException(
                    'A User with that name does not exist!')
        try:
            game = Game.new_game(user.key, request.max, request.attempts)
        except ValueError:
            raise endpoints.BadRequestException('Maximum letter attempts '
                                                'has been exceeded!')

        # Use a task queue to update the average attempts remaining.
        # This operation is not needed to complete the creation of a new game
        # so it is performed out of sequence.
        taskqueue.add(url='/tasks/cache_attempts')
        return game.to_form('Good luck playing Hangman!')

    @endpoints.method(request_message=GET_GAME_REQUEST,
                      response_message=GameForm,
                      path='game/{urlsafe_game_key}',
                      name='get_game',
                      http_method='GET')
    def get_game(self, request):
        """Return the current game state."""
        game = get_by_urlsafe(request.urlsafe_game_key, Game)
        if game:
            return game.to_form('Make a guess!')
        else:
            raise endpoints.NotFoundException('Game not found!')

    @endpoints.method(request_message=GUESS_REQUEST,
                      response_message=GameForm,
                      path='game/{urlsafe_game_key}/letter',
                      name='guess_letter',
                      http_method='PUT')
    def guess_letter(self, request):
        """Makes a move. Returns a game state with message"""
        game = get_by_urlsafe(request.urlsafe_game_key, Game)
        if game:
            if game.game_over:
                return game.to_form('Game already over!')
        else:
            raise endpoints.NotFoundException("Game not found. Start a new game!")

        if not request.guess:
            return game.to_form("Please guess a letter.")
        if request.guess.lower() in game.past_guesses:
            return game.to_form("You already guessed that letter!")
        if len(request.guess) != 1:
            return game.to_form("You can only guess a single letter.")

        # Assess the guessed letter
        game.past_guesses.append(request.guess.lower())
        move_number = len(game.past_guesses)
        if request.guess.lower() in game.word.lower():
            guess_instances = [i for i, ltr in enumerate(game.word.lower()) if ltr == request.guess.lower()]
            for i in guess_instances:
                game.word_so_far = game.word_so_far[:i] + game.word[i] + game.word_so_far[i+1:]
                if game.word_so_far == game.word:
                    # 1 point for guessing final letter
                    message = "You won! Score is 1."
                    game.save_history(request.guess, message, move_number)
                    game.end_game(True, 1.0)
                    return game.to_form(message)
                else:
                    message = "Correct guess! Word so far: " + game.word_so_far
                    game.save_history(request.guess, message, move_number)
                    game.put()
                    return game.to_form(message)
                else:
                    game.attempts_remaining -= 1
                    if game.attempts_remaining < 1:
                        # 0 points for loss
                        message = "Game over! Score is 0. Correct word is: " + game.word
                        game.save_history(request.guess, message, move_number)
                        game.end_game(False, 0.0)
                        return game.to_form(message)
                    else:
                        message = "Incorrect guess! Word so far: " + game.word_so_far
                        game.save_history(request.guess, message, move_number)
                        game.put()
                        return game.to_form(message)

        ## check the below ##
        game.attempts_remaining -= 1
        if request.guess == game.target:
            game.end_game(True)
            return game.to_form('You win!')

        if request.guess < game.target:
            msg = 'Too low!'
        else:
            msg = 'Too high!'

        if game.attempts_remaining < 1:
            game.end_game(False)
            return game.to_form(msg + ' Game over!')
        else:
            game.put()
            return game.to_form(msg)

    @endpoints.method(request_message=GUESS_REQUEST,
                    response_message=GameForm,
                    path="game/{urlsafe_game_key}/word",
                    name="guess_word",
                    http_method="PUT")
    def guess_word(self, request):
        """Guesses the entire word. Returns game state with message."""
        game = get_by_urlsafe(request.urlsafe_game_key, Game)
        if game:
            if game.game_over:
                return game.to_form("Game is already over!")
            else:
                raise endpoints.NotFoundException("Game not found. Start a new game!")
                if request.guess.lower() in game.past_guesses:
                    return game.to_form("You already guessed that word!")

        game.past_guesses.append(request.guess.lower())
        move_number = len(game.past_guesses)
        if request.guess.lower() == game.word.lower():
            # Algorithm for calculating score:
            # round to one decimal place:
            # (blanks remaining / length of word * 10) - penalty
            # --> Correct guess up front = 10.0 pts
            # --> Correct guess w/ one letter left ~= 1.0 pt
            # penalty == incorrect word (not letter) guesses
            score = round((game.word_so_far.count('_') / len(game.word)) * 10 - game.penalty, 1)
            if score < 1.0:
                score = 1.0
                game.word_so_far = game.word
                message = "You won! Score is " + str(score) + "."
                game.save_history(request.guess, message, move_number)
                game.end_game(True, score)
                return game.to_form(message)
            game.attempts_remaining -= 1
            if game.attempts_remaining < 1:
                message = "Game over! Score is 0. Correct word is: " + game.word
                game.save_history(request.guess, message, move_number)
                game.end_game(False, 0.0)
                return game.to_form(message)
        else:
            # Assess a penalty for incorrect guess (subtracted from total score)
            game.penalty += 1.0
            message = "Incorrect guess! Penalty is " + str(game.penalty) + ". Word so far: " + game.word_so_far
            game.save_history(request.guess, message, move_number)
            game.put()
            return game.to_form(message)

##--------
    @endpoints.method(response_message=ScoreForms,
                      path='scores',
                      name='get_scores',
                      http_method='GET')
    def get_scores(self, request):
        """Return all scores"""
        return ScoreForms(items=[score.to_form() for score in Score.query()])

    @endpoints.method(request_message=USER_REQUEST,
                      response_message=ScoreForms,
                      path='scores/user/{user_name}',
                      name='get_user_scores',
                      http_method='GET')
    def get_user_scores(self, request):
        """Returns all of an individual User's scores"""
        user = User.query(User.name == request.user_name).get()
        if not user:
            raise endpoints.NotFoundException(
                    'A User with that name does not exist!')
        scores = Score.query(Score.user == user.key)
        return ScoreForms(items=[score.to_form() for score in scores])

    @endpoints.method(response_message=StringMessage,
                      path='games/average_attempts',
                      name='get_average_attempts_remaining',
                      http_method='GET')
    def get_average_attempts(self, request):
        """Get the cached average moves remaining"""
        return StringMessage(message=memcache.get(MEMCACHE_GUESSES_REMAINING) or '')

    #get_user_games
    #This returns all of a User's active games.
    #You may want to modify the User and Game models to simplify this type of query.
    #Hint: it might make sense for each game to be a descendant of a User.
    @endpoints.method(request_message=GET_GAME_REQUEST,
                      response_message=GameForms,
                      path='scores/user/{user_name}',
                      name='get_user_games',
                      http_method='GET')
    def get_user_games(self, request):
        """Returns all of an individual incomplete games"""
        user = User.query(User.name == request.user_name).get()
        if not user:
            raise endpoints.NotFoundException(
                    'A User with that name does not exist!')
        games = Game.query(ndb.AND(Game.is_active == True,
                          Game.user == user.key)).fetch()
        return GameForms(items=[game.to_form() for game in games])

    #cancel_game
    #This endpoint allows users to cancel a game in progress.
    #You could implement this by deleting the Game model itself,
    #or add a Boolean field such as 'cancelled' to the model.
    #Ensure that Users are not permitted to remove completed games.
    @endpoints.method(request_message=GET_GAME_REQUEST,
                      response_message=StringMessage,
                      path='cancel_game',
                      name='cancel_game',
                      http_method='POST')
    def cancel_game(self, request):
        """Cancel an active game"""

        game = get_by_urlsafe(request.game_key, Game)
        if not game:
            raise endpoints.ConflictException('Cannot find game with key {}'.
                                              format(request.game_key))
        if not game.is_active:
            raise endpoints.ConflictException('Game already inactive')

        game.is_active = False
        game.put()

        return StringMessage(message='Game {} cancelled'.
                             format(request.game_key))


    #get user ranking
    @endpoints.method(request_message=message_types.VoidMessage,
                      response_message=StringMessages,
                      path='get_user_rankings',
                      name='get_user_rankings',
                      http_method='POST')
    def get_user_rankings(self, request):
        """Return list of Users in descending order of score"""
        users = User.query().order(-User.score).fetch()

        return StringMessages(message=['{} (score:{})'.
                              format(user.name, user.score) for user in users])

    #get game history
    @endpoints.method(request_message=GET_GAME_REQUEST,
                      response_message=StringMessages,
                      path='get_game_history',
                      name='get_game_history',
                      http_method='GET')
    def get_game_history(self, request):
        """Return list of Game plays"""

        game = get_by_urlsafe(request.game_key, Game)
        if not game:
            raise endpoints.ConflictException('Cannot find game with key {}'.
                                              format(request.game_key))

        games = Game.query(ancestor=game.key).order(Game.start_time)

        return StringMessages(message=[
            '{},{}'.format(game.player_move, game.result) for game in games])

    @staticmethod
    def _cache_average_attempts():
        """Populates memcache with the average moves remaining of Games"""
        games = Game.query(Game.game_over == False).fetch()
        if games:
            count = len(games)
            total_attempts_remaining = sum([game.attempts_remaining
                                        for game in games])
            average = float(total_attempts_remaining)/count
            memcache.set(MEMCACHE_GUESSES_REMAINING,
                         'The average moves remaining is {:.2f}'.format(average))


api = endpoints.api_server([HangmanApi])
