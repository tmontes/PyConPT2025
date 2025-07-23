#!/usr/bin/env python3

# 48x14 terminal?

import contextlib
import dataclasses
import json
import pathlib


THIS_DIR = pathlib.Path(__file__).parent


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


@dataclasses.dataclass
class T:
    scale: float
    dx: int
    dy: int


def draw_lines(stage, filepath, *, names=None, width=4, fill='#000000', transform=None):
    transform = T(scale=1.0, dx=0, dy=0) if transform is None else transform
    with open(filepath, 'rt') as f:
        data = json.load(f)
    object_ids = []
    for feature in data['features']:
        if names and feature['properties']['name'] not in names:
            continue
        canvas_coords = (
            (
                ((x + 9.48) * transform.scale * 3000) + 50 + transform.dx,
                ((38.8 - y) * transform.scale * 3000) + 200 + transform.dy
            )
            for x, y in feature['geometry']['coordinates']
        )
        object_id = stage.canvas.create_line(*canvas_coords, width=width, fill=fill)
        object_ids.append(object_id)
    stage.canvas.update()
    return object_ids


def draw_points(stage, filepath, names, *, radius=16, width=4, fill='#000000', transform=None):
    transform = T(scale=1.0, dx=0, dy=0) if transform is None else transform
    with open(filepath, 'rt') as f:
        data = json.load(f)
    object_ids = []
    for feature in data['features']:
        name = feature['properties']['name']
        if names and name not in names:
            continue
        x, y = feature['geometry']['coordinates']
        canvas_x = ((x + 9.48) * transform.scale * 3000) + 50 + transform.dx
        canvas_y = ((38.8 - y) * transform.scale * 3000) + 200 + transform.dy
        canvas_coords = (canvas_x - radius, canvas_y - radius, canvas_x + radius, canvas_y + radius)
        object_id = stage.canvas.create_oval(*canvas_coords, width=width, fill=fill)
        stage.canvas.create_text(canvas_x, canvas_y + radius * 1.5, text=name)
        object_ids.append(object_id)
    stage.canvas.update()
    return object_ids


def draw_coastline(stage, *, transform=None):
    filepath = THIS_DIR / 'gis' / 'coastline.geojson'
    names = {'norte', 'sul'}
    fill = '#00d0ff'
    return draw_lines(stage, filepath, names=names, fill=fill, transform=transform)


def draw_trainline(stage, *, transform=None):
    filepath = THIS_DIR / 'gis' / 'trainline.geojson'
    width = 8
    fill = '#000000'
    draw_lines(stage, filepath, width=width, fill=fill, transform=transform)


def draw_trainstations(stage, *, stations=None, transform=None):
    filepath = THIS_DIR / 'gis' / 'train-stations.geojson'
    fill = '#c0c0c0'
    draw_points(stage, filepath, names=stations, fill=fill)


def draw_pyconpt2025(stage):
    scale = 1.5
    offset_x, offset_y = 260, 260

    with open(THIS_DIR / 'images' / 'python-logo.json', 'rt') as f:
        data = json.load(f)

    stage.canvas.create_polygon(data['blue'], fill='#306998')
    stage.canvas.create_polygon(data['yellow'], fill='#ffd43b')
    stage.canvas.update()


BOLD = '\033[1m'
NORMAL = '\033[0m'

@clean_slate
def hello(stage):
    stage.write("\n")
    stage.write(f"  {BOLD}local self{NORMAL}\r\n")
    stage.write("  ----------\r\n")
    yield
    stage.write("  🙋  I'm Tiago️\r\n")
    yield
    stage.write("  📍  Living here since forever\r\n")
    yield
    stage.write("  🗺   Unique tips for exploring the area\r\n")
    yield
    draw_coastline(stage)
    yield
    draw_trainline(stage)
    draw_trainstations(stage, stations={'cascais', 'cais do sodré'})
    yield
    draw_trainstations(stage, stations={'carcavelos'})
    draw_pyconpt2025(stage)


SLIDES = (
    hello,
)

if __name__ == '__main__':

    drive_slides(SLIDES, countdown_seconds=5*60)

