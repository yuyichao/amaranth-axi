#

from amaranth import *
from amaranth.lib.data import StructLayout, View

from pathlib import Path

rtl_dir = Path(__file__).parent / "rtl"

def add_verilog_file(plat, file_name):
    if file_name not in plat.extra_files:
        with (rtl_dir / file_name).open('rb') as f:
            plat.add_file(file_name, f.read())

def add_verilog_files(plat, file_names):
    if plat is not None:
        for d in file_names:
            add_verilog_file(plat, d)

def cast_to_width(s, width, allow_trunc=False):
    s = Value.cast(s)
    l = len(s)
    if l == width:
        return s
    elif l > width:
        if not allow_trunc:
            raise TypeError("Signal truncation not allowed")
        return s[:width]
    else:
        return Cat(s, Signal(width - l))

def StructCat(layout=None, /, **kws):
    if layout is None:
        fields = dict()
        for (k, v) in kws.items():
            fields[k] = v.shape()
        layout = StructLayout(fields)

    signals = []
    for (k, v) in kws.items():
        signals.append(cast_to_width(v, Shape.cast(layout.members[k]).width))

    return View(layout, Cat(signals))
