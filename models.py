"""models.py - This file contains the class definitions for the Datastore
entities used by the Game. Because these classes are also regular Python
classes they can include methods (such as 'to_form' and 'new_game')."""
import random
from datetime import date
from protorpc import messages
from google.appengine.ext import ndb

""" Words to use in the hangman game. """
WORDS = ("follow", "waking", "insane", "chilly",
         "massive", "ancient", "zebra", "logical", "never", "nice")
GUESSES_ALLOWED = 7


class User(ndb.Model):
    """User profile"""
    name = ndb.StringProperty(required=True)
    email = ndb.StringProperty()
    total_score = ndb.IntegerProperty(default=0)

    def to_form(self, total_score):
        form = UserForm()
        form.user_name = self.name
        form.total_score = total_score
        return form


class Game(ndb.Model):
    """Game object"""
    user = ndb.KeyProperty(required=True, kind='User')
    target_word = ndb.StringProperty(required=True)
    word_state = ndb.StringProperty(required=True)
    attempts_remaining = ndb.IntegerProperty(required=True, default=7)
    past_guesses = ndb.StringProperty(repeated=True)
    game_over = ndb.BooleanProperty(required=True, default=False)
    attempts_allowed = ndb.IntegerProperty(required=True)

    @classmethod
    def new_game(cls, userKey):
        """Creates and returns a new game"""
        word = random.choice(WORDS)
        word_state = "_" * len(word)
        game = Game(user=userKey,
                    target_word=word,
                    attempts_allowed=GUESSES_ALLOWED,
                    attempts_remaining=GUESSES_ALLOWED,
                    word_state=word_state)

        game.put()
        return game

    def save_history(self, guess, message, order):
        """Saves the last made move to history"""
        move = History(parent=self.key,
                       guess=guess,
                       message=message,
                       order=order)
        move.put()
        return move

    def to_form(self, message):
        """Returns a GameForm representation of the Game"""
        form = GameForm()
        form.urlsafe_key = self.key.urlsafe()
        form.user_name = self.user.get().name
        form.attempts_remaining = self.attempts_remaining
        form.game_over = self.game_over
        form.word_state = self.word_state
        form.message = message
        return form

    def end_game(self, won=False, score=0):
        """Ends the game - if won is True, the player won. - if won is False,
        the player lost."""
        self.game_over = True
        self.put()
        # Add the game to the score 'board'
        score = Score(user=self.user, date=date.today(), won=won,
                      guesses=self.attempts_allowed - self.attempts_remaining,
                      points=(self.attempts_allowed - self.attempts_remaining) * 3)
        score.put()


class Score(ndb.Model):
    """Score object"""
    user = ndb.KeyProperty(required=True, kind='User')
    date = ndb.DateProperty(required=True)
    won = ndb.BooleanProperty(required=True)
    guesses = ndb.IntegerProperty(required=True)
    points = ndb.IntegerProperty(required=True)

    def to_form(self):
        return ScoreForm(user_name=self.user.get().name, won=self.won,
                         date=str(self.date), guesses=self.guesses,
                         points=self.points)

class GameForm(messages.Message):
    """GameForm for outbound game state information"""
    urlsafe_key = messages.StringField(1, required=True)
    attempts_remaining = messages.IntegerField(2, required=True)
    game_over = messages.BooleanField(3, required=True)
    message = messages.StringField(4, required=True)
    user_name = messages.StringField(5, required=True)
    word_state = messages.StringField(6, required=True)


class GameForms(messages.Message):
    """Return multiple GameForms"""
    items = messages.MessageField(GameForm, 1, repeated=True)


class NewGameForm(messages.Message):
    """Used to create a new game"""
    user_name = messages.StringField(1, required=True)


class GuessForm(messages.Message):
    """Used to make a guess in an existing game"""
    guess = messages.StringField(1, required=True)


class ScoreForm(messages.Message):
    """ScoreForm for outbound Score information"""
    user_name = messages.StringField(1, required=True)
    date = messages.StringField(2, required=True)
    won = messages.BooleanField(3, required=True)
    guesses = messages.IntegerField(4, required=True)
    points = messages.IntegerField(5, required=True)


class ScoreForms(messages.Message):
    """Return multiple ScoreForms"""
    items = messages.MessageField(ScoreForm, 1, repeated=True)


class HighScoresForm(messages.Message):
    """Return high scores, with a limit specified by the user."""
    number_of_results = messages.IntegerField(1, required=False, default=5)


class UserForm(messages.Message):
    """User Form for outbound User information"""
    user_name = messages.StringField(1, required=True)
    total_score = messages.FloatField(2, required=True)


class History(ndb.Model):
    """Object representing a past guess and result"""
    guess = ndb.StringProperty(required=True)
    message = ndb.StringProperty(required=True)
    order = ndb.IntegerProperty(required=True)

    def to_form(self):
        form = HistoryForm()
        form.guess = self.guess
        form.message = self.message
        return form


class HistoryForm(messages.Message):
    """Form for outbound History information"""
    guess = messages.StringField(1, required=True)
    message = messages.StringField(2, required=True)


class HistoryForms(messages.Message):
    """Returns multiple HistoryForms"""
    items = messages.MessageField(HistoryForm, 1, repeated=True)


class UserForms(messages.Message):
    """Container for multiple User Forms"""
    items = messages.MessageField(UserForm, 1, repeated=True)


class StringMessage(messages.Message):
    """StringMessage-- outbound (single) string message"""
    message = messages.StringField(1, required=True)
