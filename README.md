#Full Stack Nanodegree Project 4

## Set-Up Instructions:
1.  Update the value of application in app.yaml to the app ID you have registered
 in the App Engine admin console and would like to use to host your instance of this sample.
1.  Run the app with the devserver using dev_appserver.py DIR, and ensure it's
 running by visiting the API Explorer - by default localhost:8080/_ah/api/explorer.
1.  (Optional) Generate your client library(ies) with the endpoints tool.
 Deploy your application.



##Game Description:
Hangman is a simple guessing game. Each game begins with a randomly selected
word from a predefined list of words.  The user attempts to guess the word
one letter at a time.  If the guessed is a letter that is in the target word,
the user proceeds and guesses another, if it is not start drawing a hangman.
A total of 7 wrong attempts is allowed.  The score after each is stored as the
number of remaining attempts multiplied by 3.

Each game can be retrieved or played by using the path parameter
`urlsafe_game_key`.

##Files Included:
 - api.py: Contains endpoints and game playing logic.
 - app.yaml: App configuration.
 - cron.yaml: Cronjob configuration.
 - main.py: Handler for taskqueue handler.
 - models.py: Entity and message definitions including helper methods.
 - utils.py: Helper function for retrieving ndb.Models by urlsafe Key string.

##Endpoints Included:
 - **create_user**
    - Path: 'user'
    - Method: POST
    - Parameters: user_name, email (optional)
    - Returns: Message confirming creation of the User.
    - Description: Creates a new User. user_name provided must be unique. Will
    raise a ConflictException if a User with that user_name already exists.

  - **new_game**
    - Path: 'game'
    - Method: POST
    - Parameters: user_name, max, attempts
    - Returns: GameForm with initial game state.
    - Description: Creates a new Game. user_name provided must correspond to an
    existing user - will raise a NotFoundException if not. Maximum guess attempts
    should not be exceeded. Also adds a task to a task queue to update the
    moves remaining for active games.

 - **get_game**
    - Path: 'game/{urlsafe_game_key}'
    - Method: GET
    - Parameters: urlsafe_game_key
    - Returns: GameForm with current game state.
    - Description: Returns the current state of a game.

 - **make_guess**
    - Path: 'game/{urlsafe_game_key}'
    - Method: PUT
    - Parameters: urlsafe_game_key, guess
    - Returns: GameForm with new game state.
    - Description: Accepts a 'guess' and returns the updated state of the game.
    If this causes a game to end, a corresponding Score entity will be created.

 - **get_scores**
    - Path: 'scores'
    - Method: GET
    - Parameters: None
    - Returns: ScoreForms.
    - Description: Returns all Scores in the database (unordered).

 - **get_user_scores**
    - Path: 'scores/user/{user_name}'
    - Method: GET
    - Parameters: user_name
    - Returns: ScoreForms.
    - Description: Returns all Scores recorded by the provided player (unordered).
    Will raise a NotFoundException if the User does not exist.

 - **get_high_scores**
    - Path: 'high_scores'
    - Method: GET
    - Parameters: None
    - Returns: ScoreForms
    - Description: Returns an ordered list of the highest scoring games.

- **get_attempts_remaining**
    - Path: 'games/attempts_remaining'
    - Method: GET
    - Parameters: None
    - Returns: StringMessage
    - Description: Returns the cached number of moves remaining.

- **get_user_games**
    - Path: 'game/games'
    - Method: GET
    - Parameters: user_name
    - Returns: GameForms with game states for given username.
    - Description: Returns all of an individual incomplete games.

- **cancel_game**
    - Path: 'game/{urlsafe_game_key}'
    - Method: DELETE
    - Parameters: urlsafe_game_key
    - Returns: StringMessage informing the user whether a game has been canceled
    - Description: Allows users to cancel a game in progress.

- **get_user_rankings**
       - Path: 'user/ranking'
       - Method: GET
       - Parameters: None
       - Returns: UserForms
       - Description: Returns a list of Users in descending order of score.

- **get_game_history**
              - Path: 'game/{urlsafe_game_key}/history''
              - Method: GET
              - Parameters: urlsafe_game_key
              - Returns: UserForms
              - Description: Return a string message containing the past guesses
              for a given game.



##Models Included:
 - **User**
    - Stores unique user_name and email address.

 - **Game**
    - Stores unique game states. Associated with User model via KeyProperty.

 - **Score**
    - Records completed games. Associated with Users model via KeyProperty.

##Forms Included:
 - **GameForm**
    - Representation of a Game's state (urlsafe_key, attempts_remaining,
    game_over flag, message, user_name).
-  **GameForms**
    - Multiple game forms  
- **NewGameForm**
    - Used to create a new game (user_name, max, attempts)
- **GuessForm**
    - Used to make a guess in an existing game.
- **ScoreForm**
    - Representation of a completed game's Score (user_name, date, won flag,
    guesses).
- **ScoreForms**
    - Multiple ScoreForm container.
- **HighScoresForm**
    - Multiple ScoreForm container, showing highest scores with a limit set by user.
- **UserForm**
    - User Form for outbound User information (name, email, wins, total_played,
      winning percentage )
- **UserForms**
    - Multiple user forms  
 - **StringMessage**
    - General purpose String container.
