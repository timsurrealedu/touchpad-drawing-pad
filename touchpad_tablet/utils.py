"""Linux kernel input subsystem definitions, ioctls, and ctypes structures."""

import ctypes
import os
import fcntl

# Event Types (<linux/input-event-codes.h>)
EV_SYN = 0x00
EV_KEY = 0x01
EV_REL = 0x02
EV_ABS = 0x03
EV_MSC = 0x04
EV_SW  = 0x05

# Synchronization Events
SYN_REPORT    = 0
SYN_CONFIG    = 1
SYN_MT_REPORT = 2
SYN_DROPPED   = 3

# Absolute Axes (<linux/input-event-codes.h>)
ABS_X          = 0x00
ABS_Y          = 0x01
ABS_Z          = 0x02
ABS_RX         = 0x03
ABS_RY         = 0x04
ABS_RZ         = 0x05
ABS_PRESSURE   = 0x18
ABS_DISTANCE   = 0x19
ABS_TILT_X     = 0x1a
ABS_TILT_Y     = 0x1b

# Multi-touch Axes
ABS_MT_SLOT        = 0x2f
ABS_MT_TOUCH_MAJOR = 0x30
ABS_MT_TOUCH_MINOR = 0x31
ABS_MT_WIDTH_MAJOR = 0x32
ABS_MT_WIDTH_MINOR = 0x33
ABS_MT_ORIENTATION = 0x34
ABS_MT_POSITION_X  = 0x35
ABS_MT_POSITION_Y  = 0x36
ABS_MT_TOOL_TYPE   = 0x37
ABS_MT_BLOB_ID     = 0x38
ABS_MT_TRACKING_ID = 0x39
ABS_MT_PRESSURE    = 0x3a
ABS_MT_DISTANCE    = 0x3b

# Key & Button Codes (<linux/input-event-codes.h>)
BTN_LEFT       = 0x110
BTN_RIGHT      = 0x111
BTN_MIDDLE     = 0x112
BTN_TOOL_PEN   = 0x140
BTN_TOOL_RUBBER= 0x141
BTN_TOOL_BRUSH = 0x142
BTN_TOOL_PENCIL= 0x143
BTN_TOOL_AIRBRUSH = 0x144
BTN_TOOL_FINGER= 0x145
BTN_TOOL_MOUSE = 0x146
BTN_TOOL_LENS  = 0x147
BTN_TOUCH      = 0x14a
BTN_STYLUS     = 0x14b
BTN_STYLUS2    = 0x14c

# Device Properties
INPUT_PROP_POINTER   = 0x00
INPUT_PROP_DIRECT    = 0x01
INPUT_PROP_BUTTONPAD = 0x02
INPUT_PROP_SEMI_MT   = 0x03
INPUT_PROP_TOPBUTTONPAD = 0x04
INPUT_PROP_POINTING_STICK = 0x05
INPUT_PROP_ACCELEROMETER = 0x06

# Bus Types
BUS_PCI     = 0x01
BUS_ISAPNP  = 0x02
BUS_USB     = 0x03
BUS_HIL     = 0x04
BUS_BLUETOOTH = 0x05
BUS_VIRTUAL = 0x06
BUS_I2C     = 0x18
BUS_SPI     = 0x1c

# Evdev IOCTL Definitions (_IOC macro based)
# _IOC_NONE = 0, _IOC_WRITE = 1, _IOC_READ = 2
def _IOC(dir_, type_, nr, size):
    return (dir_ << 30) | (size << 16) | (type_ << 8) | nr

def _IOR(type_, nr, size):
    return _IOC(2, type_, nr, size)

def _IOW(type_, nr, size):
    return _IOC(1, type_, nr, size)

def _IO(type_, nr):
    return _IOC(0, type_, nr, 0)

# EVIOCGRAB: exclusive grab (int)
EVIOCGRAB = _IOW(ord('E'), 0x90, ctypes.sizeof(ctypes.c_int))

# EVIOCGNAME(len): read name
def EVIOCGNAME(length=256):
    return _IOR(ord('E'), 0x06, length)

# EVIOCGBIT(ev, len): read event bitmasks
def EVIOCGBIT(ev_type, length=96):
    return _IOR(ord('E'), 0x20 + ev_type, length)

# EVIOCGPROP(len): read properties
def EVIOCGPROP(length=8):
    return _IOR(ord('E'), 0x09, length)

# EVIOCGABS(abs): read axis parameters
def EVIOCGABS(abs_axis):
    return _IOR(ord('E'), 0x40 + abs_axis, ctypes.sizeof(input_absinfo))


# UInput IOCTL Definitions (<linux/uinput.h>)
UINPUT_IOCTL_BASE = ord('U')
UI_DEV_CREATE  = _IO(UINPUT_IOCTL_BASE, 1)
UI_DEV_DESTROY = _IO(UINPUT_IOCTL_BASE, 2)
UI_DEV_SETUP   = _IOW(UINPUT_IOCTL_BASE, 3, 92) # struct uinput_setup is 92 bytes
UI_ABS_SETUP   = _IOW(UINPUT_IOCTL_BASE, 4, 28) # struct uinput_abs_setup is 28 bytes
UI_SET_EVBIT   = _IOW(UINPUT_IOCTL_BASE, 100, ctypes.sizeof(ctypes.c_int))
UI_SET_KEYBIT  = _IOW(UINPUT_IOCTL_BASE, 101, ctypes.sizeof(ctypes.c_int))
UI_SET_RELBIT  = _IOW(UINPUT_IOCTL_BASE, 102, ctypes.sizeof(ctypes.c_int))
UI_SET_ABSBIT  = _IOW(UINPUT_IOCTL_BASE, 103, ctypes.sizeof(ctypes.c_int))
UI_SET_MSCBIT  = _IOW(UINPUT_IOCTL_BASE, 104, ctypes.sizeof(ctypes.c_int))
UI_SET_PROPBIT = _IOW(UINPUT_IOCTL_BASE, 110, ctypes.sizeof(ctypes.c_int))


# CTYPES Struct Definitions (<linux/input.h> and <linux/uinput.h>)

class input_id(ctypes.Structure):
    _fields_ = [
        ("bustype", ctypes.c_uint16),
        ("vendor", ctypes.c_uint16),
        ("product", ctypes.c_uint16),
        ("version", ctypes.c_uint16),
    ]

class input_absinfo(ctypes.Structure):
    _fields_ = [
        ("value", ctypes.c_int32),
        ("minimum", ctypes.c_int32),
        ("maximum", ctypes.c_int32),
        ("fuzz", ctypes.c_int32),
        ("flat", ctypes.c_int32),
        ("resolution", ctypes.c_int32),
    ]

class uinput_abs_setup(ctypes.Structure):
    _fields_ = [
        ("code", ctypes.c_uint16),
        ("absinfo", input_absinfo),
    ]

class uinput_setup(ctypes.Structure):
    _fields_ = [
        ("id", input_id),
        ("name", ctypes.c_char * 80),
        ("ff_effects_max", ctypes.c_uint32),
    ]

class timeval(ctypes.Structure):
    # On 64-bit Linux, timeval uses 64-bit long
    _fields_ = [
        ("tv_sec", ctypes.c_long),
        ("tv_usec", ctypes.c_long),
    ]

class input_event(ctypes.Structure):
    _fields_ = [
        ("time", timeval),
        ("type", ctypes.c_uint16),
        ("code", ctypes.c_uint16),
        ("value", ctypes.c_int32),
    ]

INPUT_EVENT_SIZE = ctypes.sizeof(input_event)


def grab_device(fd: int, grab: bool = True) -> None:
    """Acquires or releases exclusive grab on an evdev file descriptor."""
    # Pass integer directly so kernel receives (void *) 1 or (void *) 0
    fcntl.ioctl(fd, EVIOCGRAB, 1 if grab else 0)


def test_bit(bitfield: bytes, bit: int) -> bool:
    """Checks whether a bit is set in a bytearray bitfield."""
    byte_index = bit // 8
    bit_offset = bit % 8
    if byte_index < len(bitfield):
        return bool(bitfield[byte_index] & (1 << bit_offset))
    return False
