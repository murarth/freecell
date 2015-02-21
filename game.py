#!/usr/bin/python3
# -*- coding: utf-8

import curses
from functools import partial
import signal
import time

__all__ = [
    'ctrl', 'main',
    'Game',
]

def ctrl(ch):
    return ord(ch) & 0x1f

def main(game_class):
    stdscr = curses.initscr()
    try:
        game_class(stdscr).go()
    finally:
        curses.endwin()

class Game(object):

    GAME_TITLE = NotImplemented

    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.grab_input_callbacks = []
        self.key_callbacks = NotImplemented
        self.message = None
        self.message_timeout = None
        self.paused = False
        self.pause_draw_callback = None
        self.queue_redraw = True
        self.quit = False
        self.stopped = False

    def clear_grab(self):
        '''
        Remove all grab_input callbacks
        '''
        del self.grab_input_callbacks[:]

    def grab_input(self, cb):
        '''
        Registers a callback to preferentially receive user input.
        The callback takes a single argument, the character input value.
        It returns a boolean: True to maintain input grab; False to remove
        itself from the grab list.
        '''
        self.grab_input_callbacks.append(cb)

    def prompt_confirmation(self, msg, cb):
        '''
        Prompts for a yes or no response. If input 'y' is received,
        the given callback is called with no arguments. If any other
        input is received, input grab is released and nothing is called.
        '''
        self.set_message(msg + ' (y/n)', None)
        self.grab_input(partial(self.confirm_callback, cb = cb))

    def confirm_callback(self, ch, cb):
        '''
        Input grab callback used by prompt_confirmation.
        '''
        if ch == ord('y'):
            cb()
        self.clear_message()
        return False

    def clear_message(self):
        '''
        Clears message line
        '''
        self.message = None
        self.message_timeout = None
        self.queue_redraw = True

    def set_message(self, msg, timeout = 1):
        '''
        Sets a message to display for the given timeout, in seconds.
        If timeout is None, the message will be displayed until clear_message
        is called.
        '''
        self.message = msg
        if timeout is None:
            self.message_timeout = None
        else:
            self.message_timeout = time.time() + timeout
        self.queue_redraw = True

    def draw(self):
        '''
        Draws the contents of the screen
        '''
        win = self.stdscr

        y, x = win.getmaxyx()
        win.clear()

        try:
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
        except curses.error as e:
            msg = 'Screen is too small'
            self.draw_line(y - 1, 0, msg[:x], curses.A_BOLD)
            win.refresh()

    def draw_field(self, y, x):
        raise NotImplementedError

    def time_str(self):
        '''Returns a string "minutes:seconds" for the current timer'''
        if self.paused:
            t = self.pause_time - self.time_offset
        else:
            t = time.time() - self.time_offset
        return '{:d}:{:02d}'.format(*divmod(int(t), 60))

    def draw_clock(self, y, x):
        '''Draws the timer on the screen'''
        s = self.time_str()
        self.stdscr.addstr(0, x - len(s) - 1, s, curses.A_REVERSE)

    def draw_message(self, y, x):
        '''Draws message'''
        win = self.stdscr
        if self.message:
            win.addstr(y - 1, 0, self.message, curses.A_BOLD)

    def draw_pause(self, y, x):
        '''Draws the pause screen'''
        if self.pause_draw_callback is None:
            self.draw_centered(y // 2, x, 'Paused')
        else:
            self.pause_draw_callback(y, x)

    def draw_stopped(self, y, x):
        '''Draws the game over screen'''
        self.draw_centered(y // 2, x, 'You won!', curses.A_BOLD)

    def draw_centered(self, y, x, s, attr = 0):
        '''
        Draws a string centered on the screen.
        y is line to draw, x is the max x value of the screen.
        '''
        self.stdscr.addstr(y, (x - len(s)) // 2, s, attr)

    def draw_line(self, y, x, s, attr = 0):
        self.stdscr.addstr(y, x, s, attr)

    def draw_title(self, y, x):
        '''Draws the title to the screen'''
        self.stdscr.addstr(0, 1, self.GAME_TITLE)
        self.stdscr.chgat(0, 0, x, curses.A_REVERSE)

    def go(self):
        self.init_ui()
        self.start_game()

        while not self.quit:
            self.before_tick()

            if self.queue_redraw:
                self.draw()
                self.queue_redraw = False
            elif not (self.paused or self.stopped):
                self.draw_clock(*self.stdscr.getmaxyx())
                self.refresh()

            self.handle_input()

            self.after_tick()

        self.end_game()

    def after_tick(self):
        if self.message_timeout and self.message_timeout <= time.time():
            self.clear_message()

    def before_tick(self):
        pass

    def end_game(self):
        pass

    def handle_input(self):
        ch = self.stdscr.getch()

        if ch == -1:
            return

        if self.grab_input_callbacks:
            cb = self.grab_input_callbacks[-1]
            if not cb(ch):
                self.grab_input_callbacks.pop()
        else:
            cb = self.key_callbacks.get(ch)
            if cb:
                cb()

    def init_ui(self):
        self.stdscr.timeout(100)
        curses.curs_set(0)
        curses.noecho()
        signal.signal(signal.SIGWINCH, self.win_resized)
        self.init_colors()

    def init_colors(self):
        curses.start_color()
        curses.use_default_colors()

    def toggle_pause(self):
        if self.paused:
            self.unpause_game()
        else:
            self.pause_game()

    def pause_game(self, grab = None, draw = None):
        if not self.paused:
            self.pause_time = time.time()
            self.paused = True
            self.grab_input(self.pause_callback if grab is None else grab)
            self.pause_draw_callback = draw
            self.queue_redraw = True

    def pause_callback(self, ch):
        if ch == ord('p'):
            self.unpause_game()
            return False
        elif ch == ord('q'):
            self.confirm_quit_game()

        return True

    def unpause_game(self):
        if self.paused:
            self.time_offset = time.time() - (self.pause_time - self.time_offset)
            self.paused = False
            self.queue_redraw = True

    def confirm_new_game(self):
        self.prompt_confirmation('Start a new game?', self.new_game)

    def new_game(self):
        raise NotImplementedError

    def confirm_quit_game(self):
        self.prompt_confirmation('Quit game?', self.quit_game)

    def quit_game(self):
        self.quit = True

    def start_game(self):
        raise NotImplementedError

    def redraw(self):
        self.queue_redraw = True

    def refresh(self):
        self.stdscr.refresh()

    def win_resized(self, *args):
        curses.endwin()
        curses.initscr()
        self.queue_redraw = True
