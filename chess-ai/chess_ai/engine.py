"""Alpha-beta chess engine built on python-chess.

Features: iterative deepening, negamax with alpha-beta, transposition table,
null-move pruning, check extension, quiescence search, and move ordering
(TT move, MVV-LVA captures, killer moves, history heuristic).

Pure Python: it reaches roughly depth 4-6 in a few seconds. That is enough to beat
beginners and punish blunders, but it is far weaker than Stockfish.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import chess

from .evaluation import PIECE_VALUES, evaluate

MATE_SCORE = 100_000
MATE_THRESHOLD = MATE_SCORE - 1_000
INF = 1_000_000

EXACT, LOWER, UPPER = 0, 1, 2
MAX_PLY = 128


class _Timeout(Exception):
    pass


@dataclass
class SearchResult:
    move: chess.Move | None
    score: int  # centipawns from the side to move's perspective
    depth: int
    nodes: int
    elapsed: float
    pv: list[chess.Move] = field(default_factory=list)

    @property
    def mate_in(self) -> int | None:
        """Moves until mate (positive: side to move mates, negative: gets mated)."""
        if abs(self.score) < MATE_THRESHOLD:
            return None
        plies = MATE_SCORE - abs(self.score)
        moves = (plies + 1) // 2
        return moves if self.score > 0 else -moves


def _score_to_tt(score: int, ply: int) -> int:
    if score > MATE_THRESHOLD:
        return score + ply
    if score < -MATE_THRESHOLD:
        return score - ply
    return score


def _score_from_tt(score: int, ply: int) -> int:
    if score > MATE_THRESHOLD:
        return score - ply
    if score < -MATE_THRESHOLD:
        return score + ply
    return score


def _has_non_pawn_material(board: chess.Board) -> bool:
    side = board.occupied_co[board.turn]
    return bool(side & ~(board.pawns | board.kings))


def _victim_value(board: chess.Board, move: chess.Move) -> int:
    if board.is_en_passant(move):
        return PIECE_VALUES[chess.PAWN]
    piece_type = board.piece_type_at(move.to_square)
    return PIECE_VALUES[piece_type] if piece_type else 0


class Engine:
    def __init__(self, tt_size: int = 1_000_000) -> None:
        self.tt_size = tt_size
        self.tt: dict[object, tuple[int, int, int, chess.Move | None]] = {}
        self.nodes = 0
        self._deadline = 0.0
        self._killers: list[list[chess.Move | None]] = []
        self._history: dict[tuple[bool, int, int], int] = {}

    def new_game(self) -> None:
        self.tt.clear()
        self._history.clear()

    def search(
        self,
        board: chess.Board,
        time_limit: float = 3.0,
        max_depth: int = 64,
        on_iteration=None,
    ) -> SearchResult:
        """Find the best move for the side to move within `time_limit` seconds."""
        board = board.copy()
        start = time.perf_counter()
        self._deadline = start + time_limit
        self.nodes = 0
        self._killers = [[None, None] for _ in range(MAX_PLY)]
        if len(self.tt) > self.tt_size:
            self.tt.clear()

        legal = list(board.legal_moves)
        if not legal:
            score = -MATE_SCORE if board.is_check() else 0
            return SearchResult(None, score, 0, 0, 0.0)

        result = SearchResult(legal[0], 0, 0, 0, 0.0)
        for depth in range(1, max_depth + 1):
            try:
                score = self._negamax(board, depth, -INF, INF, 0)
            except _Timeout:
                break
            pv = self._extract_pv(board, depth)
            if not pv:
                break
            result = SearchResult(
                pv[0], score, depth, self.nodes, time.perf_counter() - start, pv
            )
            if on_iteration:
                on_iteration(result)
            if abs(score) >= MATE_THRESHOLD and MATE_SCORE - abs(score) <= depth:
                break  # found a forced mate that the full-width search proves
            if len(legal) == 1:
                break
        result.nodes = self.nodes
        result.elapsed = time.perf_counter() - start
        return result

    # ------------------------------------------------------------------ search

    def _check_time(self) -> None:
        self.nodes += 1
        if (self.nodes & 1023) == 0 and time.perf_counter() > self._deadline:
            raise _Timeout

    def _negamax(
        self, board: chess.Board, depth: int, alpha: int, beta: int, ply: int
    ) -> int:
        self._check_time()

        if ply > 0:
            if (
                board.halfmove_clock >= 100
                or board.is_insufficient_material()
                or board.is_repetition(2)
            ):
                return 0
            # Mate-distance pruning
            alpha = max(alpha, -MATE_SCORE + ply)
            beta = min(beta, MATE_SCORE - ply)
            if alpha >= beta:
                return alpha

        in_check = board.is_check()
        if in_check:
            depth += 1
        if depth <= 0 or ply >= MAX_PLY - 1:
            return self._quiesce(board, alpha, beta, ply)

        key = board._transposition_key()
        alpha_orig = alpha
        tt_move = None
        entry = self.tt.get(key)
        if entry is not None:
            e_depth, e_score, e_flag, tt_move = entry
            if ply > 0 and e_depth >= depth:
                s = _score_from_tt(e_score, ply)
                if e_flag == EXACT:
                    return s
                if e_flag == LOWER and s >= beta:
                    return s
                if e_flag == UPPER and s <= alpha:
                    return s

        # Null-move pruning: if passing still beats beta, this node is too good.
        if (
            ply > 0
            and not in_check
            and depth >= 3
            and beta < MATE_THRESHOLD
            and _has_non_pawn_material(board)
        ):
            board.push(chess.Move.null())
            score = -self._negamax(board, depth - 3, -beta, -beta + 1, ply + 1)
            board.pop()
            if score >= beta:
                return beta

        moves = self._order_moves(board, list(board.legal_moves), tt_move, ply)
        if not moves:
            return -MATE_SCORE + ply if in_check else 0

        best_score = -INF
        best_move = moves[0]
        for i, move in enumerate(moves):
            is_quiet = not board.is_capture(move) and move.promotion is None
            board.push(move)
            gives_check = board.is_check()
            if i == 0:
                score = -self._negamax(board, depth - 1, -beta, -alpha, ply + 1)
            else:
                # Late-move reduction for quiet moves, then principal variation search.
                reduction = (
                    1
                    if (
                        i >= 4
                        and depth >= 3
                        and is_quiet
                        and not in_check
                        and not gives_check
                    )
                    else 0
                )
                score = -self._negamax(
                    board, depth - 1 - reduction, -alpha - 1, -alpha, ply + 1
                )
                if alpha < score < beta or (reduction and score > alpha):
                    score = -self._negamax(board, depth - 1, -beta, -alpha, ply + 1)
            board.pop()

            if score > best_score:
                best_score = score
                best_move = move
            alpha = max(alpha, score)
            if alpha >= beta:
                if is_quiet:
                    killers = self._killers[ply]
                    if killers[0] != move:
                        killers[1] = killers[0]
                        killers[0] = move
                    hkey = (board.turn, move.from_square, move.to_square)
                    self._history[hkey] = self._history.get(hkey, 0) + depth * depth
                break

        if best_score <= alpha_orig:
            flag = UPPER
        elif best_score >= beta:
            flag = LOWER
        else:
            flag = EXACT
        self.tt[key] = (depth, _score_to_tt(best_score, ply), flag, best_move)
        return best_score

    def _quiesce(self, board: chess.Board, alpha: int, beta: int, ply: int) -> int:
        self._check_time()

        if board.is_check():
            # In check, standing pat is illegal: search all evasions.
            moves = list(board.legal_moves)
            if not moves:
                return -MATE_SCORE + ply
            moves = self._order_moves(board, moves, None, min(ply, MAX_PLY - 1))
            best = -INF
        else:
            stand_pat = evaluate(board)
            if stand_pat >= beta or ply >= MAX_PLY - 1:
                return stand_pat
            alpha = max(alpha, stand_pat)
            best = stand_pat
            moves = self._order_moves(
                board, list(board.generate_legal_captures()), None, None
            )

        for move in moves:
            board.push(move)
            score = -self._quiesce(board, -beta, -alpha, ply + 1)
            board.pop()
            best = max(best, score)
            if score >= beta:
                return score
            alpha = max(alpha, score)
        return best

    # ---------------------------------------------------------------- helpers

    def _order_moves(
        self,
        board: chess.Board,
        moves: list[chess.Move],
        tt_move: chess.Move | None,
        ply: int | None,
    ) -> list[chess.Move]:
        killers = (
            self._killers[ply]
            if ply is not None and ply < len(self._killers)
            else (None, None)
        )
        turn = board.turn

        def score(move: chess.Move) -> int:
            if move == tt_move:
                return 10_000_000
            s = 0
            if move.promotion:
                s += 900_000 + PIECE_VALUES[move.promotion]
            if board.is_capture(move):
                attacker = board.piece_type_at(move.from_square) or chess.PAWN
                s += (
                    1_000_000
                    + 10 * _victim_value(board, move)
                    - PIECE_VALUES[attacker] // 10
                )
            elif move == killers[0]:
                s += 800_000
            elif move == killers[1]:
                s += 700_000
            else:
                s += self._history.get((turn, move.from_square, move.to_square), 0)
            return s

        moves.sort(key=score, reverse=True)
        return moves

    def _extract_pv(self, board: chess.Board, depth: int) -> list[chess.Move]:
        pv: list[chess.Move] = []
        b = board.copy(stack=False)
        seen = set()
        for _ in range(depth + 8):
            key = b._transposition_key()
            if key in seen:
                break
            seen.add(key)
            entry = self.tt.get(key)
            if entry is None or entry[3] is None or not b.is_legal(entry[3]):
                break
            pv.append(entry[3])
            b.push(entry[3])
        return pv
