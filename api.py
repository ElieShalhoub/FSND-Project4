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
    ScoreForms, ScoreForm, GameForms, UserForm, UserForms, HighScoresForm
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
            raise endpoints.ConflictException('A User with that name already exists!')
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

    #--- Add  main end point ---#
    @endpoints.method(request_message=GUESS_REQUEST,
                      response_message=GameForm,
                      path='game/{urlsafe_game_key}',
                      name='make_guess',
                      http_method='PUT')
    def make_guess(self, request):
        """Makes a move. Returns a game state with message"""
        game = get_by_urlsafe(request.urlsafe_game_key, Game)
        if not game:
            raise endpoints.NotFoundException('Game not found!')
        if game.game_over:
            raise endpoints.NotFoundException('Game already over!')

        # Get user name
        user = User.query(User.name == request.user_name).get()

        # Check user is valid
        if not user:
            raise endpoints.NotFoundException('User not found!')
        # Verify user has moves left

        if len(list(request.guess)) > 1:
            raise endpoints.BadRequestException('You can only enter 1 character!')

        # Verify in history that guess has not been guessed before
#        for (usr , gss, opt) in game.history:
#            if gss == request.guess:
#                raise endpoints.BadRequestException('You already guessed that letter!')

        # Get guess and place it in game.target_word if correct
        word_guess = ''
        for num in range(0, len(game.target_word)):
            if request.guess in str(game.target_word[num]):
                word_guess = replaceCharacterAtIndexInString(word_guess,num,request.guess)
                message = "You Guessed Right!"
                # If incorrect down one counter on attempts_remaining
            elif request.guess not in str(game.target_word):
                if game.attempts_remaining == 1:
                    game.attempts_remaining -= 1
                    message = "You are hanged! Game Over!"
                else:
                    game.attempts_remaining -= 1
                    message = "Wrong Guess!"

        if word_guess == game.target_word:
            game.end_game(user.key)
            game.message = "User {} wins".format(request.user_name)
            #game.history.append(game.message)
            return game.to_form()

        game.put()

        taskqueue.add(url='/tasks/cache_attempts')
        return game.to_form()

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
            raise endpoints.NotFoundException('A User with that name does not exist!')
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
        """Get the cached average moves remaining"""
        return StringMessage(message=memcache.get(MEMCACHE_GUESSES_REMAINING) or '')

    #get_user_games
    #This returns all of a User's active games.
    #You may want to modify the User and Game models to simplify this type of query.
    #Hint: it might make sense for each game to be a descendant of a User.
    @endpoints.method(request_message=USER_REQUEST,
                      response_message=GameForms,
                      path='user/games',
                      name='get_user_games',
                      http_method='GET')
    def get_user_games(self, request):
        """Returns all of an individual incomplete games"""
        user = User.query(User.name == request.user_name).get()
        if not user:
            raise endpoints.NotFoundException('A User with that name does not exist!')
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

    #get user ranking
    @endpoints.method(response_message=UserForms,
                      path='user/ranking',
                      name='get_user_rankings',
                      http_method='GET')
    def get_user_rankings(self, request):
        """Return list of Users in descending order of score"""
        users = User.query().order(-User.score).fetch()
        return UserForms(items=[user.to_form() for user in users])

    #get game history
    @endpoints.method(request_message=GET_GAME_REQUEST,
                      response_message=StringMessage,
                      path='game/{urlsafe_game_key}/history',
                      name='get_game_history',
                      http_method='GET')
    def get_game_history(self, request):
        """Return list of Game plays"""

        game = get_by_urlsafe(request.game_key, Game)
        if not game:
            raise endpoints.ConflictException('Cannot find game with key {}'.
                                              format(request.game_key))
        games = Game.query(ancestor=game.key).order(Game.start_time)
        return StringMessage(message=[
            '{},{}'.format(game.player_move, game.result) for game in games])

    @staticmethod
    def _cache_attempts():
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
