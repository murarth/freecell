#!/usr/bin/python3
# -*- coding: utf-8

import curses
from functools import partial
import itertools
import select
import signal
import sys
import time

from freecell import *

class FreeCellGame(object):

    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.action_input = []
        self.action_display = []
        # Grabs input; returns True to keep grabbing
        self.grab_input_callback = None
        self.locate_match = None
        self.message = None
        self.message_timeout = None
        self.paused = False
        self.pause_draw_callback = None
        self.queue_redraw = True
        self.quit = False
        self.stopped = False
        self.try_sweep = False
        self.undo_list = []
        self.undo_index = None

    def repr_card(self, c):
        '''
        Returns a two-tuple (card string, curses attr)
        '''
        attr = 0
        if c.color == 'red':
            attr = curses.color_pair(1)
        if self.highlight(c):
            attr |= curses.A_REVERSE
        return '{} {:>2}'.format(c.face_char, c.name), attr

    def repr_stack(self, s):
        attr = 0
        c = s.top()
        if c.color == 'red':
            attr = curses.color_pair(1)
        if any(self.highlight(i) for i in s):
            attr |= curses.A_REVERSE
        return '{} {:>2}'.format(c.face_char, c.name), attr

    def grab_input(self, cb):
        if self.grab_input_callback is not None:
            raise Exception('Input is already grabbed')
        self.grab_input_callback = cb

    def prompt_confirmation(self, msg, cb):
        self.set_message(msg + ' (y/n)', None)
        self.grab_input(partial(self.confirm_callback, cb = cb))

    def confirm_callback(self, ch, cb):
        if ch == ord('y'):
            cb()
        self.clear_message()
        return False

    def clear_message(self):
        self.message = None
        self.message_timeout = None
        self.queue_redraw = True

    def set_message(self, msg, timeout = 1):
        self.message = msg
        if timeout:
            self.message_timeout = time.time() + timeout
        self.queue_redraw = True

    def draw(self):
        win = self.stdscr

        y, x = win.getmaxyx()
        win.clear()

        self.draw_title(y, x)
        self.draw_clock(y, x)

        if self.paused:
            self.draw_pause(y, x)
        elif self.stopped:
            self.draw_stopped(y, x)
        else:
            self.draw_field(y, x)

        self.draw_message(y, x)
        self.refresh()

    def draw_field(self, y, x):
        fc = self.freecell
        win = self.stdscr

        win.move(2, (x - ((4 * 5 + 5) * 2 + 1)) // 2)
        #                 |   |    |    |   ` Plus separator
        #                 |   |    |    ` On each side
        #                 |   |    ` Plus surrounding [] and key
        #                 |   ` Five chars wide (including space in between)
        #                 ` Four cards

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

    def draw_clock(self, y, x):
        if self.paused:
            t = int(self.pause_time - self.time_offset)
        else:
            t = int(time.time() - self.time_offset)
        s = '{:d}:{:02d}'.format(*divmod(t, 60))
        self.stdscr.addstr(0, x - len(s) - 2, s, curses.A_REVERSE)

    def draw_message(self, y, x):
        win = self.stdscr
        if self.action_display:
            action = self.action_display
            ln = sum(len(i) for i in action) + len(action)
            win.addstr(y - 1, x - ln,
                ' '.join(action), curses.A_BOLD)
        if self.message:
            win.addstr(y - 1, 0, self.message, curses.A_BOLD)

    def draw_pause(self, y, x):
        if self.pause_draw_callback is None:
            s = 'Paused'
            self.stdscr.addstr(y // 2, (x - len(s)) // 2, s)
        else:
            self.pause_draw_callback(y, x)

    def draw_stopped(self, y, x):
        s = 'You won!'
        self.stdscr.addstr(y // 2, (x - len(s)) // 2, s, curses.A_BOLD)

    def draw_stats(self, y, x):
        pass # TODO

    def draw_title(self, y, x):
        self.stdscr.addstr(0, 0, 'FreeCell')
        self.stdscr.chgat(0, 0, x, curses.A_REVERSE)

    def go(self):
        self.init_ui()
        self.start_game()

        while not self.quit:
            if self.try_sweep:
                self.sweep_step()

            if self.queue_redraw:
                self.draw()
                self.queue_redraw = False
            elif not (self.paused or self.stopped):
                self.draw_clock(*self.stdscr.getmaxyx())
                self.refresh()

            rd, _, _ = select.select([sys.stdin], [], [], 0.1)

            if rd:
                self.handle_input()

            self.after_tick()

    def game_won(self):
        self.stopped = True
        #win_time = time.time() - self.time_offset
        self.queue_redraw = True

    def after_tick(self):
        if self.message_timeout and self.message_timeout <= time.time():
            self.clear_message()

    def handle_input(self):
        while 1:
            ch = self.stdscr.getch()

            if ch == -1:
                break

            if self.grab_input_callback is not None:
                if not self.grab_input_callback(ch):
                    self.grab_input_callback = None
            else:
                cb = self.key_callbacks.get(ch)

                if cb:
                    cb()

    def init_ui(self):
        self.stdscr.nodelay(True)
        curses.noecho()
        signal.signal(signal.SIGWINCH, self.win_resized)

        self.key_callbacks = {
            ord(' '): self.clear_action,
            ord('l'): self.begin_locate,
            ctrl('l'): self.redraw,
            ord('n'): self.confirm_new_game,
            ord('p'): self.toggle_pause,
            ord('q'): self.quit_game,
            ctrl('r'): self.redo,
            #ctrl('s'): self.show_stats,
            ord('u'): self.undo,

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

    def begin_locate(self):
        self.clear_action()
        self.action_display[:] = ['L', '?', '?']
        self.locate_match = { 'color': None, 'value': None }
        self.grab_input(self.locate_callback)

    def locate_callback(self, ch):
        if ch == ord(' '):
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
        self.action_input.append(a)
        self.action_display.append(text)
        self.queue_redraw = True

        state = self.copy_state()

        if self.handle_action():
            self.try_sweep = True
            self.push_undo(state)

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

        return acted

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

    def toggle_pause(self):
        if self.paused:
            self.unpause_game()
        else:
            self.pause_game()

    def pause_game(self):
        if not (self.paused or self.stopped):
            self.pause_time = time.time()
            self.paused = True
            self.grab_input(self.pause_callback)
            self.pause_draw_callback = None
            self.queue_redraw = True

    def pause_callback(self, ch):
        if ch == ord('p'):
            self.unpause_game()
            return False
        elif ch == ord('q'):
            self.quit_game()
            return False

        return True

    def unpause_game(self):
        if self.paused:
            self.time_offset = time.time() - (self.pause_time - self.time_offset)
            self.paused = False
            self.queue_redraw = True

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

    def confirm_new_game(self):
        self.prompt_confirmation('Start a new game?', self.new_game)

    def new_game(self):
        self.start_game()
        self.queue_redraw = True

    def confirm_quit_game(self):
        self.prompt_confirmation('Quit game?', self.quit_game)

    def quit_game(self):
        self.quit = True

    def show_stats(self):
        self.pause_game()
        self.pause_draw_callback = self.draw_stats

    def start_game(self):
        self.freecell = fc = FreeCell(shuffled(make_deck()))
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

    def redraw(self):
        self.queue_redraw = True

    def refresh(self):
        y, x = self.stdscr.getmaxyx()
        self.stdscr.move(0, x - 1)
        self.stdscr.refresh()

    def win_resized(self, *args):
        self.queue_redraw = True

def ctrl(ch):
    return ord(ch) & 0x1f

def init_colors():
    curses.start_color()
    curses.use_default_colors()

    curses.init_pair(1, curses.COLOR_RED, -1)

if __name__ == '__main__':
    stdscr = curses.initscr()
    try:
        init_colors()

        FreeCellGame(stdscr).go()
    finally:
        curses.endwin()
