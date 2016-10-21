# -*- coding: utf-8 -*-`
"""api.py - Create and configure the Game API exposing the resources.
api.py also contains the hangman game logic. For more complex games it would be wise to
move game logic to another file. Ideally the API will be simple, concerned
primarily with communication to/from the API's users."""

import endpoints
from protorpc import remote, messages
from google.appengine.api import memcache
from google.appengine.api import taskqueue

from models import User, Game, Score
from models import StringMessage, NewGameForm, GameForm, GuessForm,\
    ScoreForms, ScoreForm, GameForms, UserForm, UserForms, HighScoresForm,\
    HistoryForms, History
from utils import get_by_urlsafe

NEW_GAME_REQUEST = endpoints.ResourceContainer(NewGameForm)
GET_GAME_REQUEST = endpoints.ResourceContainer(
    urlsafe_game_key=messages.StringField(1))
GUESS_REQUEST = endpoints.ResourceContainer(
    GuessForm, urlsafe_game_key=messages.StringField(1))
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
                      path="game",
                      name="new_game",
                      http_method="POST")
    def new_game(self, request):
        """Creates new game"""
        user = User.query(User.name == request.user_name).get()
        if not user:
            raise endpoints.NotFoundException(
                'A user with that name does not exist!')
        game = Game.new_game(user.key)
        # Task queue updates average attempts remaining.
        taskqueue.add(url='/tasks/cache_attempts')
        return game.to_form("A New Hangman Game Has Been Created!")

    @endpoints.method(request_message=GUESS_REQUEST,
                      response_message=GameForm,
                      path="game/{urlsafe_game_key}/letter",
                      name="make_guess",
                      http_method="PUT")
    def make_guess(self, request):
        """Makes a move. Returns a game state with message"""
        game = get_by_urlsafe(request.urlsafe_game_key, Game)
        if game:
            if game.game_over:
                return game.to_form("Game is already over!")
            if not request.guess:
                return game.to_form("Please guess a letter.")
            if request.guess.lower() in game.past_guesses:
                return game.to_form("You already guessed that letter!")
            if len(request.guess) != 1:
                return game.to_form("You can only guess a single letter.")
            # Assess the guessed letter
            game.past_guesses.append(request.guess.lower())
            move_number = len(game.past_guesses)
            if request.guess.lower() in game.target_word.lower():
                guess_instances = [i for i, ltr in enumerate(
                    game.target_word.lower()) if ltr == request.guess.lower()]
                for i in guess_instances:
                    game.word_state = game.word_state[
                        :i] + game.target_word[i] + game.word_state[i + 1:]
                if game.word_state == game.target_word:
                    # 1 point for guessing final letter
                    message = "You won! Score is 1."
                    game.save_history(request.guess, message, move_number)
                    game.end_game(True, 1)
                    return game.to_form(message)
                else:
                    message = "Correct guess! Word so far: " + game.word_state
                    game.save_history(request.guess, message, move_number)
                    game.put()
                    return game.to_form(message)
            else:
                game.attempts_remaining -= 1
                if game.attempts_remaining < 1:
                    # 0 points for loss
                    message = "Game over! Score is 0. Correct word is: " + game.target_word
                    game.save_history(request.guess, message, move_number)
                    game.end_game(False, 0)
                    return game.to_form(message)
                else:
                    message = "Incorrect guess! Word so far: " + game.word_state
                    game.save_history(request.guess, message, move_number)
                    game.put()
                    return game.to_form(message)

    @endpoints.method(request_message=GET_GAME_REQUEST,
                      response_message=GameForm,
                      path="game/{urlsafe_game_key}",
                      name="get_game",
                      http_method="GET")
    def get_game(self, request):
        """Return the current game state."""
        game = get_by_urlsafe(request.urlsafe_game_key, Game)
        if game:
            return game.to_form("Make a guess!")
        else:
            raise endpoints.NotFoundException("Game not found!")

    @endpoints.method(response_message=ScoreForms,
                      path='scores',
                      name='get_scores',
                      http_method='GET')
    def get_scores(self, request):
        """Return all scores (unordered)"""
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

    @endpoints.method(request_message=HighScoresForm,
                      response_message=ScoreForms,
                      path='high_scores',
                      name='get_high_scores',
                      http_method='GET')
    def get_high_scores(self, request):
        """Returns a list of the highest scoring games."""
        scores = Score.query().order(-Score.points).fetch(limit=request.number_of_results)
        return ScoreForms(items=[score.to_form() for score in scores])

    @endpoints.method(response_message=StringMessage,
                      path='games/attempts_remaining',
                      name='get_attempts_remaining',
                      http_method='GET')
    def get_attempts_remaining(self, request):
        """Get the cached number of moves remaining"""
        return StringMessage(message=memcache.get(MEMCACHE_GUESSES_REMAINING) or '')

    # get_user_games
    # This returns all of a User's active games.
    # You may want to modify the User and Game models to simplify this type of query.
    # Hint: it might make sense for each game to be a descendant of a User.
    @endpoints.method(request_message=USER_REQUEST,
                      response_message=GameForms,
                      path="user/games/{user_name}",
                      name="get_user_games",
                      http_method="GET")
    def get_user_games(self, request):
        """Returns all games for user"""
        user = User.query(User.name == request.user_name).get()
        if not user:
            raise endpoints.NotFoundException(
                'A User with that name does not exist!')
        games = Game.query(Game.user == user.key).fetch()
        return GameForms(items=[game.to_form("") for game in games])

    # cancel_game
    # This endpoint allows users to cancel a game in progress.
    # You could implement this by deleting the Game model itself,
    # or add a Boolean field such as 'cancelled' to the model.
    # Ensure that Users are not permitted to remove completed games.
    @endpoints.method(request_message=GET_GAME_REQUEST,
                      response_message=StringMessage,
                      path='game/{urlsafe_game_key}',
                      name='cancel_game',
                      http_method='DELETE')
    def cancel_game(self, request):
        """Cancel an active game"""

        game = get_by_urlsafe(request.urlsafe_game_key, Game)
        if game and not game.game_over:
            game.key.delete()
            return StringMessage(message='Game with key: {} deleted.'.
                                 format(request.urlsafe_game_key))
        elif game and game.game_over:
            raise endpoints.BadRequestException('Game is already over!')
        else:
            raise endpoints.NotFoundException('Game not found!')

    # get user ranking
    @endpoints.method(response_message=UserForms,
                      path='user/ranking',
                      name='get_user_rankings',
                      http_method='GET')
    def get_user_rankings(self, request):
        """Return list of users ranked in descending order of total score"""
        rankings = []
        users = User.query().fetch()
        for user in users:
            user_score = Score.query(Score.user==user.key).order(-Score.points).fetch()
            total_score = sum([score.points for score in user_score])
            rankings.append((user,total_score))
        rankings.sort(key=lambda tup: tup[1], reverse=True)
        return UserForms(items=[result[0].to_form(result[1]) for result in rankings])

    # get game history
    @endpoints.method(request_message=GET_GAME_REQUEST,
                      response_message=HistoryForms,
                      path='game/{urlsafe_game_key}/history',
                      name='get_game_history',
                      http_method='GET')
    def get_game_history(self, request):
        """Returns a history of all guesses made in game."""
        game = get_by_urlsafe(request.urlsafe_game_key, Game)
        if not game:
            raise endpoints.ConflictException('Cannot find game with key {}'.
                                              format(request.urlsafe_game_key))
        else:
            history = History.query(ancestor=game.key).order(History.order)
            return HistoryForms(items=[guess.to_form() for guess in history])

    @staticmethod
    def _cache_attempts():
        """Populates memcache with the remaining number of Guesses for all
        incomplete games."""
        games = Game.query(Game.game_over == False).fetch()
        if games:
            count = len(games)
            total_attempts_remaining = sum([game.attempts_remaining
                                            for game in games])
            memcache.set(MEMCACHE_GUESSES_REMAINING,
                         'The number of remaining guesses is {}'.format(total_attempts_remaining))

api = endpoints.api_server([HangmanApi])
