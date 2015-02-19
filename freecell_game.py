#!/usr/bin/python3
# -*- coding: utf-8

import curses
from functools import partial
import itertools
import json
import os
import sys
import time

from freecell import *
from game import *

class Stats(object):

    def __init__(self, cfg):
        self.games_played = cfg.get('games', 0)
        self.games_won = cfg.get('won', 0)
        self.total_time = cfg.get('total_time', 0)
        self.lowest_time = cfg.get('lowest_time', 0)
        self.highest_time = cfg.get('highest_time', 0)

    def add_game(self):
        self.games_played += 1

    def add_game_won(self, t):
        self.games_played += 1
        self.games_won += 1
        self.total_time += t
        if self.lowest_time == 0 or t < self.lowest_time:
            self.lowest_time = t
        if t > self.highest_time:
            self.highest_time = t

    def get_average_time(self):
        if self.games_won == 0:
            return 0
        return self.total_time // self.games_won

    def get_win_rate(self):
        if self.games_played == 0:
            return 0
        return self.games_won * 100 // self.games_played

    def clear(self):
        self.games_played = 0
        self.games_won = 0
        self.total_time = 0
        self.lowest_time = 0
        self.highest_time = 0

    def save(self):
        return {
            'games': self.games_played,
            'won': self.games_won,
            'total_time': self.total_time,
            'lowest_time': self.lowest_time,
            'highest_time': self.highest_time,
        }

class FreeCellGame(Game):

    GAME_TITLE = 'FreeCell'
    STATS_FILE = '~/.config/mur-freecell/stats.cfg'

    def __init__(self, stdscr):
        super().__init__(stdscr)
        self.action_display = []
        self.action_input = []
        self.action_keys = set()
        self.freecell = None
        self.locate_match = None
        self.stats = Stats(self.load_config(self.STATS_FILE))
        self.try_sweep = False
        self.undo_list = []
        self.undo_index = None

        self.key_callbacks = {
            ord(' '): self.clear_action,
            ctrl('['): self.clear_action,
            ord('l'): self.begin_locate,
            ctrl('l'): self.redraw,
            ord('n'): self.confirm_new_game,
            ord('p'): self.toggle_pause,
            ord('q'): self.confirm_quit_game,
            ctrl('r'): self.redo,
            ord('S'): self.show_stats,
            ord('u'): self.undo,
            ord('?'): self.show_help,

            # Action inputs
            ord('r'): partial(self.action, 'reserve', 'R'),
            ord('t'): partial(self.action, 'foundation', 'T'),
            ord('a'): partial(self.action, 0, 'A'),
            ord('s'): partial(self.action, 1, 'S'),
            ord('d'): partial(self.action, 2, 'D'),
            ord('f'): partial(self.action, 3, 'F'),
            ord('g'): partial(self.action, 4, 'G'),
            ord('h'): partial(self.action, 5, 'H'),
            ord('j'): partial(self.action, 6, 'J'),
            ord('k'): partial(self.action, 7, 'K'),
        }

        self.action_keys = {
            ord('r'), ord('t'), ord('a'), ord('s'), ord('d'),
            ord('f'), ord('g'), ord('h'), ord('j'), ord('k'),
        }

    def repr_card(self, c):
        '''
        Returns a two-tuple (card string, curses attr) for a Card
        '''
        attr = 0
        if c.color == 'red':
            attr = curses.color_pair(1)
        if self.highlight(c):
            attr |= curses.A_REVERSE
        return '{} {:>2}'.format(c.face_char, c.name), attr

    def repr_stack(self, s):
        '''
        Returns a two-tuple (card string, curses attr) for a stack of cards.
        The top card is rendered normally, but highlighting is applied if
        any cards in the stack match.
        '''
        attr = 0
        c = s.top()
        if c.color == 'red':
            attr = curses.color_pair(1)
        if any(self.highlight(i) for i in s):
            attr |= curses.A_REVERSE
        return '{} {:>2}'.format(c.face_char, c.name), attr

    def draw_field(self, y, x):
        '''
        Draws playing field containing cards and slots
        '''
        fc = self.freecell
        win = self.stdscr

        # draw_centered would be easier, but this line contains attributes
        win.move(2, (x - ((4 * 5 + 5) * 2 + 1)) // 2)
        #                  |   |   |    |   ` Plus separator
        #                  |   |   |    ` On each side
        #                  |   |   ` Plus surrounding [] and key
        #                  |   ` Five chars wide (including space in between)
        #                  ` Four cards

        win.addstr('R [ ')

        for c in fc.reserve:
            if c is None:
                win.addstr('____')
            else:
                win.addstr(*self.repr_card(c))
            win.addstr(' ')

        win.addstr('] [ ')

        for f in fc.foundation:
            if f.empty():
                win.addstr('____')
            else:
                win.addstr(*self.repr_stack(f))
            win.addstr(' ')

        win.addstr('] T')

        off = (x - (8 * 6)) // 2
        #           |   ` Six chars wide (including two spaces between)
        #           ` Eight slots

        win.addstr(4, off,
            '  '.join(' {}  '.format(k)
                for k in ('A', 'S', 'D', 'F', 'G', 'H', 'J', 'K')),
                curses.A_UNDERLINE)

        r = itertools.repeat(None)

        cols = [itertools.chain(iter(t), r) for t in fc.tableau]

        for i, _ in enumerate(range(max(len(t) for t in fc.tableau))):
            win.move(i + 5, off)
            for t in cols:
                c = next(t)
                if c is None:
                    win.addstr('    ')
                else:
                    win.addstr(*self.repr_card(c))
                win.addstr('  ')

    def draw_message(self, y, x):
        '''Draws message and action input'''
        win = self.stdscr
        if self.action_display:
            action = self.action_display
            ln = sum(len(i) for i in action) + len(action)
            win.addstr(y - 1, x - ln,
                ' '.join(action), curses.A_BOLD)
        super().draw_message(y, x)

    def draw_help(self, y, x):
        '''Draw help screen'''

        lines = [
            '?            Show this help screen',
            'Q            Quit the game (requires confirmation)',
            'P            Pause or unpause the game',
            'S            Show game stats',
            'L            Start card lookup (Esc or Space to end)',
            'R or B       Search for a Red or Black card',
            '0-9, J, Q, K Search for a card value (0 means 10)',
            '',
            'Esc or Space Cancel an action',
            'U            Undo an action',
            'Ctrl-R       Redo an action',
            'A-K          Reference a slot on the tableau',
            'R, then A-F  Reference a slot on the reserve',
            'T            Reference the foundation',
            '',
            'To move a card, reference the source slot,',
            '  then the destination slot.',
            'Pressing tableau key twice moves to reserve.',
        ]

        starty = (y - (len(lines) + 2)) // 2
        startx = (x - max(map(len, lines))) // 2

        self.draw_centered(starty, x, 'HELP', curses.A_BOLD)

        for i, s in enumerate(lines, 2):
            self.draw_line(starty + i, startx, s)

    def draw_stats(self, y, x):
        '''Draws stats screen'''
        stats = self.stats

        lines = [
            'Games played: {:>5}'.format(stats.games_played),
            'Games won:    {:>5}'.format(stats.games_won),
            'Win rate:     {:>4}%'.format(stats.get_win_rate()),
            '',
            'Average time: {:>5}'.format(self.time_str(stats.get_average_time())),
            'Lowest time:  {:>5}'.format(self.time_str(stats.lowest_time)),
            'Highest time: {:>5}'.format(self.time_str(stats.highest_time)),
        ]

        starty = (y - (len(lines) + 4)) // 2

        self.draw_centered(starty, x, 'STATS', curses.A_BOLD)

        for i, s in enumerate(lines, 2):
            self.draw_centered(starty + i, x, s)

        self.draw_centered(starty + len(lines) + 3, x, "Press 'c' to clear")

    def before_tick(self):
        super().before_tick()
        if not self.paused and self.try_sweep:
            self.sweep_step()

    def end_game(self):
        if not self.stopped and self.undo_list:
            self.stats.add_game()
            self.save_stats()

    def game_won(self):
        '''Called when the game has been won'''
        self.paused = False
        self.stopped = True
        self.try_sweep = False
        win_time = int(time.time() - self.time_offset)
        self.clear_action()
        self.clear_grab()
        self.grab_input(self.stopped_callback)
        self.queue_redraw = True

        self.stats.add_game_won(win_time)
        self.save_stats()

    def begin_locate(self):
        self.clear_action()
        self.action_display[:] = ['L', '?', '?']
        self.locate_match = { 'color': None, 'value': None }
        self.grab_input(self.locate_callback)

    def locate_callback(self, ch):
        if ch == ord(' ') or ch == ctrl('['):
            self.clear_action()
            self.locate_match = None
            return False
        elif ch == ord('b'):
            self.locate_match['color'] = 'black'
            self.action_display[1] = 'B'
        elif ch == ord('r'):
            self.locate_match['color'] = 'red'
            self.action_display[1] = 'R'
        elif ch == ord('a'):
            self.locate_match['value'] = 1
            self.action_display[2] = 'A'
        elif ch == ord('j'):
            self.locate_match['value'] = 11
            self.action_display[2] = 'J'
        elif ch == ord('q'):
            self.locate_match['value'] = 12
            self.action_display[2] = 'Q'
        elif ch == ord('k'):
            self.locate_match['value'] = 13
            self.action_display[2] = 'K'
        elif ch == ord('0'):
            self.locate_match['value'] = 10
            self.action_display[2] = '10'
        elif ch in range(ord('2'), ord('9') + 1):
            n = ch - ord('0')
            self.locate_match['value'] = n
            self.action_display[2] = str(n)
        else:
            return True

        self.queue_redraw = True
        return True

    def highlight(self, c):
        '''Returns whether the given card should be highlighted'''
        m = self.locate_match
        if m is not None:
            self.queue_redraw = True
            return c.color == m['color'] and c.value == m['value']
        return False

    def clear_action(self):
        del self.action_input[:]
        del self.action_display[:]
        self.queue_redraw = True

    def action(self, a, text):
        grab = not self.action_input
        self.action_input.append(a)
        self.action_display.append(text)
        self.queue_redraw = True

        state = self.copy_state()

        handled, acted = self.handle_action()

        if acted:
            self.try_sweep = True
            self.push_undo(state)
            return False
        elif handled:
            return False

        if grab:
            self.grab_input(self.action_callback)

        return True

    def action_callback(self, ch):
        if ch in self.action_keys:
            return self.key_callbacks[ch]()
        elif ch == ctrl('[') or ch == ord(' '):
            self.clear_action()
            return False
        return True

    def handle_action(self):
        act = self.action_input
        ln = len(act)

        if not ln:
            return

        fc = self.freecell
        handled = False
        acted = False

        if act[0] == 'reserve':
            if ln > 1:
                if isinstance(act[1], int):
                    res_n = act[1]
                    if res_n not in range(fc.RESERVE_SLOTS):
                        handled = True
                        self.set_message('Invalid reserve slot')
                    elif fc.reserve[res_n] is None:
                        handled = True
                        self.set_message('Reserve slot is empty')
                    elif ln > 2:
                        if act[2] == 'foundation':
                            if not fc.can_move_to_foundation(fc.reserve[res_n]):
                                handled = True
                                self.set_message('Cannot move to foundation')
                            else:
                                acted = handled = True
                                fc.move_to_foundation(fc.move_from_reserve(res_n))
                        elif isinstance(act[2], int):
                            if not fc.can_move_to_tableau(fc.reserve[res_n], act[2]):
                                handled = True
                                self.set_message('Cannot move to tableau')
                            else:
                                acted = handled = True
                                fc.move_to_tableau(fc.move_from_reserve(res_n), act[2])
                        else:
                            handled = True
                            self.set_message('Invalid action')
                else:
                    handled = True
                    self.set_message('Invalid action')
        elif act[0] == 'foundation':
            handled = True
            self.set_message('Cannot move cards from foundation')
        elif isinstance(act[0], int):
            tab_n = act[0]
            if tab_n not in range(fc.TABLEAU_SLOTS):
                handled = True
                self.set_message('Invalid tableau slot')
            elif fc.tableau[tab_n].empty():
                handled = True
                self.set_message('Tableau slot is empty')
            elif ln > 1:
                if act[1] == 'reserve':
                    if not fc.reserve_free():
                        handled = True
                        self.set_message('No free reserve slots')
                    else:
                        acted = handled = True
                        fc.move_to_reserve(fc.tableau[tab_n].pop())
                elif act[1] == 'foundation':
                    if not fc.can_move_to_foundation(fc.tableau[tab_n].top()):
                        handled = True
                        self.set_message('Cannot move to foundation')
                    else:
                        acted = handled = True
                        fc.move_to_foundation(fc.tableau[tab_n].pop())
                elif isinstance(act[1], int):
                    dest_n = act[1]
                    if tab_n == dest_n:
                        if not fc.reserve_free():
                            handled = True
                            self.set_message('No free reserve slots')
                        else:
                            acted = handled = True
                            fc.move_to_reserve(fc.tableau[tab_n].pop())
                    elif dest_n not in range(fc.TABLEAU_SLOTS):
                        handled = True
                        self.set_message('Invalid tableau slot')
                    else:
                        handled = True
                        acted = self.tableau_move(tab_n, dest_n)
        else:
            self.clear_action()
            self.set_message('Invalid action')

        if handled:
            self.clear_action()

        return handled, acted

    def tableau_move(self, src, dest):
        fc = self.freecell

        if fc.tableau[dest].empty():
            # NOTE: A move to an empty slot is ambiguous.
            # There is no way to know how many cards the user wants to move.
            # Therefore, we assume that the most common desired action is to
            # move as many cards as possible.
            n = fc.move_capacity(src, dest)
        else:
            for i, c in zip(range(fc.count_group(src)), reversed(fc.tableau[src])):
                if fc.can_top(c, fc.tableau[dest].top()):
                    n = i + 1
                    break
            else:
                self.set_message('Cannot move cards')
                return False

            if n > fc.move_capacity(src, dest):
                self.set_message('Not enough reserve slots to move')
                return False

        fc.move_tableau_group(src, dest, n)
        return True

    def copy_state(self):
        return self.freecell.copy()

    def undo(self):
        if not self.undo_list:
            return

        if self.undo_index is None:
            self.undo_index = len(self.undo_list) - 1
            self.undo_list.append(self.freecell)
            self.freecell = self.undo_list[self.undo_index]
        elif self.undo_index != 0:
            self.undo_index -= 1
            self.freecell = self.undo_list[self.undo_index]
        self.try_sweep = True
        self.queue_redraw = True

    def redo(self):
        if self.undo_index is not None:
            self.undo_index += 1
            if self.undo_index == len(self.undo_list):
                self.freecell = self.undo_list.pop(-1)
                self.undo_index = None
            else:
                self.freecell = self.undo_list[self.undo_index]
            self.try_sweep = True
            self.queue_redraw = True

    def push_undo(self, state):
        if self.undo_index is not None:
            del self.undo_list[self.undo_index:]
            self.undo_index = None
        self.undo_list.append(state)

    def new_game(self):
        if not self.stopped and self.undo_list:
            self.stats.add_game()
        self.start_game()
        self.save_stats()
        self.queue_redraw = True

    def show_help(self):
        self.pause_game(self.help_callback, self.draw_help)

    def show_stats(self):
        self.pause_game(self.stats_callback, self.draw_stats)

    def help_callback(self, ch):
        if ch in { ord('p'), ord(' '), ctrl('[') }:
            self.unpause_game()
            return False
        elif ch == ord('q'):
            self.confirm_quit_game()

        return True

    def stats_callback(self, ch):
        if ch in { ord('p'), ord(' '), ctrl('[') }:
            self.unpause_game()
            return False
        elif ch == ord('q'):
            self.confirm_quit_game()
        elif ch == ord('c'):
            self.prompt_confirmation('Clear stats?', self.clear_stats)

        return True

    def clear_stats(self):
        self.stats.clear()
        self.save_stats()
        self.queue_redraw = True

    def save_stats(self):
        self.save_config(self.STATS_FILE, self.stats.save())

    def start_game(self):
        self.freecell = FreeCell(shuffled(make_deck()))
        self.paused = False
        self.stopped = False
        self.try_sweep = True
        self.time_offset = time.time()
        del self.undo_list[:]
        self.undo_index = None

    def sweep_step(self):
        if self.freecell.sweep_step(3):
            self.queue_redraw = True
            if self.freecell.won():
                self.game_won()
        else:
            self.try_sweep = False

    def load_config(self, fname):
        try:
            with open(os.path.expanduser(fname), 'r') as f:
                return json.load(f)
        except IOError:
            return {}

    def save_config(self, fname, cfg):
        try:
            p = os.path.expanduser(fname)
            os.makedirs(os.path.dirname(p), 0o755, exist_ok = True)

            with open(p, 'w') as f:
                json.dump(cfg, f)
                f.write('\n')
        except IOError as e:
            self.set_message('Failed to save file: {}'.format(e))

if __name__ == '__main__':
    main(FreeCellGame)
