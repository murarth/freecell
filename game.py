#!/usr/bin/python3
# -*- coding: utf-8

import curses
import itertools
import select
import signal
import sys
import time

from freecell import *

class FreeCellGame(object):

    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.paused = False
        self.pause_draw_callback = None
        self.queue_redraw = True
        self.quit = False

    def card_repr(self, c):
        '''
        Returns a two-tuple (card string, curses attr)
        '''
        attr = 0
        if c.color == 'red':
            attr = curses.color_pair(1)
        return '{} {:>2}'.format(c.face_char, c.name), attr

    def draw(self):
        win = self.stdscr

        y, x = win.getmaxyx()
        win.clear()

        self.draw_title(y, x)
        self.update_clock(y, x)

        if self.paused:
            self.draw_pause(y, x)
        else:
            self.draw_field(y, x)

        self.refresh()

    def draw_field(self, y, x):
        fc = self.freecell
        win = self.stdscr

        win.move(2, (x - (4 * 5 * 2 + 3)) // 2)
        #                 |   |   |   ` Plus 3 wide separator
        #                 |   |   ` On each side
        #                 |   ` Five chars wide (including space in between)
        #                 ` Four cards

        for c in fc.reserve:
            if c is None:
                win.addstr('____')
            else:
                win.addstr(*self.card_repr(c))
            win.addstr(' ')

        win.addstr('| ')

        for f in fc.foundation:
            if f.empty():
                win.addstr('____')
            else:
                win.addstr(*self.card_repr(c))
            win.addstr(' ')

        off = (x - (8 * 6)) // 2
        #           |   ` Six chars wide (including two spaces between)
        #           ` Eight slots

        r = itertools.repeat(None)

        cols = [itertools.chain(iter(t), r) for t in fc.tableau]

        for i, _ in enumerate(range(max(len(t) for t in fc.tableau))):
            win.move(i + 4, off)
            for t in cols:
                c = next(t)
                if c is None:
                    win.addstr('    ')
                else:
                    win.addstr(*self.card_repr(c))
                win.addstr('  ')

    def draw_pause(self, y, x):
        if self.pause_draw_callback is None:
            s = 'Paused'
            self.stdscr.addstr(y // 2, (x - len(s)) // 2, s)
        else:
            self.pause_draw_callback(y, x)

    def draw_stats(self, y, x):
        pass # TODO

    def draw_title(self, y, x):
        self.stdscr.addstr(0, 0, 'FreeCell')
        self.stdscr.chgat(0, 0, x, curses.A_REVERSE)

    def go(self):
        self.init_ui()
        self.start_game()

        while not self.quit:
            if self.queue_redraw:
                self.draw()
                self.queue_redraw = False
            elif not self.paused:
                self.update_clock(*self.stdscr.getmaxyx())
                self.refresh()

            rd, _, _ = select.select([sys.stdin], [], [], 0.1)

            if rd:
                self.handle_input()

    def handle_input(self):
        while 1:
            ch = self.stdscr.getch()

            if ch == -1:
                break

            cb = self.key_callbacks.get(ch)

            if cb:
                cb()

    def init_ui(self):
        self.stdscr.nodelay(True)
        curses.noecho()
        signal.signal(signal.SIGWINCH, self.win_resized)

        self.key_callbacks = {
            ord('p'): self.toggle_pause,
            ord('q'): self.quit_game,
            #ord('s'): self.show_stats,
        }

    def toggle_pause(self):
        if self.paused:
            self.unpause_game()
        else:
            self.pause_game()

    def pause_game(self):
        if not self.paused:
            self.pause_time = time.time()
            self.paused = True
            self.pause_draw_callback = None
            self.queue_redraw = True

    def unpause_game(self):
        if self.paused:
            self.time_offset = time.time() - (self.pause_time - self.time_offset)
            self.paused = False
            self.queue_redraw = True

    def quit_game(self):
        self.quit = True

    def show_stats(self):
        self.pause_game()
        self.pause_draw_callback = self.draw_stats

    def start_game(self):
        self.freecell = FreeCell(shuffled(make_deck()))
        self.time_offset = time.time()

    def update_clock(self, y, x):
        t = int(time.time() - self.time_offset)
        s = '{:d}:{:02d}'.format(*divmod(t, 60))
        self.stdscr.addstr(0, x - len(s) - 2, s, curses.A_REVERSE)

    def refresh(self):
        y, x = self.stdscr.getmaxyx()
        self.stdscr.move(0, x - 1)
        self.stdscr.refresh()

    def win_resized(self, *args):
        self.queue_redraw = True

def init_colors():
    curses.start_color()
    curses.use_default_colors()

    for i in range(curses.COLORS):
        curses.init_pair(i, i, -1)

if __name__ == '__main__':
    stdscr = curses.initscr()
    try:
        init_colors()

        FreeCellGame(stdscr).go()
    finally:
        curses.endwin()
