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

    @property
    def color(self):
        return self.COLORS[self.face]

    @property
    def face_char(self):
        return self.FACE_CHARS[self.face]

    @property
    def face_index(self):
        return self.FACES.index(self.face)

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

    def fill_tableau(self, deck):
        slots = itertools.cycle(self.tableau)
        for c in deck:
            next(slots).push(c)

    def sweep_tableau(self):
        '''
        Sweeps every tableau slot and moves to foundation any card which meets
        the following conditions:
            It can be placed on foundation
            Any Card which may be placed on top may also be placed on foundation
        All tableau slots are swept until no more cards can be moved
        '''
        while 1:
            moved = False

            for t in self.tableau:
                if t and self.should_move_to_foundation(t.top()):
                    self.move_to_foundation(t.pop())
                    moved = True

            if not moved:
                break

    def can_top(self, a, b):
        '''
        Returns whether Card a can be placed, on the tableau, on top of Card b
        '''
        return a.color != b.color and a.value == b.value - 1

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
        return self.can_move_to_foundation(c) and \
            not any(self.can_top(i, c) and not self.can_move_to_foundation(i)
                for t in self.tableau
                    for i in t)

    def is_free(self, c):
        '''
        Returns whether the Card has been freed; that is, the Card is not
        contained in either reserve, foundation, or tableau
        '''
        return c not in self.reserve and \
            all(c not in f for f in self.foundation) and \
            all(c not in t for t in self.tableau)

    def move_capacity(self, to_empty = False):
        '''
        Returns how large a contiguous stack of cards may moved,
        accounting for free reserve slots and free tableau slots

        A True value of to_empty indicates that move capacity to an empty
        slot is being tested and therefore, effectively, there is one
        fewer empty slot available for a contiguous move.
        '''
        if to_empty:
            assert any(t.empty() for t in self.tableau)
        empty_slots = sum(1 for t in self.tableau if t.empty())
        return 1 + (self.reserve.count(None) * empty_slots - to_empty)

    def move_to_foundation(self, c):
        if not self.can_move_to_foundation(c):
            raise InvalidMove

        self.foundation[c.face_index].push(c)

    def move_to_tableau(self, i, c):
        assert self.is_free(c)

        t = self.tableau[i]
        if t and not self.can_top(c, t.top()):
            raise InvalidMove

        t.push(c)

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
