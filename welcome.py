#!/usr/bin/env python3

# 48x14 terminal?

import contextlib


def create_canvas():
    import tkinter

    PAD_L = PAD_R = PAD_B = 32
    PAD_T = 128

    window = tkinter.Tk()
    window.overrideredirect(True)
    window.wm_attributes('-topmost', True)
    window.wm_attributes('-transparent', True)
    window.config(bg='systemTransparent')
    window.geometry(f'+{PAD_L}+{PAD_T}')
    window.lift()
    canvas_w = window.winfo_screenwidth() - PAD_L - PAD_R
    canvas_h = window.winfo_screenheight() - PAD_T - PAD_B
    canvas = tkinter.Canvas(
        window,
        width=canvas_w,
        height=canvas_h,
        bg='systemTransparent',
        bd=0,
        highlightthickness=0,
    )
    canvas.pack()
    return canvas


@contextlib.contextmanager
def tui_gui():
    import termios
    import types
    import tty
    import shutil
    import sys

    SCREEN_ALT = b'\x1b[?1049h'
    SCREEN_REGULAR = b'\x1b[?1049l'
    SCREEN_CLEAR = b'\x1b[2J'
    CURSOR_HIDE = b'\x1b[?25l'
    CURSOR_SHOW = b'\x1b[?25h'
    CURSOR_TOP_LEFT = b'\x1b[H'
    TERM_SETUP = CURSOR_HIDE + SCREEN_ALT + SCREEN_CLEAR + CURSOR_TOP_LEFT
    TERM_RESET = SCREEN_REGULAR + CURSOR_SHOW

    def write_raw(b):
        sys.stdout.buffer.raw.write(b)

    def write(t):
        sys.stdout.write(t)
        sys.stdout.flush()

    def write_at(col, line, text, *, fg=None, bg=None):
        colors = (f"\033[38;5;{fg}m" if fg else "") + (f"\033[48;5;{bg}m" if bg else "")
        seq = f"\033[s\033[{line};{col}H{colors}{text}\033[0m\033[u"
        sys.stdout.write(seq)
        sys.stdout.flush()

    stage = types.SimpleNamespace()
    stage.canvas = create_canvas()
    stage.read_raw = sys.stdin.buffer.raw.read
    stage.write = write
    stage.write_at = write_at
    stage.clear = lambda: write_raw(SCREEN_CLEAR + CURSOR_TOP_LEFT)
    stage.columns, stage.lines = shutil.get_terminal_size()

    orig_settings = termios.tcgetattr(sys.stdin)
    try:
        write_raw(TERM_SETUP)
        tty.setraw(sys.stdin.fileno())
        yield stage
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, orig_settings)
        write_raw(TERM_RESET)
        stage.canvas.winfo_toplevel().destroy()


def drive_slides(slides, *, countdown_seconds):
    import time

    KEY_NEXT = b'n'
    KEY_PREV = b'N'
    KEY_CTRL_C = b'\x03'

    end_seconds = int(time.time()) + int(countdown_seconds)
    def show_remaining_time(stage):
        seconds_remaining = end_seconds - int(time.time())
        minutes, seconds = divmod(seconds_remaining, 60)
        text = f' {minutes:02d}:{seconds:02d} '
        x = stage.columns - len(text) + 1
        y = stage.lines
        fg, bg = (250, None) if seconds_remaining > 60 else (231, 196)
        stage.write_at(x, y, text, fg=fg, bg=bg)

    slide_count = len(slides)
    slide_index = 0
    with tui_gui() as stage:
        next(slide_run := slides[slide_index](stage))
        slide_start = True
        show_remaining_time(stage)
        while (input_byte := stage.read_raw(1)) != KEY_CTRL_C:
            show_remaining_time(stage)
            delta = None
            if input_byte == KEY_NEXT and slide_run:
                try:
                    next(slide_run)
                    slide_start = False
                except StopIteration:
                    slide_run = None
                continue
            elif input_byte == KEY_NEXT:
                delta = 1
            elif input_byte == KEY_PREV:
                delta = -1 if slide_start else 0
            if delta is None:
                continue
            if 0 <= slide_index + delta < slide_count:
                slide_index += delta
                next(slide_run := slides[slide_index](stage))
                slide_start = True
                show_remaining_time(stage)


def clean_slate(slide_painter):
    def wrapper(stage, *args, **kwargs):
        stage.canvas.delete('all')
        stage.canvas.update()
        stage.clear()
        yield from slide_painter(stage, *args, **kwargs)
    return wrapper


@clean_slate
def paint_slide(stage, n):
    from random import randint
    stage.write(f'slide #{n}')
    yield
    w = stage.canvas.winfo_width()
    h = stage.canvas.winfo_height()
    for _ in range(42):
        stage.canvas.create_line(
            randint(0, w),
            randint(0, h),
            randint(0, w),
            randint(0, h),
            width=8,
            fill=f'#20{randint(64, 192):02x}{randint(128, 255):02x}',
        )
    stage.canvas.update()
    yield
    stage.write('\r\n\nsopa de cebola')


SLIDES = (
    lambda stage: paint_slide(stage, 1),
    lambda stage: paint_slide(stage, 2),
)

if __name__ == '__main__':

    drive_slides(SLIDES, countdown_seconds=5*60)

