import collections
from collections.abc import Iterable

import bitboards as bb
from bitboards import Bitboard, ChessBitboards
from square import Square
import piece as pce

Move = collections.namedtuple("Move",
                              ["to", "frm"])


def make_move(bitboards: ChessBitboards, move: Move) -> ChessBitboards:
    """Clear move.frm and set move.to in the same bitboard. Clear move.to"""

    def f(current_bb: Bitboard, frm_bb: Bitboard, to_bb: Bitboard):
        if current_bb & frm_bb:
            return (current_bb ^ frm_bb) | to_bb
        elif current_bb & to_bb:
            return current_bb ^ to_bb
        else:
            return current_bb

    return ChessBitboards(*[f(current_bb, Bitboard.from_square(move.frm), Bitboard.from_square(move.to))
                            for current_bb in bitboards])


def square_distance(a: Square, b: Square) -> int:
    """Rank or file difference (whichever is greater)"""
    return max(abs(a.rank() - b.rank()),
               abs(a.file() - b.file()))


def sliding_moves(square: Square, occupied: Bitboard, deltas: Iterable[int]) -> Bitboard:
    """
    Repeatedly add a delta to square until resultant is outside bitboard range,
    until resultant wraps around bitboard, or encounters a piece (WILL INCLUDE THAT PIECE)

    bitwise-and with not of color to ensure you're not allowing capturing of colors' own piece.
    """
    moves: Bitboard = Bitboard(0)
    for delta in deltas:
        sqr: Square = square
        while True:
            sqr += delta
            if (0 < sqr <= 64) or square_distance(sqr, sqr - delta) > 2:
                break
            moves |= sqr
            if occupied & Bitboard.from_square(sqr):
                break
    return moves


def step_moves(square: Square, deltas: Iterable[int]) -> Bitboard:
    """Generate bitboard of square+deltas, if resultant is within bitboard range and doesn't wrap board"""
    return bb.reduce_with_bitwise_or(Bitboard.from_square(square + delta)
                                     for delta in deltas
                                     if not (0 < square + delta <= 64)
                                     or 2 >= square_distance(square, square + delta))


def pawn_attacks(square: Square, color: bool) -> Bitboard:
    """Must be bitwise and'd with all squares occupied by enemy, make sure to include en passent"""
    return step_moves(square, ((-7, -9), (7, 9))[color])


def pawn_pushes(square: Square, color: bool) -> Bitboard:
    return step_moves(square, ((-1), (1))[color])


def knight_moves(square: Square) -> Bitboard:
    return step_moves(square, (6, -6, 15, -15, 17, -17, 10, -10))


def king_moves(square: Square) -> Bitboard:
    return step_moves(square, (1, -1, 8, -8, 9, -9))


def rank_moves(square: Square, occupied: Bitboard) -> Bitboard:
    return sliding_moves(square, occupied, (-1, 1))


def file_moves(square: Square, occupied: Bitboard) -> Bitboard:
    return sliding_moves(square, occupied, (-8, 8))


def diagonal_moves(square: Square, occupied: bb.Bitboard) -> bb.Bitboard:
    return sliding_moves(square, occupied, (-9, 9, -7, 7))


def piece_move_mask(square: Square, piece: pce.Piece, occupied: bb.Bitboard) -> bb.Bitboard:
    moves: bb.Bitboard = bb.Bitboard(0)
    if abs(piece.value) in {3, 5}:  # Bishop or queen
        moves |= diagonal_moves(square, occupied)
    if abs(piece.value) in {4, 5}:  # Rook or queen
        moves |= rank_moves(square, occupied) | file_moves(square, occupied)
    if abs(piece.value) == 2:  # knight
        moves |= knight_moves(square)
    if abs(piece.value) == 6:  # king
        moves |= king_moves(square)
    return moves
