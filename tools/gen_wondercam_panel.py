#!/usr/bin/env python3
# =================================================================================================
#
#   File....... gen_wondercam_panel.py
#   Purpose.... Generate the WonderCam front-panel DEBUG-PLOT artwork (BMP layers) AND print the
#               matching Spin2 CON layout block, so the art and the demo code share ONE source of
#               truth and cannot drift.  (Sprint plan section 8 / spec section 6.2.)
#   Authors.... Stephen M Moraco / Claude Code
#   E-mail..... stephen@ironsheep.biz
#
#   Outputs (written next to the Spin2 source, in ../src/):
#     wc_panel_bg.bmp  - static panel: header, camera-view frame, side-panel labels, footer help.
#     wc_font.bmp      - horizontal digit/glyph strip (Pattern B): "0123456789-+. " on PANEL_BG.
#     wc_modes.bmp     - vertical mode-name strip (Pattern A/B): 12 rows, srcY = funcId * cell_h.
#     wc_led.bmp       - 2-cell LED-state strip: off | on, srcX = state * cell_w, on HEADER_BG.
#
#   All BMPs are 24-bit, uncompressed (BI_RGB), NO alpha - the only format DEBUG `LAYER` accepts.
#   Pillow's Image.new("RGB", ...).save("x.bmp") produces exactly that.
#
#   Dependency: Pillow (PIL).  In the Linux dev container:  sudo apt-get install -y python3-pil
#               On the macOS host:  pip3 install Pillow  (or use sips-based regeneration).
#
#   Re-run after any layout change, paste the printed CON block into src/demo_wondercam.spin2,
#   then recompile.  Verify art without a viewer by converting BMP->PNG:
#     python3 -c "from PIL import Image; Image.open('src/wc_panel_bg.bmp').save('/tmp/x.png')"
#
# =================================================================================================

import os
from PIL import Image, ImageDraw, ImageFont

# -------------------------------------------------------------------------------------------------
# LAYOUT - the single source of truth.  Every number a CROP coordinate depends on is defined here
# ONCE, used to draw the art, and emitted as a Spin2 CON block at the end.
# -------------------------------------------------------------------------------------------------

# Window
WIN_W = 480
WIN_H = 320

# Layer numbers (also the order they are loaded in setup()).  Kept as documentation; the DEBUG
# commands themselves use literal layer numbers (the reference-display idiom).
LAYER_BG   = 1
LAYER_FONT = 2
LAYER_MODE = 3
LAYER_LED  = 4

# Bands
HEADER_H = 30
FOOTER_H = 30

# Camera-view region (left) - the live detection field that the per-mode views (section 9) draw into
VIEW_X = 8
VIEW_Y = 38
VIEW_W = 304
VIEW_H = 240

# Side panel x-origin (right of the camera view)
PANEL_X = 320

# Mode-name strip cell (blitted into the side panel); srcY = funcId * MODE_CELL_H
MODE_SLOT_X = PANEL_X
MODE_SLOT_Y = 48
MODE_CELL_W = 152
MODE_CELL_H = 24

# Digit/glyph font strip; srcX = glyphIndex * DIG_W, srcY = 0
DIG_W = 16
DIG_H = 24
GLYPHS = "0123456789-+. "            # index 0..9 digits, 10='-', 11='+', 12='.', 13=' ' (blank)
GLYPH_MINUS = 10
GLYPH_PLUS  = 11
GLYPH_DOT   = 12
GLYPH_BLANK = 13

# Echo readout (the live device-reported active-function number) - a right-aligned 2-digit field
ECHO_X = 384
ECHO_Y = 82
ECHO_DIGITS = 2

# LED-state strip cell (in the header); srcX = ledState * LED_W
LED_SLOT_X = 426
LED_SLOT_Y = 6
LED_W = 44
LED_H = 20

# Generic info readout slots (side panel, lower) - the per-mode views (section 9) draw here
INFO_X      = PANEL_X
INFO_Y      = 120
INFO_LINE_H = 28
INFO_RMARGIN = 8                     # right margin from the window edge
INFO_W = WIN_W - INFO_X - INFO_RMARGIN          # erase/draw width of the info area
INFO_H = (WIN_H - FOOTER_H - 2) - INFO_Y        # erase/draw height (down to just above the footer)

# Mode names indexed by funcId 0..11 (FUNC_NONE .. FUNC_LANDMARK).  Order MUST match the driver's
# func-number enum in src/isp_wondercam.spin2 (FUNC_NONE=0 .. FUNC_LANDMARK=11).
MODE_NAMES = [
    "IDLE",        # 0  FUNC_NONE
    "FACE",        # 1  FUNC_FACE
    "OBJECT",      # 2  FUNC_OBJECT
    "CLASSIFY",    # 3  FUNC_CLASSIFY
    "FEATURE",     # 4  FUNC_FEATURE
    "COLOR",       # 5  FUNC_COLOR
    "LINE",        # 6  FUNC_LINE
    "APRILTAG",    # 7  FUNC_APRILTAG
    "QR CODE",     # 8  FUNC_QRCODE
    "BARCODE",     # 9  FUNC_BARCODE
    "NUMBER",      # 10 FUNC_NUMBER
    "ROAD SIGN",   # 11 FUNC_LANDMARK
]
MODE_COUNT = len(MODE_NAMES)         # 12 rows

# -------------------------------------------------------------------------------------------------
# Palette - colors are shared between art regions and sprite-cell backgrounds so opaque blits
# leave NO seam (24-bit BMP has no alpha; every CROP overwrites a rectangle).
# -------------------------------------------------------------------------------------------------
PANEL_BG  = (28, 28, 36)             # window body + font/mode cell backgrounds
HEADER_BG = (44, 44, 58)             # header + footer band + LED cell background
VIEW_BG   = (8, 8, 12)              # camera-view interior
FRAME     = (90, 90, 120)            # border / divider lines
TEXT      = (220, 220, 230)          # labels and footer help
TITLE_CLR = (120, 200, 255)          # panel title
DIGIT_CLR = (80, 230, 120)           # numeric readout glyphs
MODE_CLR  = (245, 210, 120)          # mode-name text
LED_OFF   = (70, 40, 40)             # LED indicator body, off
LED_ON    = (60, 220, 90)            # LED indicator body, on
LED_RING  = (110, 110, 130)          # LED bezel ring

# -------------------------------------------------------------------------------------------------
# Font loading - prefer a TrueType face for legibility; fall back to Pillow's bitmap default.
# -------------------------------------------------------------------------------------------------
_TTF_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def get_font(size):
    for path in _TTF_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)   # raises if the path is missing -> try the next
        except Exception:
            pass
    return ImageFont.load_default()


def text_size(draw, s, font):
    # Pillow >=8 has textbbox; older has textsize. Use bbox when present.
    if hasattr(draw, "textbbox"):
        x0, y0, x1, y1 = draw.textbbox((0, 0), s, font=font)
        return (x1 - x0, y1 - y0, x0, y0)
    w, h = draw.textsize(s, font=font)
    return (w, h, 0, 0)


def draw_centered(draw, cx, cy, s, font, fill):
    w, h, ox, oy = text_size(draw, s, font)
    draw.text((cx - w / 2 - ox, cy - h / 2 - oy), s, font=font, fill=fill)


# -------------------------------------------------------------------------------------------------
# Art builders
# -------------------------------------------------------------------------------------------------

def build_background():
    img = Image.new("RGB", (WIN_W, WIN_H), PANEL_BG)
    d = ImageDraw.Draw(img)
    label_font = get_font(13)
    title_font = get_font(16)
    small_font = get_font(12)

    # Header band
    d.rectangle([0, 0, WIN_W - 1, HEADER_H - 1], fill=HEADER_BG)
    d.line([0, HEADER_H - 1, WIN_W - 1, HEADER_H - 1], fill=FRAME)
    d.text((8, 7), "WONDERCAM FRONT PANEL", font=title_font, fill=TITLE_CLR)

    # Footer band + help text
    fy = WIN_H - FOOTER_H
    d.rectangle([0, fy, WIN_W - 1, WIN_H - 1], fill=HEADER_BG)
    d.line([0, fy, WIN_W - 1, fy], fill=FRAME)
    d.text((8, fy + 9), "[SPACE/n] next  [p] prev  [l] LED  [ESC] quit",
           font=small_font, fill=TEXT)

    # Camera-view interior + frame
    d.rectangle([VIEW_X, VIEW_Y, VIEW_X + VIEW_W - 1, VIEW_Y + VIEW_H - 1], fill=VIEW_BG)
    d.rectangle([VIEW_X - 2, VIEW_Y - 2, VIEW_X + VIEW_W + 1, VIEW_Y + VIEW_H + 1],
                outline=FRAME)
    d.text((VIEW_X + 2, VIEW_Y - 16), "CAMERA VIEW", font=small_font, fill=TEXT)

    # Side-panel labels
    d.text((PANEL_X, MODE_SLOT_Y - 15), "MODE", font=label_font, fill=TEXT)
    d.text((PANEL_X, ECHO_Y + 4), "ECHO", font=label_font, fill=TEXT)

    img.save(bmp_path("wc_panel_bg.bmp"))


def build_font_strip():
    n = len(GLYPHS)
    img = Image.new("RGB", (n * DIG_W, DIG_H), PANEL_BG)
    d = ImageDraw.Draw(img)
    font = get_font(20)
    for i, ch in enumerate(GLYPHS):
        if ch != " ":
            draw_centered(d, i * DIG_W + DIG_W / 2, DIG_H / 2, ch, font, DIGIT_CLR)
    img.save(bmp_path("wc_font.bmp"))


def build_mode_strip():
    img = Image.new("RGB", (MODE_CELL_W, MODE_COUNT * MODE_CELL_H), PANEL_BG)
    d = ImageDraw.Draw(img)
    font = get_font(16)
    for i, name in enumerate(MODE_NAMES):
        cy = i * MODE_CELL_H + MODE_CELL_H / 2
        draw_centered(d, MODE_CELL_W / 2, cy, name, font, MODE_CLR)
    img.save(bmp_path("wc_modes.bmp"))


# LED-cell cosmetic geometry (internal to the strip art; not part of the emitted CON layout)
LED_BEZEL_PAD   = 6                  # vertical inset of the indicator circle within the cell
LED_DOT_INSET_X = 4                  # circle left margin from the cell edge
LED_LABEL_RATIO = 0.62               # label center as a fraction of the cell width


def build_led_strip():
    img = Image.new("RGB", (2 * LED_W, LED_H), HEADER_BG)
    d = ImageDraw.Draw(img)
    font = get_font(12)
    r = (LED_H - LED_BEZEL_PAD) // 2
    cy = LED_H // 2
    for state, (body, label) in enumerate(((LED_OFF, "OFF"), (LED_ON, "ON"))):
        ox = state * LED_W
        cx = ox + r + LED_DOT_INSET_X
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=body, outline=LED_RING)
        draw_centered(d, ox + LED_W * LED_LABEL_RATIO, cy, label, font, TEXT)
    img.save(bmp_path("wc_led.bmp"))


# -------------------------------------------------------------------------------------------------
# Paths + Spin2 CON emission
# -------------------------------------------------------------------------------------------------

def src_dir():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "src"))


def bmp_path(name):
    return os.path.join(src_dir(), name)


def print_con_block():
    lines = [
        "con { ===== panel layout - GENERATED by tools/gen_wondercam_panel.py, do not hand-edit ===== }",
        "",
        "  ' Window geometry",
        f"  WIN_W = {WIN_W}",
        f"  WIN_H = {WIN_H}",
        "",
        "  ' Layer numbers (load order). DEBUG commands use literal layer numbers; these document them.",
        f"  LAYER_BG   = {LAYER_BG}                                            ' wc_panel_bg.bmp - static panel",
        f"  LAYER_FONT = {LAYER_FONT}                                            ' wc_font.bmp     - digit/glyph strip",
        f"  LAYER_MODE = {LAYER_MODE}                                            ' wc_modes.bmp    - mode-name strip",
        f"  LAYER_LED  = {LAYER_LED}                                            ' wc_led.bmp      - LED-state strip",
        "",
        "  ' Camera-view region (per-mode views from section 9 draw here)",
        f"  VIEW_X = {VIEW_X}",
        f"  VIEW_Y = {VIEW_Y}",
        f"  VIEW_W = {VIEW_W}",
        f"  VIEW_H = {VIEW_H}",
        "",
        "  ' Mode-name strip cell - srcY = funcId * MODE_CELL_H, srcX = 0",
        f"  MODE_SLOT_X = {MODE_SLOT_X}",
        f"  MODE_SLOT_Y = {MODE_SLOT_Y}",
        f"  MODE_CELL_W = {MODE_CELL_W}",
        f"  MODE_CELL_H = {MODE_CELL_H}",
        "",
        "  ' Digit/glyph font strip - srcX = glyphIndex * DIG_W, srcY = 0",
        f"  DIG_W = {DIG_W}",
        f"  DIG_H = {DIG_H}",
        f"  GLYPH_MINUS = {GLYPH_MINUS}",
        f"  GLYPH_PLUS  = {GLYPH_PLUS}",
        f"  GLYPH_DOT   = {GLYPH_DOT}",
        f"  GLYPH_BLANK = {GLYPH_BLANK}",
        "",
        "  ' Echo readout (live device mode-echo number) - right-aligned ECHO_DIGITS-wide field",
        f"  ECHO_X = {ECHO_X}",
        f"  ECHO_Y = {ECHO_Y}",
        f"  ECHO_DIGITS = {ECHO_DIGITS}",
        "",
        "  ' LED-state strip cell (header) - srcX = ledState * LED_W, srcY = 0",
        f"  LED_SLOT_X = {LED_SLOT_X}",
        f"  LED_SLOT_Y = {LED_SLOT_Y}",
        f"  LED_W = {LED_W}",
        f"  LED_H = {LED_H}",
        "",
        "  ' Generic info readout area (side panel, lower) - the section 9 per-mode readouts draw here",
        f"  INFO_X      = {INFO_X}",
        f"  INFO_Y      = {INFO_Y}",
        f"  INFO_W      = {INFO_W}",
        f"  INFO_H      = {INFO_H}",
        f"  INFO_LINE_H = {INFO_LINE_H}",
    ]
    print("\n".join(lines))


def main():
    os.makedirs(src_dir(), exist_ok=True)
    build_background()
    build_font_strip()
    build_mode_strip()
    build_led_strip()
    print("# wrote 4 BMP layers to %s" % src_dir())
    print("# --- paste the block below into src/demo_wondercam.spin2 ---")
    print_con_block()


if __name__ == "__main__":
    main()
