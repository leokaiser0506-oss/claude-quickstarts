"""Command-line interface: play against the engine, or analyse a position.

Examples:
    python -m chess_ai play --color white --time 3
    python -m chess_ai analyze "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"
    python -m chess_ai analyze --pgn game.pgn --stockfish /usr/games/stockfish
"""

from __future__ import annotations

import argparse
import sys

import chess
import chess.engine
import chess.pgn

from .engine import Engine, SearchResult


def format_score(result: SearchResult, turn: chess.Color) -> str:
    """Score from White's point of view, like most chess GUIs show it."""
    mate = result.mate_in
    if mate is not None:
        mate = mate if turn == chess.WHITE else -mate
        return f"#{mate}"
    cp = result.score if turn == chess.WHITE else -result.score
    return f"{cp / 100:+.2f}"


def pv_san(board: chess.Board, pv: list[chess.Move]) -> str:
    return board.variation_san(pv) if pv else ""


class Analyzer:
    """Wraps either the built-in engine or an external UCI engine such as Stockfish."""

    def __init__(self, stockfish_path: str | None = None) -> None:
        self.engine = Engine()
        self.uci: chess.engine.SimpleEngine | None = None
        if stockfish_path:
            self.uci = chess.engine.SimpleEngine.popen_uci(stockfish_path)

    def close(self) -> None:
        if self.uci:
            self.uci.quit()

    def best(
        self, board: chess.Board, time_limit: float, verbose: bool = False
    ) -> SearchResult:
        if self.uci:
            info = self.uci.analyse(board, chess.engine.Limit(time=time_limit))
            pov = info["score"].pov(board.turn)
            mate = pov.mate()
            if mate is not None:
                score = (
                    (100_000 - (2 * mate - 1)) if mate > 0 else (-100_000 + 2 * -mate)
                )
            else:
                score = pov.score() or 0
            pv = info.get("pv", [])
            return SearchResult(
                pv[0] if pv else None,
                score,
                info.get("depth", 0),
                info.get("nodes", 0),
                time_limit,
                pv,
            )

        def report(r: SearchResult) -> None:
            if verbose:
                print(
                    f"  depth {r.depth:2d}  eval {format_score(r, board.turn):>7}  "
                    f"nodes {r.nodes:>8}  {r.elapsed:5.1f}s  {pv_san(board, r.pv)}"
                )

        return self.engine.search(board, time_limit=time_limit, on_iteration=report)


def parse_move(board: chess.Board, text: str) -> chess.Move | None:
    for parser in (board.parse_san, board.parse_uci):
        try:
            return parser(text)
        except ValueError:
            continue
    return None


def print_board(board: chess.Board, orientation: chess.Color) -> None:
    print()
    print(board.unicode(empty_square="·", orientation=orientation, borders=False))
    files = "a b c d e f g h" if orientation == chess.WHITE else "h g f e d c b a"
    print(files)
    print()


def cmd_play(args: argparse.Namespace) -> int:
    board = chess.Board(args.fen) if args.fen else chess.Board()
    human = chess.WHITE if args.color == "white" else chess.BLACK
    analyzer = Analyzer(args.stockfish)
    print("Commands: <move> (e4, Nf3, e2e4), hint, undo, fen, pgn, quit")
    try:
        while not board.is_game_over(claim_draw=True):
            print_board(board, human)
            if board.turn == human:
                text = input("Your move: ").strip()
                if text in ("quit", "exit"):
                    return 0
                if text == "fen":
                    print(board.fen())
                    continue
                if text == "pgn":
                    print(chess.pgn.Game.from_board(board))
                    continue
                if text == "undo":
                    if len(board.move_stack) >= 2:
                        board.pop()
                        board.pop()
                    continue
                if text == "hint":
                    r = analyzer.best(board, args.time)
                    print(
                        f"Hint: {board.san(r.move)}  (eval {format_score(r, board.turn)})"
                    )
                    continue
                move = parse_move(board, text)
                if move is None:
                    print("Illegal or unreadable move.")
                    continue
                board.push(move)
            else:
                print("Engine thinking...")
                r = analyzer.best(board, args.time, verbose=args.verbose)
                print(
                    f"Engine plays {board.san(r.move)}  "
                    f"(eval {format_score(r, board.turn)}, depth {r.depth})"
                )
                board.push(r.move)
        print_board(board, human)
        print("Game over:", board.result(claim_draw=True))
        return 0
    finally:
        analyzer.close()


def cmd_analyze(args: argparse.Namespace) -> int:
    analyzer = Analyzer(args.stockfish)
    try:
        if args.pgn:
            with open(args.pgn, encoding="utf-8") as f:
                game = chess.pgn.read_game(f)
            if game is None:
                print("No game found in PGN.", file=sys.stderr)
                return 1
            return _review_game(analyzer, game, args.time)

        board = chess.Board(args.fen) if args.fen else chess.Board()
        print_board(board, board.turn)
        r = analyzer.best(board, args.time, verbose=True)
        if r.move is None:
            print("No legal moves:", board.result())
            return 0
        print(f"\nBest move: {board.san(r.move)}   eval {format_score(r, board.turn)}")
        print(f"Line:      {pv_san(board, r.pv)}")
        return 0
    finally:
        analyzer.close()


def _review_game(analyzer: Analyzer, game: chess.pgn.Game, time_limit: float) -> int:
    """Flag moves that lose a lot of evaluation compared to the engine's choice."""
    board = game.board()
    for node in game.mainline():
        move = node.move
        before = analyzer.best(board, time_limit)
        san = board.san(move)
        number = f"{board.fullmove_number}{'.' if board.turn == chess.WHITE else '...'}"
        board.push(move)
        after = analyzer.best(board, time_limit)
        # Both scores from the mover's perspective.
        best_cp = _cp(before.score)
        played_cp = -_cp(after.score)
        loss = best_cp - played_cp
        tag = ""
        if before.move != move:
            if loss >= 300:
                tag = "?? blunder"
            elif loss >= 100:
                tag = "?  mistake"
            elif loss >= 50:
                tag = "?! inaccuracy"
        line = f"{number} {san:<8}"
        if tag and before.move is not None:
            prev = board.copy()
            prev.pop()
            line += f" {tag}  (best: {prev.san(before.move)}, loss {loss / 100:.2f})"
        print(line)
    print("Result:", game.headers.get("Result", "*"))
    return 0


def _cp(score: int) -> int:
    # Clamp mate scores so that "loss" stays readable.
    return max(-2000, min(2000, score))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="chess_ai", description=__doc__.splitlines()[0]
    )
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--time", type=float, default=3.0, help="seconds per move (default 3)"
    )
    common.add_argument(
        "--stockfish",
        metavar="PATH",
        help="use an external UCI engine (e.g. Stockfish) instead",
    )

    p_play = sub.add_parser(
        "play", parents=[common], help="play a game against the engine"
    )
    p_play.add_argument("--color", choices=["white", "black"], default="white")
    p_play.add_argument("--fen", help="start from this position")
    p_play.add_argument(
        "-v", "--verbose", action="store_true", help="show search progress"
    )
    p_play.set_defaults(func=cmd_play)

    p_an = sub.add_parser(
        "analyze", parents=[common], help="best move for a FEN, or review a PGN"
    )
    p_an.add_argument(
        "fen", nargs="?", help="FEN of the position (default: start position)"
    )
    p_an.add_argument(
        "--pgn", help="review every move of the first game in this PGN file"
    )
    p_an.set_defaults(func=cmd_analyze)

    args = parser.parse_args(argv)
    return args.func(args)
