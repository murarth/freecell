#!/usr/bin/python3
# -*- coding: utf-8

import itertools
import random

__all__ = [
    'Card', 'FreeCell', 'InvalidMove', 'MoveFromEmpty',
    'make_deck', 'shuffled',
]

class InvalidMove(Exception): pass
class MoveFromEmpty(Exception): pass

class Card(object):

    FACES = ('club', 'heart', 'spade', 'diamond')
    VALUES = range(1, 14)

    COLORS = {
        'club': 'black',
        'diamond': 'red',
        'heart': 'red',
        'spade': 'black',
    }

    FACE_CHARS = {
        'club': '\N{BLACK CLUB SUIT}',
        'diamond': '\N{BLACK DIAMOND SUIT}',
        'heart': '\N{BLACK HEART SUIT}',
        'spade': '\N{BLACK SPADE SUIT}',
    }

    NAMES = {
        1: 'A',
        11: 'J',
        12: 'Q',
        13: 'K',
    }

    def __init__(self, face, value):
        assert face in self.FACES
        assert value in self.VALUES
        self.face = face
        self.value = value

    def __eq__(self, rhs):
        if isinstance(rhs, Card):
            return self.face == rhs.face and self.value == rhs.value
        return NotImplemented

    def __repr__(self):
        return 'Card({!r}, {!r})'.format(self.face, self.value)

    def __str__(self):
        return '<Card {} {}>'.format(self.face_char, self.name)

    @property
    def color(self):
        return self.COLORS[self.face]

    @property
    def face_char(self):
        return self.FACE_CHARS[self.face]

    @classmethod
    def get_index(cls, face):
        return cls.FACES.index(face)

    @property
    def face_index(self):
        return self.get_index(self.face)

    @property
    def name(self):
        return self.NAMES.get(self.value) or str(self.value)

class stack(object):

    def __init__(self):
        self.li = []

    def __bool__(self):
        return bool(self.li)

    def __contains__(self, item):
        return item in self.li

    def __iter__(self):
        return iter(self.li)

    def __len__(self):
        return len(self.li)

    def __reversed__(self):
        return reversed(self.li)

    def copy(self):
        s = stack.__new__(stack)
        s.li = self.li[:]
        return s

    def empty(self):
        return not self.li

    def pop(self):
        return self.li.pop(-1)

    def push(self, item):
        self.li.append(item)

    def top(self):
        return self.li[-1]

def make_deck():
    return [Card(*i) for i in itertools.product(Card.FACES, Card.VALUES)]

def shuffled(li):
    random.shuffle(li)
    return li

class FreeCell(object):

    '''
    Represents a FreeCell game playing field and all possible operations
    '''

    RESERVE_SLOTS = 4
    FOUNDATION_SLOTS = len(Card.FACES)
    TABLEAU_SLOTS = 8

    def __init__(self, deck):
        '''
        Initializes a FreeCell game; deck is expected to be shuffled
        '''
        self.reserve = [None] * self.RESERVE_SLOTS
        self.foundation = [stack() for i in range(self.FOUNDATION_SLOTS)]
        self.tableau = [stack() for i in range(self.TABLEAU_SLOTS)]
        self.fill_tableau(deck)

    def copy(self):
        fc = FreeCell.__new__(FreeCell)
        fc.reserve = self.reserve[:]
        fc.foundation = [s.copy() for s in self.foundation]
        fc.tableau = [t.copy() for t in self.tableau]
        return fc

    def fill_tableau(self, deck):
        slots = itertools.cycle(self.tableau)
        for c in deck:
            next(slots).push(c)

    def sweep(self):
        '''
        Sweeps every tableau and reserve slot and moves to foundation
        any card which meets the following conditions:
            It can be placed on foundation
            Any Card which may be placed on top may also be placed on foundation
        All slots are swept until no more cards can be moved
        '''
        while 1:
            moved = False

            for i, r in enumerate(self.reserve):
                if r is not None and self.should_move_to_foundation(r):
                    self.move_to_foundation(self.move_from_reserve(i))
                    moved = True

            for t in self.tableau:
                if t and self.should_move_to_foundation(t.top()):
                    self.move_to_foundation(t.pop())
                    moved = True

            if not moved:
                break

    def sweep_step(self, n = 1):
        '''
        Attempts to sweep only one card and returns whether it was successful
        '''
        success = False
        left = n

        for i, r in enumerate(self.reserve):
            if r is not None and self.should_move_to_foundation(r):
                self.move_to_foundation(self.move_from_reserve(i))
                left -= 1
                if left <= 0:
                    return True

        for t in self.tableau:
            if t and self.should_move_to_foundation(t.top()):
                self.move_to_foundation(t.pop())
                left -= 1
                if left <= 0:
                    return True

        return left != n

    def can_top(self, a, b):
        '''
        Returns whether Card a can be placed, on the tableau, on top of Card b
        '''
        return a.color != b.color and a.value == b.value - 1

    def can_move_to_tableau(self, c, i):
        '''
        Returns whether the given Card c can be moved into tableau slot i
        '''
        t = self.tableau[i]
        return t.empty() or self.can_top(c, t.top())

    def can_move_to_foundation(self, c):
        '''
        Returns whether the given Card can be moved to foundation
        '''
        f = self.foundation[c.face_index]
        return c.value == 1 if f.empty() else (f.top().value == c.value - 1)

    def should_move_to_foundation(self, c):
        '''
        Returns whether the given Card should be moved to foundation in a
        sweep operation
        '''
        if not self.can_move_to_foundation(c):
            return False

        def get_value(idx):
            f = self.foundation[idx]
            return 0 if f.empty() else f.top().value

        min_black = min(
            get_value(Card.get_index('spade')),
            get_value(Card.get_index('club')))

        min_red = min(
            get_value(Card.get_index('heart')),
            get_value(Card.get_index('diamond')))

        if c.color == 'black':
            auto_black = min(min_black + 3, min_red + 2)
            return c.value <= auto_black
        else:
            auto_red = min(min_black + 2, min_red + 3)
            return c.value <= auto_red

    def is_free(self, c):
        '''
        Returns whether the Card has been freed; that is, the Card is not
        contained in either reserve, foundation, or tableau
        '''
        assert isinstance(c, Card)
        return c not in self.reserve and \
            all(c not in f for f in self.foundation) and \
            all(c not in t for t in self.tableau)

    def move_capacity(self, a, b):
        '''
        Returns how large a contiguous stack of cards may moved from
        tableau slot a to b, accounting for free reserve slots and free
        tableau slots. If this is greater than the current number of
        grouped cards in stack a, that value is returned instead.

        NOTE: This method does NOT check whether such a move is valid
        based on the card on top of slot b.
        '''
        if self.tableau[a].empty():
            raise MoveFromEmpty
        to_empty = (self.tableau[b].empty())
        empty_slots = sum(1 for t in self.tableau if t.empty())
        return min(self.count_group(a),
            (1 + self.reserve.count(None)) * 2 ** (empty_slots - to_empty))

    def count_group(self, i):
        '''
        Returns how many cards on top of slot i comprise a valid group
        '''
        t = self.tableau[i]
        if t.empty():
            return 0
        if len(t) == 1:
            return 1

        n = 1

        # From top of stack, iterate over adjacent pairs
        r = reversed(t)
        r2 = reversed(t)
        next(r2)

        for a, b in zip(r, r2):
            if self.can_top(a, b):
                n += 1
            else:
                break

        return n

    def move_to_foundation(self, c):
        if not self.can_move_to_foundation(c):
            raise InvalidMove

        self.foundation[c.face_index].push(c)

    def move_to_tableau(self, c, i):
        '''
        Moves the given Card c to tableau slot i
        '''
        assert self.is_free(c)

        if not self.can_move_to_tableau(c, i):
            raise InvalidMove

        self.tableau[i].push(c)

    def move_tableau_group(self, a, b, n):
        '''
        Moves n cards from tableau slot a to b
        '''
        if n == 0:
            raise InvalidMove
        if n > self.move_capacity(a, b):
            raise InvalidMove

        ta = self.tableau[a]

        cards = [ta.pop() for i in range(n)]
        [self.move_to_tableau(c, b) for c in reversed(cards)]

    def move_to_reserve(self, c):
        assert self.is_free(c)

        if not self.reserve_free():
            raise InvalidMove

        self.reserve[self.reserve.index(None)] = c

    def move_from_reserve(self, i):
        if self.reserve[i] is None:
            raise MoveFromEmpty

        c = self.reserve[i]
        self.reserve[i] = None
        return c

    def reserve_free(self):
        return not all(self.reserve)

    def won(self):
        return all(t.empty() for t in self.tableau)
