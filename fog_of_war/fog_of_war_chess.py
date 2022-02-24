# pylint: disable=C0415
"""
attack_masks.py
Functions for generating bitboard masks for different pieces attack patterns.

Author: Noah Rowe
Date: 2022/02/21
Last Modified: 2022/02/23
    Added docstrings
"""
from __future__ import annotations

from functools import cached_property
from random import choice as rand_choice
from typing import List, Generator

import numpy as np

from fog_of_war.attack_masks import piece_move_mask, pawn_attack_mask
from fog_of_war.chess_bitboards import Bitboard, ChessBitboards
from fog_of_war.special_move_bitboards import SpecialMoveBitboards
from fog_of_war.helper_functions import \
    reverse_scan_for_square, \
    reduce_with_bitwise_or, \
    reverse_scan_for_mask
from fog_of_war.move import Move
from fog_of_war.piece import Piece
from fog_of_war.square import Square


def apply_fog(board: np.ndarray, fog: np.ndarray) -> np.ndarray:
    """
    Apply fog to board. Fog is represented as 15.
    @param board: 8x8 numpy array representing a chess board
    @param fog:  8x8 numpy array representing fog over a chess board
    @return foggy_board: 8x8 numpy array representing a chess board with fog applied.
    """
    # This is a bit dumb, but I dunno
    return np.clip(board + np.logical_not(fog.copy()) * 20, -16, 15)


class FOWChess:
    """
    Represents a state of a fog of war chess game.
    """
    WHITE = True
    BLACK = False

    def __init__(self,
                 bitboards: ChessBitboards,
                 turn: bool,
                 special_moves: SpecialMoveBitboards,
                 half_move: int, ) -> None:
        # immutable
        self.__current_turn: bool = turn  # color of the current player
        self.__bitboards = bitboards  # Integer bitboards of both colors and all pieces
        self.__special: SpecialMoveBitboards = special_moves  # Bitboards for castling/ep bitboards
        self.__half_move: int = half_move

    def __hash__(self) -> int:
        return (*self.__bitboards, *self.__special, self.__current_turn, self.__half_move).__hash__()

    @classmethod
    def new_game(cls) -> FOWChess:
        """
        Alternate constructor for a FOWChess game.
        Creates game in the standard chess board starting position.
        """
        return cls(
            bitboards=ChessBitboards.new_game(),
            turn=cls.WHITE,
            special_moves=SpecialMoveBitboards.new_game(),
            half_move=0)

    @classmethod
    def from_fow(cls, parent: FOWChess, move: Move) -> FOWChess:
        """
        Create a new fow game state,
        by applying a move to an existing fow game state
        """
        return cls(
            bitboards=parent.bitboards.make_move(move),
            turn=not parent.current_turn,
            special_moves=parent.special_moves.update(parent.bitboards, move),
            half_move=parent.half_move_counter + 1
        )

    @property
    def half_move_counter(self) -> int:
        """
        How many half moves have occurred?
        Half moves count from 0
        """
        return self.__half_move

    @property
    def full_move_number(self) -> int:
        """
        What number of full move is the game currently on?
        Counts from 1
        """
        return self.__half_move // 2 + 1

    @property
    def current_turn(self) -> bool:
        """Color of the current player. True if white, False if black"""
        return self.__current_turn

    @property
    def bitboards(self) -> ChessBitboards:
        """Bitboards representing pieces and colors"""
        return self.__bitboards

    @property
    def special_moves(self) -> SpecialMoveBitboards:
        """Bitboards representing ep and castling bitboards"""
        return self.__special

    @property
    def possible_moves_list(self) -> List[Move]:
        """List of possible legal moves"""
        return list(self.possible_moves_generator())

    def make_move(self, move: Move) -> FOWChess:
        """Given a move, create a FOWChess node where that move has been made."""
        return FOWChess(
            bitboards=self.bitboards.make_move(move),
            turn=not self.current_turn,
            special_moves=self.special_moves.update(self.bitboards, move),
            half_move=self.half_move_counter+1
        )

    def make_random_move(self) -> FOWChess:
        """Make a randomly chosen move from the list of possible moves"""
        return self.make_move(rand_choice(self.possible_moves_list))

    @cached_property
    def is_over(self) -> bool:  # TODO: better termination checks
        """True if 1 king left on board"""
        return len(list(reverse_scan_for_mask(self.bitboards.kings))) == 1

    @cached_property
    def winner(self) -> bool | None:  # maybe make this a class
        """Return True if white, False if Black, None if not over."""
        white: int = self.bitboards.white & self.bitboards.kings
        black: int = self.bitboards.black & self.bitboards.kings
        if white == black:
            return None
        elif not white:
            return self.BLACK
        elif not black:
            return self.WHITE

    @cached_property
    def board_as_numpy(self) -> np.ndarray:
        """
        A numpy representation of the chess board, using integers.
        See Piece enum for encoding
        """
        return (
                       self.bitboards.kings.bitboard_to_numpy() * Piece['K'].value
                       + self.bitboards.queens.bitboard_to_numpy() * Piece['Q'].value
                       + self.bitboards.pawns.bitboard_to_numpy() * Piece['P'].value
                       + self.bitboards.rooks.bitboard_to_numpy() * Piece['R'].value
                       + self.bitboards.bishops.bitboard_to_numpy() * Piece['B'].value
                       + self.bitboards.knights.bitboard_to_numpy() * Piece['N'].value
               ) * (
                       self.bitboards.black.bitboard_to_numpy() * -1
                       + self.bitboards.white.bitboard_to_numpy()
               )

    @cached_property
    def black_board(self) -> np.ndarray:
        """Numpy array representation of board, with black on the bottom."""
        # * -1 and mirror about 1 as well if you want it to look like white
        return np.flip(self.board_as_numpy, 0)

    @cached_property
    def white_board(self) -> np.ndarray:
        """Numpy array representation of board, where white is on bottom"""
        return self.board_as_numpy

    @cached_property
    def black_fog(self) -> np.ndarray:
        """Numpy array representation of black's fog, where black is on bottom"""
        return np.flip(self._visible_squares(False).bitboard_to_numpy(), 0)

    @cached_property
    def white_fog(self) -> np.ndarray:
        """Numpy array representation of white's fog, where white is on bottom"""
        return self._visible_squares(True).bitboard_to_numpy()

    @cached_property
    def white_foggy_board(self) -> np.ndarray:
        """Numpy array representation of board with white's fog applied, where white is on bottom"""
        return apply_fog(self.white_board, self.white_fog)

    @cached_property
    def black_foggy_board(self) -> np.ndarray:
        """Numpy array representation of board with black's fog applied, where black is on bottom"""
        return apply_fog(self.black_board, self.black_fog)

    def _occupied_by_color(self, color: bool) -> Bitboard:
        """White's bitboard if True, black's if False"""
        return self.bitboards.white if color else self.bitboards.black

    def _anyone_attacking(self, square_mask: Bitboard) -> bool:
        """
        Using the principal of
        "Is one of their pieces attacking square" being logically the same as
        "If a piece of our color was on square, could it attack the same piece type of their color"
        determine if anyone is attacking square.
        """
        square: Square = Square(square_mask.bit_length())
        from attack_masks import rank_moves, file_moves, diagonal_moves, king_moves, knight_moves

        occupied = self.bitboards.black | self.bitboards.white
        their_pieces = self._occupied_by_color(not self.current_turn)

        r_and_f_attackers = (self.bitboards.queens | self.bitboards.rooks) & their_pieces
        diag_attackers = (self.bitboards.queens | self.bitboards.bishops) & their_pieces
        king_attackers = (self.bitboards.kings | self.bitboards.queens) & their_pieces
        knight_attackers = self.bitboards.knights & their_pieces

        return any((
            (self.bitboards.pawns
             & their_pieces
             & pawn_attack_mask(square, self.current_turn)),
            ((rank_moves(square, occupied) | file_moves(square, occupied))
             & r_and_f_attackers),
            diagonal_moves(square, occupied) & diag_attackers,
            king_moves(square) & king_attackers,
            knight_moves(square) & knight_attackers))

    def possible_moves_generator(self) -> Generator[Move]:
        """List of possible moves the current player can legally make."""

        # 'Best practice' calls for this to be made into a billion little functions
        # But honestly I think making a bunch of little functions just to use them here
        # is less readable and takes more time than this huge massive one.
        # And they're all pretty specialized,
        # so it's not like they'll be reused anywhere other than in visible_squares.

        our_pieces: Bitboard = self._occupied_by_color(self.current_turn)
        their_pieces: Bitboard = self._occupied_by_color(not self.current_turn)
        everyones_pieces: Bitboard = our_pieces | their_pieces

        # Generate non-pawn moves.
        for frm_sqr in reverse_scan_for_square(our_pieces & ~self.bitboards.pawns):
            for to_sqr in reverse_scan_for_square(
                    ~our_pieces &
                    piece_move_mask(frm_sqr, self.bitboards.piece_at(frm_sqr), everyones_pieces)
            ):
                yield Move(to=to_sqr, frm=frm_sqr)

        # check for castling
        if (self.special_moves.castling_kings & our_pieces
                and self.special_moves.castling_rooks & our_pieces):

            backrank: Bitboard = (Bitboard.from_rank(1)
                                  if self.current_turn else Bitboard.from_rank(8))

            a_mask: Bitboard = backrank & Bitboard.from_file(1)
            b_mask: Bitboard = backrank & Bitboard.from_file(2)
            c_mask: Bitboard = backrank & Bitboard.from_file(3)
            d_mask: Bitboard = backrank & Bitboard.from_file(4)

            f_mask: Bitboard = backrank & Bitboard.from_file(6)
            g_mask: Bitboard = backrank & Bitboard.from_file(7)
            h_mask: Bitboard = backrank & Bitboard.from_file(8)

            our_king_mask: Bitboard = self.bitboards.kings & our_pieces

            # Try for king side castle
            if (self.special_moves.castling_kings & our_pieces
                    and self.special_moves.king_side_castling & our_pieces
                    and ~everyones_pieces & (f_mask | g_mask)
                    and not any(self._anyone_attacking(square_mask)
                                for square_mask in (our_king_mask, f_mask, g_mask))):
                yield Move(to=Square(g_mask.bit_length()),
                           frm=Square(our_king_mask.bit_length()),
                           rook_to=Square(f_mask.bit_length()),
                           rook_frm=Square(h_mask.bit_length()))
            # Try for queen side
            if (self.special_moves.castling_kings & our_pieces
                    and self.special_moves.queen_side_castling & our_pieces
                    and ~everyones_pieces & (b_mask | c_mask | d_mask)
                    and not any(self._anyone_attacking(square)
                                for square in (our_king_mask, c_mask, d_mask))):
                yield Move(to=Square(c_mask.bit_length()),
                           frm=Square(our_king_mask.bit_length()),
                           rook_frm=Square(a_mask.bit_length()),
                           rook_to=Square(d_mask.bit_length()))

        # If there are pawns, generate their moves
        if pawns := self.bitboards.pawns & our_pieces:
            # First if they can attack anyone
            for frm_sqr in reverse_scan_for_square(pawns):
                for to_sqr in reverse_scan_for_square(
                        pawn_attack_mask(frm_sqr, self.current_turn)
                        & their_pieces):
                    yield Move(to_sqr, frm_sqr)

            backrank: Bitboard
            # Then find their single and double moves
            if self.current_turn == self.WHITE:
                single_moves = (pawns << 8) & ~everyones_pieces
                double_moves = (single_moves << 8
                                & Bitboard.from_rank(4)
                                & ~everyones_pieces)
                backrank = Bitboard.from_rank(1)
            else:
                single_moves = pawns >> 8 & ~everyones_pieces
                double_moves = (
                        single_moves >> 8
                        & Bitboard.from_rank(6)
                        & ~everyones_pieces)
                backrank = Bitboard.from_rank(8)

            for to_sqr in reverse_scan_for_square(single_moves):
                yield Move(to_sqr, Square(to_sqr.value - 8))

            for to_sqr in reverse_scan_for_square(double_moves):
                yield Move(to_sqr, Square(to_sqr.value - 16))

            # promotion
            if backrank & pawns:
                for pawn in reverse_scan_for_square(pawns):
                    for promote in (2, 3, 4):
                        yield Move(to=pawn,
                                   frm=pawn,
                                   promotion_to=Piece(
                                       promote * (-1 * (not self.current_turn))
                                   ))

            # Check for en passent
            if (self.special_moves.ep_bitboard
                    and not self.special_moves.ep_bitboard & everyones_pieces):
                # "Is there one of our pawns attacking the ep square?"
                # is logically the same question as
                # "If there was one of their pawns on the ep square,
                #   would it be attacking one of our pawns?"
                ep_square: Square = Square(self.special_moves.ep_bitboard.bit_length())
                for frm_sqr in reverse_scan_for_square(
                        pawn_attack_mask(ep_square, not self.current_turn) & pawns):
                    yield Move(ep_square, frm_sqr)

    def _visible_squares(self, color: bool) -> Bitboard:
        """
        Generate a bitboard of squares which should be visible to the @param color
        (where True is white and black is False)
        """
        # 'Best practice' calls for this to be made into a billion little functions
        # But honestly I think making a bunch of little functions just to use them here
        # is less readable and takes more time than this huge massive one.
        # And they're all pretty specialized,
        # so it's not like they'll be reused anywhere other than in possible_move_generator.

        visible: Bitboard = Bitboard(0)

        our_pieces: Bitboard = Bitboard(self._occupied_by_color(color))
        their_pieces: Bitboard = Bitboard(self._occupied_by_color(not color))
        everyones_pieces: Bitboard = our_pieces | their_pieces

        visible |= our_pieces

        # Generate non-pawn moves.
        piece_moves = reduce_with_bitwise_or(
            *(piece_move_mask(frm, self.bitboards.piece_at(frm), everyones_pieces) & ~our_pieces
              for frm in (reverse_scan_for_square(our_pieces & ~self.bitboards.pawns)))
        )
        visible |= piece_moves

        # If there are pawns, generate their moves
        if pawns := self.bitboards.pawns & our_pieces:
            # First if they can attack anyone
            pawn_attacks = reduce_with_bitwise_or(
                *(pawn_attack_mask(frm, color) & their_pieces
                  for frm in reverse_scan_for_square(pawns))
            )
            visible |= pawn_attacks

            # Then find their single and double moves
            if color == self.WHITE:
                single_moves = pawns << 8 & ~everyones_pieces
                double_moves = single_moves << 8 & Bitboard.from_rank(4) & ~everyones_pieces

            else:
                single_moves = pawns >> 8 & ~everyones_pieces
                double_moves = single_moves >> 8 & Bitboard.from_rank(6) & ~everyones_pieces
            visible |= single_moves | double_moves

            # Finally, check if an en passant is available
            if (self.special_moves.ep_bitboard
                    and not (everyones_pieces
                             & self.special_moves.ep_bitboard)):
                ep_square: Square = Square(self.special_moves.ep_bitboard.bit_length())
                visible |= reduce_with_bitwise_or(
                    *(frm for frm in reverse_scan_for_mask(
                        pawn_attack_mask(ep_square, not self.current_turn) & pawns)))

        return Bitboard(visible)