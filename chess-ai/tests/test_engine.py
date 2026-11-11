import chess

from chess_ai import Engine, evaluate


def test_start_position_is_roughly_equal():
    assert abs(evaluate(chess.Board())) < 50


def test_returns_legal_move():
    board = chess.Board()
    result = Engine().search(board, time_limit=0.5)
    assert result.move in board.legal_moves


def test_finds_mate_in_one():
    # Scholar's mate: Qxf7#
    board = chess.Board(
        "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"
    )
    result = Engine().search(board, time_limit=2.0)
    assert board.san(result.move) == "Qxf7#"
    assert result.mate_in == 1


def test_finds_mate_in_two():
    # Rook ladder: 1. Ra7 Kg8 2. Rb8#
    board = chess.Board("7k/8/8/8/8/8/8/RR4K1 w - - 0 1")
    result = Engine().search(board, time_limit=5.0)
    assert result.mate_in == 2, result


def test_takes_hanging_queen():
    board = chess.Board("rnb1kbnr/pppp1ppp/8/8/3q4/5N2/PPPPPPPP/RNBQKB1R w KQkq - 0 1")
    result = Engine().search(board, time_limit=1.0)
    assert board.san(result.move) == "Nxd4"


def test_no_moves_when_checkmated():
    board = chess.Board("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3")
    result = Engine().search(board, time_limit=0.5)
    assert result.move is None
