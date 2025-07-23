#!/usr/bin/env python3

# 48x14 terminal?

import contextlib
import dataclasses
import itertools
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
    scale: float = 1.0
    dx: int = 0
    dy: int = 0

    def x(self, x):
        return ((x + 9.48) * self.scale * 3000) + 50 + self.dx

    def y(self, y):
        return ((38.8 - y) * self.scale * 3000) + 200 + self.dy


def draw_lines(stage, filepath, *, names=None, width=4, fill='#000000', transform=None):
    transform = T(scale=1.0, dx=0, dy=0) if transform is None else transform
    with open(filepath, 'rt') as f:
        data = json.load(f)
    object_ids = []
    for feature in data['features']:
        if names and feature['properties']['name'] not in names:
            continue
        canvas_coords = (
            (transform.x(lon), transform.y(lat))
            for lon, lat in feature['geometry']['coordinates']
        )
        object_id = stage.canvas.create_line(*canvas_coords, width=width, fill=fill)
        object_ids.append(object_id)
    stage.canvas.update()
    return object_ids


def draw_points(stage, filepath, names=None, *, radius=16, width=4, fill='#000000', transform=None):
    transform = T(scale=1.0, dx=0, dy=0) if transform is None else transform
    with open(filepath, 'rt') as f:
        data = json.load(f)
    object_ids = []
    for feature in data['features']:
        name = feature['properties']['name']
        if names and name not in names:
            continue
        lon, lat = feature['geometry']['coordinates']
        canvas_x = transform.x(lon)
        canvas_y = transform.y(lat)
        canvas_coords = (canvas_x - radius, canvas_y - radius, canvas_x + radius, canvas_y + radius)
        object_id = stage.canvas.create_oval(*canvas_coords, width=width, fill=fill)
        draw_text(stage, canvas_x, canvas_y + radius * 1.5, text=name)
        object_ids.append(object_id)
    stage.canvas.update()
    return object_ids


TEXT_BG_OFFSETS = list(itertools.product((-1, 0, 1), (-1, 0, 1)))
TEXT_BG_OFFSETS.remove((0, 0))

def draw_text(stage, x, y, *, bg='white', fg='black', text):
    for dx, dy in TEXT_BG_OFFSETS:
        stage.canvas.create_text(x + dx, y + dy, fill=bg, text=text)
    stage.canvas.create_text(x, y, fill=fg, text=text)


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
    draw_points(stage, filepath, names=stations, fill=fill, transform=transform)


def draw_pyconpt2025(stage, *, transform=None):
    transform = T(scale=1.0, dx=0, dy=0) if transform is None else transform
    with open(THIS_DIR / 'gis' / 'points-of-interest.geojson', 'rt') as f:
        points = json.load(f)
    with open(THIS_DIR / 'images' / 'python-logo.json', 'rt') as f:
        logo = json.load(f)
    lon, lat = [
        x['geometry']['coordinates']
        for x in points['features'] 
        if x['properties']['name'] == 'PyConPT 2025'
    ][0]
    canvas_x = transform.x(lon)
    canvas_y = transform.y(lat)
    blue = [(canvas_x + x, canvas_y + y) for x, y in logo['blue']]
    stage.canvas.create_polygon(blue, fill='#306998', outline='black')
    yellow = [(canvas_x + x, canvas_y + y) for x, y in logo['yellow']]
    stage.canvas.create_polygon(yellow, fill='#ffd43b', outline='black')
    stage.canvas.update()


def slide_title(stage, title_text):
    BOLD = '\033[1m'
    NORMAL = '\033[0m'
    underline = '⎺' * len(title_text)
    stage.write(f"\n  {BOLD}{title_text}{NORMAL}\r\n  {underline}\r\n")


@clean_slate
def hello(stage):
    transform = T()
    slide_title(stage, "local self")
    yield
    stage.write("  🙋  I'm Tiago️\r\n")
    yield
    stage.write("  📍  Living here since forever\r\n")
    yield
    stage.write("  🗺   Unique tips for exploring the area\r\n")
    yield
    draw_coastline(stage, transform=transform)
    yield
    draw_trainline(stage, transform=transform)
    draw_trainstations(stage, stations={'cascais', 'cais do sodré'}, transform=transform)
    yield
    draw_pyconpt2025(stage, transform=transform)
    yield
    draw_trainstations(stage, stations={'carcavelos'}, transform=transform)


def draw_santini(stage, *, transform):
    filepath = THIS_DIR / 'gis' / 'points-of-interest.geojson'
    names = {'Santini'}
    draw_points(stage, filepath, names=names, fill='yellow', transform=transform)
    filepath = THIS_DIR / 'gis' / 'lines-of-interest.geojson'
    names = {'nova-santini'}
    object_ids = draw_lines(stage, filepath, names=names, fill='#ff8000', transform=transform)
    for object_id in object_ids:
        stage.canvas.lower(object_id)
    stage.canvas.update()


@clean_slate
def icecream(stage):
    transform = T(scale=7.7, dx=-3000, dy=-2400)
    draw_coastline(stage, transform=transform)
    draw_trainline(stage, transform=transform)
    draw_trainstations(stage, stations={'carcavelos'}, transform=transform)
    draw_pyconpt2025(stage, transform=transform)
    yield
    slide_title(stage, "icecream 🍦")
    yield
    stage.write("  👶 I'm a client since I was three\r\n")
    stage.write("  📅 Est. in the 1960's in Estoril (now a franchise)\r\n")
    stage.write("  👑 Served King Humberto II of Italy\r\n")
    yield
    draw_santini(stage, transform=transform)
    stage.write_at(14, 2, ' @ Santini')
    stage.write_at(13, 3, '⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺')
    yield
    stage.write("  🍓 Fruit flavours are the best\r\n")
    stage.write("     (strawberry, hazelnut, mango, melon, ...)\r\n")
    yield
    stage.write("  ⁉️  Still the 2nd best in the world?\r\n")
    stage.write_at(26, 14, "15-20m walk", fg=250)


SLIDES = (
    # hello,
    icecream,
)

if __name__ == '__main__':

    drive_slides(SLIDES, countdown_seconds=5*60)

