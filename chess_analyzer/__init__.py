from os import environ
from flask import (
    Flask,
    render_template,
    request,
    current_app,
    Response,
    session,
    redirect,
    url_for,
)
from flask_session import Session
import chess
import chess.svg
import chess.pgn
import chess.engine
import logging
from flask_sqlalchemy import SQLAlchemy
from uuid import uuid4
from . import logger
from . import auth
import io
import json

db = SQLAlchemy()


# TODO: maybe this is just worse than a config file?
def load_config(app: Flask):
    config_vars = [
        "FLASK_APP",
        "HAS_AUTH",
        "HAS_DATABASE",
        "APP_VERSION",
        "FLASK_ENV",
    ]

    if environ.get("HAS_AUTH") is not None and environ["HAS_AUTH"] == "true":
        config_vars.extend(
            [
                "CLERK_FRONTEND_KEY",
                "CLERK_BACKEND_KEY",
            ]
        )

    # TODO: this is a bit of a hack, but it works for now
    if environ.get("HAS_DATABASE") is not None and environ["HAS_DATABASE"] == "true":
        config_vars.extend(
            ["SQLALCHEMY_DATABASE_URI", "SQLALCHEMY_TRACK_MODIFICATIONS"]
        )

    for var in config_vars:
        if environ.get(var) is None:
            raise Exception(f"{var} must be provided")
        app.config[var] = environ[var]

    # TODO: move this to a config file
    app.config["SESSION_TYPE"] = "sqlalchemy"
    app.config["SESSION_SQLALCHEMY"] = db
    app.config["SESSION_SQLALCHEMY_TABLE"] = "sessions"


def board_svg(game: chess.pgn.Game, move: int) -> str:
    board = chess.Board()
    i = 0
    for m in game.mainline_moves():
        i += 1
        if i > move:
            break
        board.push(m)

    return chess.svg.board(board=board)


def create_app():
    # setup logging
    logger.setup_logging()

    app = Flask(__name__)
    load_config(app)

    # setup FLASK_ENV defaults
    if app.config["FLASK_ENV"] == "development":
        app.config["DEBUG"] = True
        app.config["TEMPLATES_AUTO_RELOAD"] = True
        app.logger.setLevel(logging.DEBUG)
    else:
        app.logger.setLevel(logging.INFO)

    # setup database
    if app.config["HAS_DATABASE"] == "true":
        db.init_app(app)
        from .models import games_table

    # setup session middleware
    Session(app)

    @app.before_request
    def log_before_request():
        # add a unique id to the request
        request.id = str(uuid4())
        current_app.logger.info(f"request [{request.method} {request.full_path}]")

    @app.after_request
    def log_after_request(response: Response):
        current_app.logger.info(
            f"response [{request.method} {request.full_path} {response.status_code}]"
        )
        return response

    @app.route("/")
    def index():
        # get the games from the database
        result = db.session.execute(games_table.select())

        # TODO: cache this
        games = []
        for row in result.all():
            games.append({"id": row.id, "name": row.name})

        pgn = session.get("pgn")

        if pgn is None:
            return render_template("index.html", games=games, current_game=-1)

        pgn_io = io.StringIO(pgn)

        game = chess.pgn.read_game(pgn_io)

        if game is None:
            return render_template("error.html", error="invalid PGN provided"), 400

        current_move = session.get("current_move")

        if current_move is None:
            return render_template("error.html", error="no current move"), 400

        game_id = session.get("game_id")

        if game_id is None:
            return render_template("error.html", error="no game id"), 400

        # get the current games metadata
        result = db.session.execute(
            games_table.select().where(games_table.c.id == game_id)
        )

        row = result.first()

        if row is None:
            return render_template("error.html", error="game not found"), 404

        game_metadata = json.loads(row.metadata)

        moves = []
        for move in game_metadata["moves"]:
            moves.append(move["move"])

        return render_template(
            "index.html",
            svg=board_svg(game, current_move),
            games=games,
            current_game=session.get("game_id"),
            moves=moves,
            current_move=current_move,
        )

    @app.route("/pgn/create", methods=["GET"])
    def create_pgn_form():
        # just used for htmx to select the form
        return render_template("index.html")

    @app.post("/pgn/create")
    def create_pgn():
        pgn = request.form.get("PGN")

        if pgn is None:
            return render_template("error.html", error="no PGN provided"), 400

        pgn_io = io.StringIO(pgn)
        game = chess.pgn.read_game(pgn_io)

        if game is None:
            return render_template("error.html", error="invalid PGN provided"), 400

        # TODO: move this to a config file and cache it
        engine = chess.engine.SimpleEngine.popen_uci(
            "/home/jscott/stockfish/stockfish-ubuntu-x86-64-avx2"
        )

        # TODO: move this to a background task
        # analyze the game
        board = chess.Board()
        metadata = {}
        metadata["moves"] = []
        previous_evaluation = 0
        game_name = ""
        for move in game.mainline_moves():
            if len(game_name) < 10:
                game_name += board.san(move)
            analysis = engine.analyse(board, chess.engine.Limit(depth=10))
            evaluation = analysis["score"].white().wdl().expectation()
            metadata["moves"].append(
                {
                    "move": board.san(move),
                    "evaluation_diff": evaluation - previous_evaluation,
                }
            )
            previous_evaluation = evaluation
            board.push(move)

        engine.quit()

        try:
            # save the game to the database
            create_game_statement = games_table.insert().values(
                name=game_name, pgn=pgn, metadata=json.dumps(metadata)
            )
            result = db.session.execute(create_game_statement)
            db.session.commit()
        except Exception as e:
            current_app.logger.error(e)
            return render_template("error.html", error="failed to create game"), 500

        session["pgn"] = pgn
        session["current_move"] = 0
        session["game_id"] = result.lastrowid

        # TODO: make less expensive to render
        return redirect(url_for("index"))

    @app.route("/move/forward", methods=["POST"])
    def move_forward():
        pgn = session.get("pgn")

        if pgn is None:
            return render_template("error.html", error="no PGN provided"), 400

        pgn_io = io.StringIO(pgn)
        game = chess.pgn.read_game(pgn_io)
        current_app.logger.info(f"pgn: {pgn}")
        current_app.logger.info(f"game: {game}")

        if game is None:
            return render_template("error.html", error="invalid PGN provided"), 400

        current_move = session.get("current_move")

        if current_move is None:
            return render_template("error.html", error="no current move"), 400

        current_move += 1
        session["current_move"] = current_move

        # TODO: make less expensive to render
        return redirect(url_for("index"))

    @app.route("/move/backward", methods=["POST"])
    def move_backward():
        pgn = session.get("pgn")

        if pgn is None:
            return render_template("error.html", error="no PGN provided"), 400

        pgn_io = io.StringIO(pgn)
        game = chess.pgn.read_game(pgn_io)

        if game is None:
            return render_template("error.html", error="invalid PGN provided"), 400

        current_move = session.get("current_move")

        if current_move is None:
            return render_template("error.html", error="no current move"), 400

        current_move -= 1
        session["current_move"] = current_move

        # TODO: make less expensive to render
        return redirect(url_for("index"))

    @app.route("/game/<int:game_id>", methods=["GET"])
    def game(game_id: int):
        result = db.session.execute(
            games_table.select().where(games_table.c.id == game_id)
        )

        row = result.first()

        if row is None:
            return render_template("error.html", error="game not found"), 404

        session["pgn"] = row.pgn
        session["current_move"] = 0
        session["game_id"] = row.id

        pgn_io = io.StringIO(row.pgn)
        game = chess.pgn.read_game(pgn_io)

        if game is None:
            return render_template("error.html", error="invalid PGN provided"), 400

        # TODO: make less expensive to render
        return redirect(url_for("index"))

    @app.route("/error")
    def trigger_error():
        return render_template("error.html", error="you triggered an error"), 500

    @app.route("/health", methods=["GET"])
    def health():
        return "OK"

    @app.cli.command("create_database")
    def create_database():
        if app.config["HAS_DATABASE"] == "true":
            db.create_all()

    return app
