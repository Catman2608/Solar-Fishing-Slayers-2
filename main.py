# Imports
# GUI (Primary And Fallback)
import webview
# Text Parsing
import json
import re
# Misc
import traceback
import threading
import subprocess
import requests
import io
import base64
import time
import sys
import webbrowser
import os
import shutil
from pathlib import Path
# Computer Vision
import cv2
import numpy as np
# Capture
if sys.platform == "win32":
    try:
        import dxcam
    except:
        dxcam = None
else:
    dxcam = None
import mss
# Keyboard And Mouse Clicks (Platform-specific)
from pynput.keyboard import Listener as KeyListener, Key
from pynput import keyboard, mouse
from pynput.keyboard import Controller as KeyboardController
from pynput.mouse import Controller as MouseController
from pynput.mouse import Button
import ctypes
if sys.platform == "win32":
    from ctypes import wintypes
    try:
        import pygetwindow as gw
    except ImportError:
        gw = None
elif sys.platform == "darwin":
    import Quartz
    import AppKit
elif sys.platform == "linux":
    from Xlib import X, XK, display as Xdisplay
    from Xlib.ext import xtest

# Define Platform-Specific Constants
# All Platforms
keyboard_controller = KeyboardController()
mouse_controller = MouseController()
APP_VERSION = "2026.11.1"
BETA_VERSION = 0
DEVELOPER = "Catman2608"
def load_misc_settings(misc_path):
    try:
        with open(misc_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data

    except:
        return {}

def get_macos_menu_offset():
    if sys.platform != "darwin":
        return 0

    try:
        screen = AppKit.NSScreen.mainScreen()
        full_frame = screen.frame()
        visible_frame = screen.visibleFrame()
        return int(full_frame.size.height - visible_frame.size.height)

    except Exception:
        return 0

if sys.platform == "darwin":
    import Quartz
    _QUARTZ_SRGB_COLOR_SPACE = Quartz.CGColorSpaceCreateWithName(Quartz.kCGColorSpaceSRGB)
    # Cache display P3 color space (what MSS typically returns on modern Macs)
    _QUARTZ_P3_COLOR_SPACE = Quartz.CGColorSpaceCreateWithName(Quartz.kCGColorSpaceDisplayP3)
else:
    _QUARTZ_SRGB_COLOR_SPACE = None
    _QUARTZ_P3_COLOR_SPACE = None
def mss_to_srgb_numpy(image, source_is_p3=True):
    """
    Convert an untagged raw MSS/Fastgrab frame buffer from Display P3 to sRGB
    using macOS native ColorSync engine for identical Quartz output.
    """
    if image is None or getattr(image, "ndim", 0) != 3 or image.shape[2] not in (3, 4):
        return image

    if sys.platform != "darwin" or not source_is_p3:
        bgr = image[:, :, :3]
        return bgr if bgr.flags["C_CONTIGUOUS"] else np.ascontiguousarray(bgr)

    height, width = image.shape[:2]
    # 1. Ensure input buffer is BGRA (4 channels required by CGDataProvider)
    if image.shape[2] == 3:
        bgra = np.empty((height, width, 4), dtype=np.uint8)
        bgra[:, :, :3] = image
        bgra[:, :, 3] = 255
    else:
        bgra = image
    # 2. Wrap raw NumPy buffer in CGImage tagged as Display P3
    bytes_per_row = width * 4
    provider = Quartz.CGDataProviderCreateWithData(None, bgra.tobytes(), len(bgra.tobytes()), None)
    src_cg_image = Quartz.CGImageCreate(
        width, height, 8, 32, bytes_per_row,
        _QUARTZ_P3_COLOR_SPACE,
        Quartz.kCGImageAlphaPremultipliedFirst | Quartz.kCGBitmapByteOrder32Little,
        provider, None, False, Quartz.kCGRenderingIntentDefault
    )
    # 3. Draw into an sRGB context (CoreGraphics handles exact ColorSync transformation)
    out_raw = np.empty((height, width, 4), dtype=np.uint8)
    context = Quartz.CGBitmapContextCreate(out_raw, width, height, 8, bytes_per_row, _QUARTZ_SRGB_COLOR_SPACE, Quartz.kCGImageAlphaPremultipliedLast | Quartz.kCGBitmapByteOrder32Big)
    Quartz.CGContextDrawImage(context, Quartz.CGRectMake(0, 0, width, height), src_cg_image)
    # 4. Extract BGR uint8 result matching Quartz/MSS consumers
    return np.ascontiguousarray(out_raw[:, :, :3][:, :, ::-1])

def cgimage_to_srgb_numpy(image):
    if sys.platform == "darwin":
        width = Quartz.CGImageGetWidth(image)
        height = Quartz.CGImageGetHeight(image)
        bytes_per_row = width * 4
        raw = np.empty((height, width, 4), dtype=np.uint8)
        context = Quartz.CGBitmapContextCreate(raw, width, height, 8, bytes_per_row, _QUARTZ_SRGB_COLOR_SPACE, Quartz.kCGImageAlphaPremultipliedLast | Quartz.kCGBitmapByteOrder32Big)
        if context is None:
            return None

        Quartz.CGContextDrawImage(context, Quartz.CGRectMake(0, 0, width, height), image)
        return raw[:, :, :3][:, :, ::-1]

    return image

# Reload
def reload_page(skip=True):
    if skip == False:
        return

    if sys.platform == "win32":
        # Wrap in quotes to prevent compilation issues
        args = [sys.executable, f'"{sys.argv[0]}"'] + sys.argv[1:]
        os.execv(sys.executable, args)
    else:
        # os.execv does not use a shell, so do not wrap the script path in quotes.
        # Extra quotes become part of the filename and fail on macOS/Linux.
        args = [sys.executable] + list(sys.argv)
        os.execv(sys.executable, args)
# MSS screen dimensions and attribute checking
try:
    MSS = mss.MSS
except AttributeError:
    MSS = mss.mss
with MSS() as _sct:
    if len(_sct.monitors) > 1:
        _m = _sct.monitors[1]   # Primary monitor
    else:
        _m = _sct.monitors[0]   # Fallback: only one entry exists
    SCREEN_WIDTH  = _m["width"]
    SCREEN_HEIGHT = _m["height"]
    SCREEN_LEFT   = _m["left"]
    SCREEN_TOP    = _m["top"]
HALF_WIDTH = int(SCREEN_WIDTH / 2)
HALF_HEIGHT = int(SCREEN_HEIGHT / 2)
# Windows (Transparency And Ctypes Windll)
if sys.platform == "win32":
    windll = ctypes.windll.user32
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    # Ctypes GUI Constants
    SW_MAXIMIZE = 3
    user32 = ctypes.windll.user32
    user32.GetWindowLongW.restype = wintypes.LONG
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowLongW.restype = wintypes.LONG
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
    user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
    user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, ctypes.c_byte, wintypes.DWORD]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [
        wintypes.HWND,
        ctypes.c_int
    ]
    # Set Dpi Awareness Early To Ensure Consistent Coordinate Handling
    try:
        windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_PER_MONITOR_DPI_AWARE
        # Dpi Awareness Successfully Set
    except:
        try:
            windll.user32.SetProcessDPIAware()  # Fallback for older Windows
            # Dpi Awareness Set (Fallback Method)
        except:
            pass  # DPI awareness could not be set - coordinates may be inconsistent

    # Define the RECT structure used by Windows API
    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long)
        ]
    def get_taskbar_height():
        # Find the window handle for the taskbar
        hwnd = ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None)
        if hwnd:
            rect = RECT()
            # Get the bounding rectangle coordinates
            if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                taskbar_height = rect.bottom - rect.top
                return int(taskbar_height)

            else:
                return "Failed to get taskbar dimensions."

        else:
            return "Could not find the Windows Taskbar window."

    # Windows Api Related Functions
    def get_scale_factor():
        return 1

    def _get_hwnd(window):
        """Return a Windows HWND int from a pywebview window/native object."""
        native = getattr(window, "native", window)
        candidates = (
            native,
            getattr(native, "Handle", None),  # WinForms BrowserForm -> System.IntPtr
            getattr(window, "Handle", None),
            getattr(window, "hwnd", None),
        )
        for candidate in candidates:
            if not candidate:
                continue

            if isinstance(candidate, int):
                return candidate

            if hasattr(candidate, "value") and candidate.value:
                return int(candidate.value)

            if hasattr(candidate, "ToInt64"):
                value = int(candidate.ToInt64())
                if value:
                    return value

            if hasattr(candidate, "ToInt32"):
                value = int(candidate.ToInt32())
                if value:
                    return value

            try:
                value = int(candidate)
            except (TypeError, ValueError):
                continue

            if value:
                return value

        return None

# macOS (Keyboard, Scale Factor, Mouse Button, ScreenCaptureKit)
elif sys.platform == "darwin":
    # ScreenCaptureKit (preferred capture backend on macOS 12.3+)
    try:
        import ScreenCaptureKit as _SCK
        from collections import OrderedDict
        try:
            from Foundation import NSRunLoop
        except:
            NSRunLoop = None
        from ScreenCaptureKit import (SCShareableContent, SCContentFilter, SCStreamConfiguration, SCStream, SCStreamOutputType, SCStreamOutputTypeScreen)
        from Foundation import NSDate, NSObject
        import objc
        _SCK_AVAILABLE = True
        # PyObjC exposes the enum as a NewType. Cases are module constants
        # (SCStreamOutputTypeScreen == 0), not attributes of the NewType.
        _SCK_OUTPUT_SCREEN = SCStreamOutputTypeScreen
    except Exception as e:
        _SCK = None
        SCShareableContent = None
        SCContentFilter = None
        SCStreamConfiguration = None
        SCStream = None
        SCStreamOutputType = None
        NSDate = None
        NSObject = None
        objc = None
        _SCK_AVAILABLE = False
        _SCK_OUTPUT_SCREEN = 0
    _scale_cache = None
    MAC_KEY_MAP = {
        "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
        "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19, "3": 20,
        "4": 21, "6": 22, "5": 23, "equal": 24, "9": 25, "7": 26, "minus": 27, "-": 27, "8": 28, "0": 29, "o": 31,
        "u": 32, "i": 34, "p": 35, "l": 37, "j": 38, "'": 39, "quote": 39, "apostrophe": 39, "k": 40, "semicolon": 41, "comma": 43, "slash": 44, "n": 45,
        "m": 46, "period": 47, "space": 49, "return": 36, "enter": 76, "tab": 48, "backspace": 51, "delete": 51, "escape": 53,
        "command": 55, "cmd": 55, "shift": 56, "option": 58, "alt": 58, "control": 59, "ctrl": 59,
    }
    _QUARTZ_KEY_SOURCE = None
    def get_taskbar_height():
        return 0

    def _get_quartz_key_source():
        # Private Source So Posted Keys Do Not Inherit Hardware Command/Fn/Globe State
        global _QUARTZ_KEY_SOURCE
        if _QUARTZ_KEY_SOURCE is None:
            _QUARTZ_KEY_SOURCE = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStatePrivate)
            try:
                Quartz.CGEventSourceSetLocalEventsSuppressionInterval(_QUARTZ_KEY_SOURCE, 0.0)
            except Exception:
                pass

        return _QUARTZ_KEY_SOURCE

    def get_scale_factor():
        global _scale_cache
        if _scale_cache is not None:
            return _scale_cache

        try:
            _scale_cache = float(AppKit.NSScreen.mainScreen().backingScaleFactor())
        except Exception:
            _scale_cache = 1.0
        return _scale_cache

    def get_mouse_position():
        event = Quartz.CGEventCreate(None)
        loc = Quartz.CGEventGetLocation(event)
        return loc.x, loc.y

    def _move_mouse(x, y):
        """Expects logical points."""
        point = Quartz.CGPointMake(x, y)
        Quartz.CGWarpMouseCursorPosition(point)
        Quartz.CGAssociateMouseAndMouseCursorPosition(True)
    def _warp_mouse(x, y):
        """
        Instantly warps the mouse cursor to the given (x, y) coordinates
        without generating mouse-motion events.
        """
        # Define the target point
        point = Quartz.CGPointMake(float(x), float(y))
        event = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, point, Quartz.kCGMouseButtonLeft)
        # Warp the cursor
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
    def _mouse_event(button="left", press=True, x=None, y=None):
        """Unified cross-platform mouse event.
        button: 'left'/'right'/'middle' or 1/2/3
        press=True → down, False → up
        """
        if x is None or y is None:
            x, y = get_mouse_position()
        # Map Button → (Quartz Button Constant, Down Event, Up Event)
        button_map = {
            "left":   (Quartz.kCGMouseButtonLeft, Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp),
            1:        (Quartz.kCGMouseButtonLeft, Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp),
            "right":  (Quartz.kCGMouseButtonRight,Quartz.kCGEventRightMouseDown,Quartz.kCGEventRightMouseUp),
            3:        (Quartz.kCGMouseButtonRight,Quartz.kCGEventRightMouseDown,Quartz.kCGEventRightMouseUp),
            "middle": (Quartz.kCGMouseButtonCenter, Quartz.kCGEventOtherMouseDown,Quartz.kCGEventOtherMouseUp),
            2:        (Quartz.kCGMouseButtonCenter, Quartz.kCGEventOtherMouseDown,Quartz.kCGEventOtherMouseUp),
        }
        key = button.lower() if isinstance(button, str) else button
        if key not in button_map:
            key = "left"
        btn, down_evt, up_evt = button_map[key]
        event_type = down_evt if press else up_evt
        event = Quartz.CGEventCreateMouseEvent(None, event_type, Quartz.CGPointMake(float(x), float(y)), btn)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
    def send_key(key, delay=0.05, click_type=0, flags=0):
        """
        Send a keyboard event.
        click_type:
            0 = click (press + release)   [default]
            1 = hold (press only)
            2 = release (release only)
        flags: Quartz modifier mask. Default 0 so Globe/Fn is never inherited.
        """
        keycode = MAC_KEY_MAP.get(str(key).lower())
        if keycode is None:
            return

        source = _get_quartz_key_source()
        def _post_key(down):
            event = Quartz.CGEventCreateKeyboardEvent(source, keycode, down)
            if event is None:
                return

            # Explicit Flags Only. A Null Source Inherits Combined Session Flags,
            # Often Including Globe/Fn. Two Letters Then Look Like A Double
            # Globe Tap And macOS Opens Siri / Type To Siri / Dictation.
            Quartz.CGEventSetFlags(event, flags or 0)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        if click_type == 1:           # Hold (press only)
            _post_key(True)
        elif click_type == 2:         # Release only
            _post_key(False)
        else:                         # Click (press + release)
            _post_key(True)
            time.sleep(delay)
            _post_key(False)
    def send_hotkey(modifier, key, delay=0.05):
        """Modifier Down, Key Click With That Flag, Modifier Up."""
        flag_map = {
            "command": Quartz.kCGEventFlagMaskCommand,
            "cmd": Quartz.kCGEventFlagMaskCommand,
            "shift": Quartz.kCGEventFlagMaskShift,
            "option": Quartz.kCGEventFlagMaskAlternate,
            "alt": Quartz.kCGEventFlagMaskAlternate,
            "control": Quartz.kCGEventFlagMaskControl,
            "ctrl": Quartz.kCGEventFlagMaskControl,
        }
        flag = flag_map.get(str(modifier).lower(), 0)
        send_key(modifier, click_type=1, flags=flag)
        time.sleep(0.02)
        send_key(key, delay=delay, flags=flag)
        time.sleep(0.02)
        send_key(modifier, click_type=2, flags=0)
# Linux (Mouse Positions And Xdisplay)
elif sys.platform.startswith("linux"):
    _xdisplay = None
    def get_taskbar_height():
        return 0

    def _get_xdisplay():
        global _xdisplay
        if _xdisplay is None:
            _xdisplay = Xdisplay.Display()
        return _xdisplay

    def get_scale_factor():
        """
        X11 normally works in physical pixels.
        Return 1.0 unless you implement desktop-specific scaling detection.
        """
        return 1.0

    def get_mouse_position():
        d = _get_xdisplay()
        root = d.screen().root
        pointer = root.query_pointer()
        return pointer.root_x, pointer.root_y

    def _move_mouse(x, y):
        d = _get_xdisplay()
        root = d.screen().root
        root.warp_pointer(int(x), int(y))
        d.sync()
    def _mouse_event(button="left", press=True, x=None, y=None):
        """Unified cross-platform mouse event.
        button: 'left'/'right'/'middle' or 1/2/3
        press=True → down, False → up
        """
        d = _get_xdisplay()
        if x is not None and y is not None:
            _move_mouse(x, y)   # move first so the click happens at the desired location
        button_map = {
            "left": 1, 1: 1,
            "middle": 2, 2: 2,
            "right": 3, 3: 3,
        }
        key = button.lower() if isinstance(button, str) else button
        btn = button_map.get(key, 1)
        xtest.fake_input(d, X.ButtonPress if press else X.ButtonRelease, btn)
        d.sync()
    def send_key(key, delay=0.05, click_type=0):
        d = _get_xdisplay()
        keysym = XK.string_to_keysym(str(key))
        if keysym == 0:
            keysym = XK.string_to_keysym(str(key).lower())
        if keysym == 0:
            return

        keycode = d.keysym_to_keycode(keysym)
        if keycode == 0:
            return

        if click_type == 0:
            xtest.fake_input(d, X.KeyPress, keycode)
            d.sync()
            time.sleep(delay)
            xtest.fake_input(d, X.KeyRelease, keycode)
            d.sync()
        elif click_type == 1:
            xtest.fake_input(d, X.KeyPress, keycode)
            d.sync()
        elif click_type == 2:
            xtest.fake_input(d, X.KeyRelease, keycode)
            d.sync()
        else:
            xtest.fake_input(d, X.KeyPress, keycode)
            d.sync()
            time.sleep(delay)
            xtest.fake_input(d, X.KeyRelease, keycode)
            d.sync()

# ---------------------------------------------------------------------------
# ScreenCaptureKit region capture (inlined from DeepFish macOS v1.1.7)
#
# One stream per capture region, lazy pixel copy, blocking condition-based
# frame handoff, MSS fallback with a format compatibility check, and
# exclusion of the app's own windows (live preview, HUD).
#
# All public geometry is in Quartz screen points. Output is tightly packed
# BGRA at pixel_scale pixels per point.
# ---------------------------------------------------------------------------

class NoNewFrame(TimeoutError):
    '''The stream is alive but has no unconsumed complete frame.'''


def _source_rect(region, display):
    x, y, w, h = (region[k] for k in ('left', 'top', 'width', 'height'))
    dx, dy, dw, dh = display
    if w <= 0 or h <= 0 or x < dx or y < dy or x + w > dx + dw or y + h > dy + dh:
        raise ValueError('Capture region must fit inside one display')
    return (x - dx, y - dy), (w, h)


def _copy_bgra(buffer, width, height, stride):
    if width <= 0 or height <= 0 or stride < width * 4:
        raise ValueError('Invalid BGRA frame dimensions')
    rows = np.frombuffer(buffer, dtype=np.uint8, count=stride * height).reshape(height, stride)
    return rows[:, :width * 4].reshape(height, width, 4).copy()


def _compatible_pixels(native, reference):
    '''Startup sanity check: native SCK output must match MSS format.

    Own-process windows are excluded from SCK but not from MSS, so a patch
    where one overlaps the region can differ; that must NOT send the region
    to MSS (MSS would then show those windows to detection). A real format
    mismatch (channel swap, wrong stride) makes nearly every coloured pixel
    wrong, not a patch.
    '''
    if native.shape != reference.shape or native.dtype != np.uint8:
        return False
    delta = np.abs(native[::2, ::2, :3].astype(np.int16) - reference[::2, ::2, :3]).max(axis=2)
    if float(np.quantile(delta, 0.75)) <= 12:
        return True
    ref = reference[::2, ::2, :3].astype(np.int16)
    coloured = ref.max(axis=2) - ref.min(axis=2) >= 30
    if coloured.mean() < 0.05:
        return False
    return float((delta[coloured] <= 12).mean()) >= 0.4


class _PendingFrame:
    '''A delivered SCK sample whose pixels are copied lazily, at most once.'''

    def __init__(self, sample, width, height):
        self.sample, self.width, self.height = sample, width, height
        self.pixels = None
        self.lock = threading.Lock()

    def get(self):
        if sys.platform != "darwin":
            return 0
        with self.lock:
            if self.pixels is None:
                import Quartz as Q
                import CoreMedia as CM
                pixel = CM.CMSampleBufferGetImageBuffer(self.sample)
                if Q.CVPixelBufferLockBaseAddress(pixel, Q.kCVPixelBufferLock_ReadOnly) != 0:
                    raise RuntimeError('Could not lock capture pixels')
                try:
                    stride = Q.CVPixelBufferGetBytesPerRow(pixel)
                    base = Q.CVPixelBufferGetBaseAddress(pixel)
                    self.pixels = _copy_bgra(base.as_buffer(stride * self.height), self.width, self.height, stride)
                finally:
                    Q.CVPixelBufferUnlockBaseAddress(pixel, Q.kCVPixelBufferLock_ReadOnly)
                self.sample = None
            return self.pixels


def _pixels(frame):
    if isinstance(frame, _PendingFrame):
        return frame.get()
    return frame


class _LatestFrame:
    '''Thread-safe single-slot holder for the newest complete frame.'''

    def __init__(self):
        self.condition = threading.Condition()
        self.sequence = 0
        self.frame = None
        self.timestamp = 0.0
        self.error = None
        self.closed = False

    def publish(self, frame, timestamp):
        with self.condition:
            if self.closed:
                return
            self.frame, self.timestamp = frame, timestamp
            self.sequence += 1
            self.condition.notify_all()

    def fail(self, error):
        with self.condition:
            self.error = error
            self.condition.notify_all()

    def read(self, after, timeout):
        with self.condition:
            self.condition.wait_for(
                (lambda: self.sequence > after or self.error or self.closed), timeout)
            if self.error:
                raise RuntimeError(str(self.error))
            if self.closed:
                raise RuntimeError('Capture closed')
            if self.sequence <= after:
                raise NoNewFrame('Waiting for a fresh capture frame')
            sequence, frame, timestamp = self.sequence, self.frame, self.timestamp
        return sequence, _pixels(frame), timestamp

    def close(self):
        with self.condition:
            self.closed = True
            self.frame = None
            self.condition.notify_all()


_receiver_class = None
_receiver_lock = threading.Lock()
_EXCLUSION_FAST, _EXCLUSION_SLOW = 0.15, 2.0
_exclusion_burst_until = 0.0


def expect_new_windows(seconds=2.5):
    '''Call after showing a window that capture must leave out.'''
    global _exclusion_burst_until
    _exclusion_burst_until = max(_exclusion_burst_until, time.perf_counter() + seconds)


def _receiver_class_factory():
    if sys.platform != "darwin":
        return
    global _receiver_class
    with _receiver_lock:
        if _receiver_class is not None:
            return _receiver_class
        import objc
        import ScreenCaptureKit as SCK
        import CoreMedia as CM
        import Quartz as Q
        from Foundation import NSObject

        class _CaptureReceiver(NSObject, protocols=[
                objc.protocolNamed('SCStreamOutput'),
                objc.protocolNamed('SCStreamDelegate')]):
            def stream_didOutputSampleBuffer_ofType_(self, stream, sample, kind):
                if kind != SCK.SCStreamOutputTypeScreen or self.owner is None:
                    return
                owner = self.owner
                try:
                    attachments = CM.CMSampleBufferGetSampleAttachmentsArray(sample, False)
                    if not attachments:
                        return
                    status = attachments[0].get(SCK.SCStreamFrameInfoStatus)
                    owner.last_callback = time.perf_counter()
                    if status == SCK.SCFrameStatusIdle:
                        owner.last_idle = owner.last_callback
                        return
                    if status != SCK.SCFrameStatusComplete:
                        return
                    pixel = CM.CMSampleBufferGetImageBuffer(sample)
                    if pixel is None:
                        return
                    if Q.CVPixelBufferGetPixelFormatType(pixel) != Q.kCVPixelFormatType_32BGRA:
                        raise ValueError('ScreenCaptureKit did not return BGRA')
                    width, height = Q.CVPixelBufferGetWidth(pixel), Q.CVPixelBufferGetHeight(pixel)
                    if (width, height) != owner.size:
                        raise ValueError('ScreenCaptureKit region scale changed')
                    frame = _PendingFrame(sample, width, height)
                    now_host = CM.CMTimeGetSeconds(CM.CMClockGetTime(CM.CMClockGetHostTimeClock()))
                    pts = CM.CMTimeGetSeconds(CM.CMSampleBufferGetPresentationTimeStamp(sample))
                    age = max(0.0, now_host - pts)
                    if not np.isfinite(age) or age > 0.25:
                        return
                    owner.latest.publish(frame, time.perf_counter() - age)
                except Exception as exc:
                    owner.latest.fail(exc)

            def stream_didStopWithError_(self, stream, error):
                if self.owner is not None:
                    self.owner.latest.fail(error)

        _receiver_class = _CaptureReceiver
        return _receiver_class


def _display_refresh_rate(display_id, fallback=60.0):
    if sys.platform != "darwin":
        return 0
    import Quartz as Q
    try:
        mode = Q.CGDisplayCopyDisplayMode(display_id)
        rate = Q.CGDisplayModeGetRefreshRate(mode) if mode else 0.0
        if rate and rate > 1:
            return float(rate)
    except Exception:
        pass
    try:
        for screen in AppKit.NSScreen.screens():
            number = screen.deviceDescription().get('NSScreenNumber')
            if number is None:
                continue
            if int(number) == int(display_id):
                rate = float(screen.maximumFramesPerSecond())
                if rate > 1:
                    return rate
    except Exception:
        pass
    return fallback


def _await_completion(operation, timeout=4.0):
    done = threading.Event()
    result = []

    def complete(*args):
        result.extend(args)
        done.set()

    operation(complete)
    if not done.wait(timeout):
        raise TimeoutError('ScreenCaptureKit operation timed out')
    if result and result[-1] is not None:
        raise RuntimeError(str(result[-1]))
    if len(result) > 1:
        return result[0]


_EXCLUDED_WINDOW_TITLES = {'Solar Fishing Live Preview',
                        'Solar Fishing Live Preview · Bellona 1',
                        'Solar Fishing Live Preview · Bellona 2'}


def _own_process_ids():
    ids = {os.getpid()}
    try:
        import multiprocessing
        ids.update(child.pid for child in multiprocessing.active_children() if child.pid)
    except Exception:
        pass
    return ids


def _excluded_windows(content):
    own = _own_process_ids()
    out = []
    for window in content.windows():
        app = window.owningApplication()
        if app is None or int(app.processID()) not in own:
            if str(window.title() or '') not in _EXCLUDED_WINDOW_TITLES:
                continue
        out.append(window)
    return out


class _NativeRegion:
    '''One SCK stream for one capture region, in Quartz screen points.'''

    def __init__(self, region, fps, pixel_scale=1.0):
        if sys.platform != "darwin":
            return
        import ScreenCaptureKit as SCK
        import CoreMedia as CM
        import Quartz as Q
        self.latest = _LatestFrame()
        self.sequence = 0
        self.size = int(region['width'] * pixel_scale), int(region['height'] * pixel_scale)
        self.last_callback = time.perf_counter()
        self.last_idle = 0.0
        self.stream = None
        self.receiver = None
        self.filter_generation = 0
        self._exclusion_inflight = False
        content = _await_completion(
            (lambda cb: SCK.SCShareableContent
                .getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(
                    True, True, cb)))
        display, crop = None, None
        for candidate in content.displays():
            bounds = Q.CGDisplayBounds(candidate.displayID())
            try:
                crop = _source_rect(region, (
                    bounds.origin.x, bounds.origin.y,
                    bounds.size.width, bounds.size.height))
                display = candidate
                break
            except ValueError:
                continue
        if display is None:
            raise ValueError('Region crosses displays or is outside the desktop')
        self.refresh_rate = _display_refresh_rate(display.displayID())
        config = SCK.SCStreamConfiguration.alloc().init()
        config.setSourceRect_(crop)
        config.setWidth_(self.size[0])
        config.setHeight_(self.size[1])
        config.setPixelFormat_(Q.kCVPixelFormatType_32BGRA)
        config.setColorSpaceName_(Q.kCGColorSpaceSRGB)
        config.setShowsCursor_(False)
        config.setQueueDepth_(3)
        config.setMinimumFrameInterval_(CM.CMTimeMake(1, self._capture_rate(fps)))
        self.config, self.fps = config, fps
        own = _excluded_windows(content)
        self.display = display
        self.excluded_ids = {window.windowID() for window in own}
        self.filter_checked = time.perf_counter()
        filter_ = SCK.SCContentFilter.alloc().initWithDisplay_excludingWindows_(display, own)
        self.receiver = _receiver_class_factory().alloc().init()
        self.receiver.owner = self
        self.stream = SCK.SCStream.alloc().initWithFilter_configuration_delegate_(
            filter_, config, self.receiver)
        try:
            ok, error = self.stream.addStreamOutput_type_sampleHandlerQueue_error_(
                self.receiver, SCK.SCStreamOutputTypeScreen, None, None)
            if not ok:
                raise RuntimeError(str(error))
            _await_completion(self.stream.startCaptureWithCompletionHandler_)
        except Exception:
            self.close()
            raise

    def _capture_rate(self, fps):
        cap = round(self.refresh_rate) or 360
        return max(1, min(360, int(fps), cap))

    def set_fps(self, fps):
        if sys.platform != "darwin":
            return
        if fps == self.fps:
            return
        import CoreMedia as CM
        self.config.setMinimumFrameInterval_(CM.CMTimeMake(1, self._capture_rate(fps)))
        _await_completion(
            (lambda cb: self.stream.updateConfiguration_completionHandler_(self.config, cb)))
        self.fps = fps

    def refresh_exclusions(self):
        '''Add windows shown after start (live preview) to the exclusion list.
        Only one query is in flight at a time so bursts cannot pile up.
        '''
        if sys.platform != "darwin":
            return
        now = time.perf_counter()
        interval = _EXCLUSION_FAST if now < _exclusion_burst_until else _EXCLUSION_SLOW
        if now - getattr(self, 'filter_checked', now) < interval or self.stream is None:
            return
        if self._exclusion_inflight:
            return
        self._exclusion_inflight = True
        self.filter_checked = now
        import ScreenCaptureKit as SCK

        def listed(content, error):
            self._exclusion_inflight = False
            if content is None or self.stream is None:
                return
            try:
                windows = _excluded_windows(content)
            except Exception:
                return
            try:
                ids = {window.windowID() for window in windows}
                if ids == self.excluded_ids:
                    return
                self.excluded_ids = ids
                filter_ = SCK.SCContentFilter.alloc().initWithDisplay_excludingWindows_(
                    self.display, windows)
                self.stream.updateContentFilter_completionHandler_(filter_, None)
                self.filter_generation += 1
            except Exception:
                return

        SCK.SCShareableContent.getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(
            True, True, listed)

    def grab(self, wait=True):
        self.refresh_exclusions()
        try:
            timeout = 3.0 if not self.sequence else 0.1 if wait else 0.0
            self.sequence, frame, stamp = self.latest.read(self.sequence, timeout)
        except NoNewFrame:
            if not self.sequence or time.perf_counter() - self.last_callback > 5:
                raise RuntimeError('ScreenCaptureKit stopped delivering frames')
            still = self.latest.frame
            if still is not None and time.perf_counter() - self.last_idle <= 0.25:
                return _pixels(still), self.last_idle
            raise
        if time.perf_counter() - stamp > 0.25:
            raise NoNewFrame('Discarded stale frame')
        return frame, stamp

    def close(self):
        self.latest.close()
        if self.stream is not None:
            try:
                _await_completion(self.stream.stopCaptureWithCompletionHandler_, timeout=1.0)
            except Exception:
                pass
        if self.receiver is not None:
            self.receiver.owner = None
        self.stream = self.receiver = None


class _RegionCapture:
    '''Worker-owned region streams with MSS fallback.'''

    def __init__(self, fps=240, log=print, pixel_scale=1.0):
        if sys.platform != "darwin":
            return
        self.fps = fps
        self.log = log
        self.pixel_scale = pixel_scale
        self.fallback = None
        self.regions = OrderedDict() if 'OrderedDict' in globals() else {}
        self.timestamp = 0.0
        self.backend = None
        self.preference = 'ScreenCaptureKit'

    def set_backend(self, preference):
        if preference not in ('ScreenCaptureKit', 'MSS'):
            raise ValueError('Unknown capture backend')
        if preference == self.preference:
            return
        for native in self.regions.values():
            if native is not None:
                native.close()
        self.regions.clear()
        self.preference = preference
        self.log(f'>>> CAPTURE: selected {preference}')

    def _mss(self):
        if self.fallback is None:
            self.fallback = MSS()
        return self.fallback

    def set_fps(self, fps):
        self.fps = fps
        for key, native in list(self.regions.items()):
            if native is not None:
                try:
                    native.set_fps(fps)
                except Exception as exc:
                    native.close()
                    self.regions[key] = None
                    self.log(f'>>> CAPTURE: rate update failed; using MSS ({exc})')
                    continue

    def grab(self, region, wait=True):
        if self.preference == 'MSS':
            frame = np.asarray(self._mss().grab(region))
            self.timestamp, self.backend = time.perf_counter(), 'MSS'
            return frame
        key = tuple(int(region[k]) for k in ('left', 'top', 'width', 'height'))
        if key not in self.regions:
            if len(self.regions) >= 2:
                _, old = self.regions.popitem(last=False)
                if old is not None:
                    old.close()
            native = None
            try:
                native = _NativeRegion(region, self.fps, pixel_scale=self.pixel_scale)
                frame, stamp = native.grab()
                for attempt in range(3):
                    try:
                        reference = np.asarray(self._mss().grab(region))
                    except Exception as exc:
                        self.log(f'>>> CAPTURE: MSS comparison unavailable ({exc}); using native format checks')
                        break
                    if _compatible_pixels(frame, reference):
                        break
                    if attempt == 2:
                        raise ValueError('RGB/Retina comparison differed from MSS')
                    try:
                        frame, stamp = native.grab()
                    except NoNewFrame:
                        continue
                    except Exception:
                        raise
            except Exception as exc:
                if native is not None:
                    native.close()
                self.regions[key] = None
                self.log(f'>>> CAPTURE: using MSS fallback ({exc})')
                frame = np.asarray(self._mss().grab(region))
                self.timestamp, self.backend = time.perf_counter(), 'MSS'
                return frame
            self.regions[key] = native
            self.timestamp, self.backend = stamp, 'ScreenCaptureKit'
            self.log('>>> CAPTURE: ScreenCaptureKit region ready (BGRA)')
            refresh_rate = getattr(native, 'refresh_rate', None)
            if isinstance(refresh_rate, (int, float)) and self.fps > refresh_rate:
                self.log(f'>>> CAPTURE: capturing at {round(refresh_rate)} fps '
                        f'(display refresh) instead of {self.fps}')
            return frame
        native = self.regions[key]
        try:
            self.regions.move_to_end(key)
        except AttributeError:
            pass
        if native is not None:
            try:
                native.set_fps(self.fps)
                frame, self.timestamp = native.grab(wait=wait)
                self.backend = 'ScreenCaptureKit'
                return frame
            except NoNewFrame:
                raise
            except Exception as exc:
                native.close()
                self.regions[key] = None
                self.log(f'>>> CAPTURE: stream failed; using MSS ({exc})')
        frame = np.asarray(self._mss().grab(region))
        self.timestamp, self.backend = time.perf_counter(), 'MSS'
        return frame

    def __enter__(self):
        return self

    def __exit__(self, *args):
        for native in self.regions.values():
            if native is not None:
                native.close()
        self.regions.clear()
        if self.fallback is not None:
            self.fallback.close()
            self.fallback = None

# ── Scanner (ported from scanner.py) ────────────────────────────────
DEFAULT_ZONE_HOLD_MISS_FRAMES = 45
DEFAULT_WHITE_HOLD_MISS_FRAMES = 30
MIN_W = 40
MIN_H = 40
from dataclasses import dataclass

@dataclass(frozen=True)
class ScanBox:
    x: int
    y: int
    w: int
    h: int
    @property
    def mid_x(self) -> int: return self.x + self.w // 2
    @property
    def mid_y(self) -> int: return self.y + self.h // 2
    @property
    def top(self) -> int: return self.y
    @property
    def bottom(self) -> int: return self.y + self.h - 1
@dataclass(frozen=True)
class Box:
    x: 'int'
    y: 'int'
    w: 'int'
    h: 'int'
    @property
    def mid_x(self) -> 'int':
        return self.x + self.w // 2

    @property
    def mid_y(self) -> 'int':
        return self.y + self.h // 2

    @property
    def top(self) -> 'int':
        return self.y

    @property
    def bottom(self) -> 'int':
        return self.y + self.h - 1

def _largest_run(mask_1d: 'np.ndarray') -> 'tuple[int, int] | None':
    '''Largest contiguous True run → (start, end inclusive).'''

    padded = np.concatenate(([False], mask_1d.astype(bool), [False]))
    diff = np.diff(padded.astype(np.int8))
    starts = np.flatnonzero(diff == 1)
    ends = np.flatnonzero(diff == -1) - 1
    if starts.size == 0 or starts.size != ends.size:
        return
    lengths = ends - starts + 1
    best = int(np.argmax(lengths))
    return int(starts[best]), int(ends[best])
def _bgr_samples(samples: 'list[dict]') -> 'np.ndarray':
    rows = []
    for s in samples:
        r, g, b = (int(v) for v in s['rgb'])
        rows.append([b, g, r])
    if rows:
        return np.array(rows, dtype=np.int16)
    return np.zeros((0, 3), dtype=np.int16)

def _schedule_webview_destroy(win, after=None, delay=0.05):
    """Destroy a pywebview window after the current JS/GUI call returns.
    Calling Window.destroy() from that window's js_api deadlocks pywebview
    (the bridge waits for destroy; destroy waits for the bridge). The stall
    freezes every other window too. Tear windows down from a short-lived
    thread instead.
    """
    if win is None:
        if after:
            try:
                after()
            except Exception:
                pass

        return

    def _destroy():
        if delay:
            time.sleep(delay)
        try:
            win.destroy()
        except Exception:
            pass

        if after:
            try:
                after()
            except Exception:
                pass

    threading.Thread(target=_destroy, daemon=True).start()
# Config Management
def get_base_path():
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            # User-writable data directory for macOS .app bundles
            data_dir = Path.home() / "Library" / "Application Support" / "SolarFishingSlayers2"
            data_dir.mkdir(parents=True, exist_ok=True)
            return data_dir, True

        elif sys.platform == "linux":
            if 'AppRun' in sys.executable:
                return Path(sys.executable).parent.resolve(), True
        else:
            return Path(sys.executable).parent.resolve(), True
    else:
        return Path(__file__).parent.resolve(), False

# Get Read Only Path
def get_resource_path():
    """
    Packaged assets (ui/, images/, bundled default configs/).
    Compiled macOS/Linux: PyInstaller onedir --add-data folder (sys._MEIPASS, typically <app>/_internal or .app/Contents/Frameworks).
    Compiled Windows: directory next to the .exe (unchanged).
    Dev: project directory.
    """
    if getattr(sys, 'frozen', False):
        if sys.platform == "win32":
            return Path(sys.executable).parent.resolve()

        if hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS).resolve()

        return Path(sys.executable).parent.resolve()

    return Path(__file__).parent.resolve()

# Make Sure That Configs Actually Exist
def ensure_config_exists():
    colors = os.path.join(EDITABLE_PATH, "colors.json")
    settings = os.path.join(EDITABLE_PATH, "settings.json")
    defaults = {
        colors: {"rgb_tol": 12, "yellow": [], "green": []},
        settings: {},
    }
    for path, default in defaults.items():
        # Write a valid JSON seed if the file is missing OR empty.
        try:
            if not os.path.exists(path) or os.path.getsize(path) == 0:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(default, f, indent=4)
        except OSError:
            # Read-only path (e.g. accidental write into .app bundle) — let
            # later load fail loudly instead of crashing at import time.
            pass
    return colors, settings

# Establish The Global Base Path For Solar Fishing V5
EDITABLE_PATH, IS_COMPILED = get_base_path()
READ_ONLY_PATH = get_resource_path()
# Make Sure Base Path Exists
os.makedirs(EDITABLE_PATH, exist_ok=True)
os.makedirs(READ_ONLY_PATH, exist_ok=True)
# Configs Path
LAST_CONFIG = os.path.join(EDITABLE_PATH, "misc.json")
data = load_misc_settings(LAST_CONFIG)
UI_PATH = os.path.join(READ_ONLY_PATH, "ui")
COLORS_PATH, SETTINGS_PATH = ensure_config_exists()
# None until index.html is parsed. Must exist before _get_prompt_defaults reads it.
_PROMPT_DEFAULTS = None
# Central Area Definitions.  To Add A New Selectable Area:
# 1. Add An Entry Below (Key, Color, Label, Default Ratios 0–1).
# 2. That'S It — Selector Ui, Save/Load, Defaults, And The Show/Hide Menu
#      all pick it up automatically.  Use get_areas("your_key") later if needed.
AREA_CONFIG = {
    "fish": {
        "color": "#df0000",
        "label": "Fish Box",
        "default": {"x": 0.731640625, "y": 0.2923611111111111, "w": 0.03828125, "h": 0.3763888888888889},
    },
}
# Display / Iteration Order (Also Used For Numberkey Toggles 1–9 In The Selector)
AREA_ORDER = list(AREA_CONFIG.keys())
class AreaSelector:
    # Do not expose to JS API — holds pywebview Window (native.AccessibilityObject recursion / WebView2 COM).
    _serializable = False
    HTML_FILE = os.path.join(UI_PATH, "area_selector.html")
    def __init__(self, parent_app):
        self.parent_app = parent_app
        self.overlay_window = None  
        self._open = False
        self._visible = False
        self._areas = {}
        self._visible_areas = {}
        self._screen_capture = None
        self._screenshot_b64 = None
        self._page_ready = False
        self._pending_js = []
        # Track active viewport geometry (logical points for pywebview)
        self.left = 0
        self.top = 0
        self.width = 0
        self.height = 0
    def _to_window_coords(self, left, top, width, height):
        """
        Convert physical-pixel geometry (from _get_areas / capture) into the
        logical points pywebview expects for window x/y/width/height.
        On Windows scale is always 1; on macOS Retina it is typically 2.0.
        Also clamps width/height so a bad (e.g. post-reset) size cannot make
        the overlay cover the entire screen or exceed monitor bounds.
        """
        scale = get_scale_factor()
        if scale <= 0:
            scale = 1.0
        left = int(left)
        top = int(top)
        width = max(1, int(width))
        height = max(1, int(height))
        # SCREEN_* are physical pixels; window geometry is in logical points.
        screen_w = max(1, int(SCREEN_WIDTH * scale))
        screen_h = max(1, int(SCREEN_HEIGHT * scale))
        width = min(width, screen_w)
        height = min(height, screen_h)
        left = max(0, min(left, max(0, screen_w - width)))
        top = max(0, min(top, max(0, screen_h - height)))
        return left, top, width, height

    def show(self):
        """Creates and displays the transparent frameless overlay window.
        Arguments are physical-pixel screen coordinates (same space as _get_areas / capture_frame). They are converted to logical points
        for pywebview.
        """
        # Position below the macOS menu area; use physical pixels because
        # _to_window_coords converts its geometry to logical window points.
        scale = get_scale_factor()
        if scale <= 0:
            scale = 1.0
        macos_offset = int(round(get_macos_menu_offset()))
        left, top, width, height = self._to_window_coords(0, macos_offset, SCREEN_WIDTH, max(1, SCREEN_HEIGHT - macos_offset),)
        if self._open and self.overlay_window:
            # If already open, shift/resize it instead of duplicating
            self.resize(left, top, width, height, already_logical=True)
            return

        self._page_ready = False
        self._pending_js = []
        self._screen_capture = self._capture_and_crop()
        self._screenshot_b64 = self._encode_screenshot(self._screen_capture)
        self._view_w = float(width)
        self._view_h = float(height)
        self.left = left
        self.top = top
        self.width = width
        self.height = height
        # Thin js_api only. Do not pass self — it holds the pywebview Window,
        # and pywebview walks that into AccessibilityObject.Bounds recursion.
        outer = self
        class _AreaSelectorApi:
            def window_ready(self, win_x, win_y, width=None, height=None):
                return outer.window_ready(win_x, win_y, width, height)

            def get_screenshot_data(self):
                return outer.get_screenshot_data()

            def save_areas(self, areas):
                return outer.save_areas(areas)

        self.overlay_window = webview.create_window("Area Selector", self.HTML_FILE, js_api=_AreaSelectorApi(), transparent=False, frameless=True, easy_drag=False, on_top=True, resizable=False, focus=True, width=self.width, height=self.height, x=self.left, y=self.top, background_color="#000000", min_size=(10, 10),)
        self._open = True
        self._visible = True
        self.overlay_window.events.closed += self._on_closed
        if sys.platform == "win32":
            def maximize_area_selector():
                try:
                    hwnd = _get_hwnd(self.overlay_window)
                    if hwnd:
                        user32.ShowWindow(wintypes.HWND(hwnd), SW_MAXIMIZE)
                except Exception as e:
                    try:
                        self.parent_app.set_status("Failed to maximize area selector:", e)
                    except Exception:
                        pass

            self.overlay_window.events.shown += maximize_area_selector
    def hide(self):
        """Destroys the current window instance completely.
        Clear _open BEFORE destroy so concurrent minigame threads that still
        call clear()/draw_box()/_eval skip the disposed WebView2 and avoid
        ObjectDisposedException (logged by pywebview as 'Error occurred in script').
        Destroy is scheduled off the JS-API thread to avoid pywebview deadlock.
        """
        win = self.overlay_window
        if not win or not self._open:
            self._open = False
            self._visible = False
            return

        self._open = False
        self._visible = False
        self.overlay_window = None
        _schedule_webview_destroy(win, after=self._on_closed)
    def window_ready(self, win_x, win_y, width=None, height=None):
        """JS signals the page is ready — record CSS client size and push screenshot.
        width/height are window.innerWidth / innerHeight (CSS pixels). Using
        these for box conversion fixes the off-screen drawing that happens
        when display scale ≠ 100% and SCREEN_* (physical) ≠ canvas size.
        """
        try:
            if width is not None and height is not None:
                w = float(width)
                h = float(height)
                if w > 0 and h > 0:
                    self._view_w = w
                    self._view_h = h
        except (TypeError, ValueError):
            pass

        if self._screenshot_b64 and self.overlay_window and self._open:
            # Inject Via A Short Data Reference; Js Stores It And Draws.
            try:
                # Pass As Return Value Of A Dedicated Getter Instead Of
                # Embedding A Huge String In Evaluate_Js When Possible.
                self.overlay_window.evaluate_js("window.__applyScreenshot && window.__applyScreenshot()")
            except Exception:
                pass

        self._page_ready = True
        self._flush_pending_js()
        return None

    def update(self, areas_dict, data):
        self.clear()
        scale = get_scale_factor() or 1.0
        if scale <= 0:
            scale = 1.0
        menu_offset_pixels = int(round(get_macos_menu_offset() * scale))
        self._visible_areas = {}
        visible_areas = []
        visible_areas.append("fish")
        for name in AREA_ORDER:
            area_data = (areas_dict or {}).get(name)
            if not isinstance(area_data, dict):
                # Unset: treat default as relative to the current Roblox window
                default = dict(AREA_CONFIG[name]["default"])
                try:
                    area_data = self.parent_app._map_relative_area_to_screen(default)
                except Exception:
                    area_data = default
            color = AREA_CONFIG[name]["color"]
            label = AREA_CONFIG[name].get("label", name)
            self._areas[name] = self.pixels_to_ratios(area_data)
            # Now draw the areas
            if name in visible_areas:
                self._visible_areas[name] = {"color": color, "label": label}
        # Convert ratios to logical canvas coordinates (CSS pixels).
        # SCREEN_WIDTH/HEIGHT are logical; menu_offset_pixels is physical and
        # must be converted to logical before subtracting from the canvas y.
        menu_offset_logical = menu_offset_pixels / scale
        boxes = {}
        for name, style in self._visible_areas.items():
            area = self._areas[name]
            boxes[name] = {
                "x": area["x"] * SCREEN_WIDTH,
                "y": area["y"] * SCREEN_HEIGHT - menu_offset_logical,
                "width": area["width"] * SCREEN_WIDTH,
                "height": area["height"] * SCREEN_HEIGHT,
                **style,
            }
        self._eval(f"window.fishOverlay && window.fishOverlay.setBoxes({json.dumps(boxes)})")
        # Draw cyan outline of the detected Roblox window (or full screen fallback)
        roblox = getattr(self.parent_app, "roblox_bounds", None)
        if roblox and isinstance(roblox, dict):
            try:
                left = float(roblox.get("left", 0) or 0)
                top = float(roblox.get("top", 0) or 0)
                width = float(roblox.get("width", 0) or 0)
                height = float(roblox.get("height", 0) or 0)
                # Same coordinate space as the area boxes (logical CSS pixels)
                roblox_js = {
                    "x": left,
                    "y": top - menu_offset_logical,
                    "width": width,
                    "height": height,
                    "color": "#00FFFF",
                    "label": "Roblox",
                }
                self._eval(f"window.fishOverlay && window.fishOverlay.setRobloxRect({json.dumps(roblox_js)})")
            except Exception:
                self._eval("window.fishOverlay && window.fishOverlay.setRobloxRect(null)")
        else:
            self._eval("window.fishOverlay && window.fishOverlay.setRobloxRect(null)")
    def resize(self, left, top, width, height, already_logical=False):
        """Resizes and moves the window dynamically if it exists.
        By default arguments are physical pixels (same as show()).
        Pass already_logical=True when the caller has already converted them.
        """
        if not already_logical:
            left, top, width, height = self._to_window_coords(left, top, width, height)
        self.left = left
        self.top = top
        self.width = width
        self.height = height
        if self.overlay_window and self._open:
            try:
                self.overlay_window.move(self.left, self.top)
                self.overlay_window.resize(self.width, self.height)
            except Exception:
                # Window may already be disposed (race with stop_macro / hide)
                self._open = False
                self.overlay_window = None
    def pixels_to_ratios(self, area):
        """Convert pixels to ratios by dividing values by screen width and height"""
        if not isinstance(area, dict):
            return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}

        values = {
            "x": float(area.get("x", 0)),
            "y": float(area.get("y", 0)),
            "width": float(area.get("width", area.get("w", 0))),
            "height": float(area.get("height", area.get("h", 0))),
        }
        if any(abs(values[key]) > 1 for key in values):
            values["x"] /= SCREEN_WIDTH
            values["y"] /= SCREEN_HEIGHT
            values["width"] /= SCREEN_WIDTH
            values["height"] /= SCREEN_HEIGHT
        return values

    def clear(self):
        """Clears rendering elements inside the web view context."""
        self._eval("window.fishOverlay && window.fishOverlay.clear()")
    def get_screenshot_data(self):
        """Return the data-URL of the frozen (menu-bar-cropped) screenshot."""
        return self._screenshot_b64 or ""

    def save_areas(self, areas):
        """Persist the current canvas boxes as ratios relative to the Roblox window.
        0,0 = left/top of the cached Roblox bounds; 1,1 = width/height of the Roblox bounds.
        Also caches the Roblox window coordinates used for the conversion.
        Called from JS on Esc / F6 / beforeunload so changes are always written back.
        """
        if not isinstance(areas, dict):
            areas = {}
        scale = get_scale_factor() or 1.0
        if scale <= 0:
            scale = 1.0
        # menu_offset is stored/used in logical units to match the canvas and
        # SCREEN_WIDTH/HEIGHT (which are logical).
        menu_offset_logical = get_macos_menu_offset()
        # Detect and cache the Roblox window bounds (falls back to full screen)
        try:
            roblox = self.parent_app.detect_roblox()
        except Exception:
            roblox = {"left": 0, "top": 0, "width": SCREEN_WIDTH, "height": SCREEN_HEIGHT}
        r_left = float(roblox.get("left", 0) or 0)
        r_top = float(roblox.get("top", 0) or 0)
        r_w = float(roblox.get("width", 0) or 0)
        r_h = float(roblox.get("height", 0) or 0)
        if r_w < 10 or r_h < 10:
            r_left, r_top, r_w, r_h = 0.0, 0.0, float(SCREEN_WIDTH), float(SCREEN_HEIGHT)
        self.parent_app.roblox_bounds_cache = {
            "left": r_left,
            "top": r_top,
            "width": r_w,
            "height": r_h,
        }
        self.parent_app.roblox_bounds = dict(self.parent_app.roblox_bounds_cache)
        for name, box in areas.items():
            if name not in self._areas or not isinstance(box, dict):
                continue

            # Canvas pixels → absolute screen position (undo menu offset on Y)
            abs_x = float(box.get("x", 0))
            abs_y = float(box.get("y", 0)) + menu_offset_logical
            abs_w = float(box.get("width", box.get("w", 0)))
            abs_h = float(box.get("height", box.get("h", 0)))
            # Convert absolute → relative to cached Roblox window
            rel_x = (abs_x - r_left) / r_w if r_w > 0 else 0.0
            rel_y = (abs_y - r_top) / r_h if r_h > 0 else 0.0
            rel_w = abs_w / r_w if r_w > 0 else 0.0
            rel_h = abs_h / r_h if r_h > 0 else 0.0
            self._areas[name] = {
                "x": rel_x,
                "y": rel_y,
                "width": rel_w,
                "height": rel_h,
            }
            self.parent_app.bar_areas[name] = dict(self._areas[name])
        self.parent_app.save_misc_settings()
        try:
            self.parent_app.set_status(f"Areas saved relative to Roblox ({int(r_left)}, {int(r_top)}, {int(r_w)}×{int(r_h)})")
        except Exception:
            pass

        self.hide()
    def request_save_and_close(self):
        """Ask the page to persist its current boxes before closing."""
        if not self._open or not self.overlay_window:
            return

        if not self._page_ready:
            self.hide()
            return

        self.overlay_window.evaluate_js("window.fishOverlay && window.fishOverlay.saveAndClose()")
    def draw_box(self, x1, y1, x2, y2, color, show_bar_center=False, label=""):
        """Evaluates JS drawing contexts based on calculations inside the viewport.
        bar_center / box_size / canvas_offset are in physical pixels relative to
        the fish capture region; they are converted to logical CSS pixels for
        the overlay canvas (which matches the logical window size).
        """
        # Ensure the overlay exists before trying to execute scripts on it
        if not self._open or not self.overlay_window:
            return

        scale = get_scale_factor()
        if scale <= 0:
            scale = 1.0
        shape = {
            "x1": int(x1 / scale),
            "y1": int(y1 / scale),
            "x2": int(x2 / scale),
            "y2": int(y2 / scale),
            "color": str(color),
            "show_bar_center": bool(show_bar_center),
            "label": str(label or "")
        }
        self._eval(f"window.fishOverlay && window.fishOverlay.draw({json.dumps(shape)})")
    def _eval(self, script):
        """Safely executes JavaScript strings within the running window environment.
        Calls made before the page is ready are queued — evaluate_js during
        create_window can fail and must not tear the overlay down (that was dropping the screenshot)."""
        if not (self.overlay_window and self._open):
            return

        if not self._page_ready:
            self._pending_js.append(script)
            return

        try:
            self.overlay_window.evaluate_js(script)
        except Exception:
            # Page may not be attached yet; keep the window and retry later.
            self._pending_js.append(script)
    def _flush_pending_js(self):
        if not (self.overlay_window and self._open and self._page_ready):
            return

        pending = self._pending_js
        self._pending_js = []
        for script in pending:
            try:
                self.overlay_window.evaluate_js(script)
            except Exception:
                self._pending_js.append(script)
    def _capture_and_crop(self):
        """Capture full screen and remove the macOS menu bar strip so the
        image matches the frameless window geometry (no menu bar)."""
        frame = self.parent_app.capture_single_frame()
        if frame is None:
            return None

        if frame.ndim == 3 and frame.shape[2] == 4:
            frame = frame[:, :, :3].copy()
        scale = get_scale_factor()
        macos_offset = get_macos_menu_offset()
        if scale <= 0:
            scale = 1.0
        self._scale = scale
        # Crop top (macOS menu bar) so canvas y=0 aligns with menu macos_offset
        menu_bar_pixels = int(round(macos_offset * scale))
        if 0 < menu_bar_pixels < frame.shape[0]:
            frame = frame[
                menu_bar_pixels:int(round(SCREEN_HEIGHT * scale)),
                0:int(round(SCREEN_WIDTH * scale)),
            ]
        frame = np.clip(frame.astype(np.int16) - 15, 0, 255).astype(np.uint8)
        return frame

    def _encode_screenshot(self, frame):
        """Encode BGR numpy frame as a JPEG data-URL for the canvas."""
        if frame is None:
            return None

        try:
            # Jpeg Keeps The Payload Small Enough For Evaluate_Js
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not ok:
                return None

            b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            return "data:image/jpeg;base64," + b64

        except Exception:
            return None

    def is_open(self):
        return self._open

    def _on_closed(self):
        """Internal callback cleaning lifecycle states upon execution exit."""
        self.overlay_window = None
        self._open = False
        self._visible = False
# Eyedropper Class
class Eyedropper:
    """
    Fullscreen transparent overlay for color picking using pywebview.
    Captures a frozen screenshot (menu bar cropped so it matches the frameless window), renders it in the canvas, and returns the picked color.
    """
    # Prevent Pywebview From Walking This Object When The Main Api Is Js_Api
    # (Window.Native.Accessibilityobject.Bounds Recursion / Webview2 Com).
    _serializable = False
    HTML_FILE = os.path.join(UI_PATH, "eyedropper.html")
    def __init__(self, parent_app):
        self.parent = parent_app
        self.eyedropper_window = None
        self._open = False
        self._visible = False
        self.last_picked_color = None
        self._cancelled = False
        self._color_key = None
        self._scale = 1.0
        self._screen_capture = None
        self._screenshot_b64 = None
        self.left = 0
        self.top = 0
        self.width = 0
        self.height = 0
    def _capture_and_crop(self):
        """Capture full screen and remove the macOS menu bar strip so the
        image matches the frameless window geometry (no menu bar)."""
        frame = self.parent.capture_single_frame()
        if frame is None:
            return None

        if frame.ndim == 3 and frame.shape[2] == 4:
            frame = frame[:, :, :3].copy()
        menu_offset = get_macos_menu_offset()
        scale = get_scale_factor()
        if scale <= 0:
            scale = 1.0
        self._scale = scale
        if menu_offset > 0:
            crop = int(round(menu_offset * scale))
            if 0 < crop < frame.shape[0]:
                frame = frame[crop:, :, :].copy()
        return frame

    def _encode_screenshot(self, frame):
        """Encode BGR numpy frame as a JPEG data-URL for the canvas."""
        if frame is None:
            return None

        try:
            # Jpeg Keeps The Payload Small Enough For Evaluate_Js
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not ok:
                return None

            b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            return "data:image/jpeg;base64," + b64

        except Exception:
            return None

    def show(self, color_key=None):
        """Open the eyedropper overlay. Optional color_key is the settings
        field that should receive the picked color (e.g. 'fish_color').
        Thin js_api object — only exposes the methods the HTML page calls.
        Do NOT pass `self` (or any object that holds a reference to the pywebview Window): on macOS Cocoa that triggers infinite recursion
        via AccessibilityObject.Bounds (same crash previously fixed for AreaSelector).
        """
        if self._open and self.eyedropper_window:
            return

        outer = self
        class _EyedropperApi:
            def window_ready(self, win_x, win_y):
                return outer.window_ready(win_x, win_y)

            def get_screenshot_data(self):
                return outer.get_screenshot_data()

            def get_pixel_at(self, x, y):
                return outer.get_pixel_at(x, y)

            def pick_color(self, hex_color):
                return outer.pick_color(hex_color)

            def close_eyedropper(self):
                return outer.close_eyedropper()

        self.last_picked_color = None
        self._cancelled = False
        self._color_key = color_key
        self._screen_capture = self._capture_and_crop()
        self._screenshot_b64 = self._encode_screenshot(self._screen_capture)
        menu_offset = get_macos_menu_offset()
        win_h = max(1, SCREEN_HEIGHT - menu_offset)
        self.left = SCREEN_LEFT
        self.top = SCREEN_TOP
        self.width = SCREEN_WIDTH
        self.height = win_h
        self.eyedropper_window = webview.create_window("Eyedropper", self.HTML_FILE, js_api=_EyedropperApi(), transparent=False, frameless=True, easy_drag=False, on_top=True, resizable=False, focus=True, width=self.width, height=self.height, x=self.left, y=self.top, background_color="#000000",)
        self._open = True
        self._visible = True
        self.eyedropper_window.events.closed += self._on_closed
        if sys.platform == "win32":
            # Maximize On Windows After The Window Is Created
            def maximize_area_selector():
                try:
                    hwnd = _get_hwnd(self.eyedropper_window)
                    if hwnd:
                        user32.ShowWindow(wintypes.HWND(hwnd), SW_MAXIMIZE)
                except Exception as e:
                    self.parent.set_status("Failed to maximize area selector:", e)
            self.eyedropper_window.events.shown += maximize_area_selector
        try:
            self.parent.set_status("Eyedropper opened • Hover to preview • Click to pick • Esc to cancel")
        except Exception:
            pass

    def is_open(self):
        return self._open and self.eyedropper_window is not None

    def hide(self):
        """Destroy the overlay without freezing the GUI.
        pywebview deadlocks if destroy() runs on the same window whose JS
        bridge is still inside pick_color() / close_eyedropper(). That also
        stalls the main window ("not responding"). Clear flags immediately,
        then destroy on a short-lived thread so the JS call can return first.
        """
        win = self.eyedropper_window
        if not win or not self._open:
            self._open = False
            self._visible = False
            return

        self._open = False
        self._visible = False
        self.eyedropper_window = None
        _schedule_webview_destroy(win, after=self._on_closed)
    def close(self):
        """Alias used by shutdown / toggle paths."""
        self.hide()
    # ── Js Api Methods (Called From Eyedropper.Html) ──
    def window_ready(self, win_x, win_y):
        """JS signals the page is ready — push the frozen screenshot."""
        if self._screenshot_b64 and self.eyedropper_window and self._open:
            # Inject Via A Short Data Reference; Js Stores It And Draws.
            try:
                # Pass As Return Value Of A Dedicated Getter Instead Of
                # Embedding A Huge String In Evaluate_Js When Possible.
                self.eyedropper_window.evaluate_js("window.__applyScreenshot && window.__applyScreenshot()")
            except Exception:
                pass

        return None

    def get_screenshot_data(self):
        """Return the data-URL of the frozen (menu-bar-cropped) screenshot."""
        return self._screenshot_b64 or ""

    def get_pixel_at(self, x, y):
        """Sample the frozen capture at logical canvas coordinates (x, y).
        Menu bar was already cropped out, so no y-offset is needed."""
        if not self.is_open():
            return "#000000"

        frame = self._screen_capture
        if frame is None:
            return "#000000"

        scale = self._scale if self._scale > 0 else 1.0
        px = int(x * scale)
        py = int(y * scale)
        if px < 0 or py < 0 or py >= frame.shape[0] or px >= frame.shape[1]:
            return "#000000"

        b = int(frame[py, px, 0])
        g = int(frame[py, px, 1])
        r = int(frame[py, px, 2])
        hex_color = f"#{r:02X}{g:02X}{b:02X}"
        try:
            self.parent.set_status(f"{hex_color} • Click to pick • Esc to cancel")
        except Exception:
            pass

        return hex_color

    def pick_color(self, hex_color):
        """Called by JS when user clicks to pick a color.
        Stores the color, pushes it to the main UI, and closes the overlay."""
        if not self.is_open():
            return None

        if not hex_color or not isinstance(hex_color, str):
            return None

        hex_color = hex_color.strip()
        if not hex_color.startswith("#"):
            hex_color = "#" + hex_color
        self.last_picked_color = hex_color
        self._cancelled = False
        # Write Into Settings Vars When A Target Key Was Provided
        color_key = self._color_key
        if color_key:
            try:
                self.parent.vars[color_key] = hex_color
            except Exception:
                pass

        # Notify The Main Webview So The Color Input Updates
        self._notify_main_ui(hex_color, color_key)
        try:
            self.parent.set_status(f"Picked color: {hex_color}")
        except Exception:
            pass

        self.hide()
        return hex_color

    def close_eyedropper(self):
        """Called by JS on Escape — cancel without picking."""
        if not self.is_open():
            return

        self._cancelled = True
        self.last_picked_color = None
        try:
            self.parent.set_status("Eyedropper cancelled")
        except Exception:
            pass

        self.hide()
    def _notify_main_ui(self, hex_color, color_key=None):
        """Push the picked color into the main pywebview window."""
        try:
            safe = hex_color.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
            key_js = "null"
            if color_key:
                key_js = "'" + str(color_key).replace("\\", "\\\\").replace("'", "\\'") + "'"
            script = (
                f"(function(){{"
                f"var c='{safe}',k={key_js};"
                f"if(window.onColorPicked)window.onColorPicked(c,k);"
                f"if(window.setPickedColor)window.setPickedColor(c,k);"
                f"if(k){{var el=document.getElementById(k)||document.querySelector('[data-color-key=\"'+k+'\"]')"
                f"||document.querySelector('input[name=\"'+k+'\"]');"
                f"if(el){{el.value=c;el.dispatchEvent(new Event('input',{{bubbles:true}}));"
                f"el.dispatchEvent(new Event('change',{{bubbles:true}}));}}"
                f"}}"
                f"}})()"
            )
            # Main Window Is The First Created Window
            if webview.windows:
                webview.windows[0].evaluate_js(script)
        except Exception:
            pass

    def _on_closed(self, *args):
        """Lifecycle cleanup when the overlay is destroyed."""
        self.eyedropper_window = None
        self._open = False
        self._visible = False
        self._screenshot_b64 = None
        # Keep Last_Picked_Color So The Main Ui Can Still Poll It
class FishOverlay:
    # Prevent Pywebview From Walking This Object When The Main Api Is Js_Api
    # (Window.Native.Accessibilityobject.Bounds Recursion / Webview2 Com).
    _serializable = False
    HTML_FILE = os.path.join(UI_PATH, "fish_overlay.html")
    def __init__(self, parent_app):
        self.parent_app = parent_app
        self._overlay_window = None
        self._open = False
        self._visible = False
        # Track Active Viewport Geometry (Logical Points For Pywebview)
        self.left = 0
        self.top = 0
        self.width = 0
        self.height = 0
    def _to_window_coords(self, left, top, width, height):
        """
        Convert physical-pixel geometry (from _get_areas / capture) into the
        logical points pywebview expects for window x/y/width/height.
        On Windows scale is always 1; on macOS Retina it is typically 2.0.
        Also clamps width/height so a bad (e.g. post-reset) size cannot make
        the overlay cover the entire screen or exceed monitor bounds.
        """
        scale = get_scale_factor()
        if scale <= 0:
            scale = 1.0
        left = int(left / scale)
        top = int(top / scale)
        width = max(1, int(width / scale))
        height = max(1, int(height / scale))
        # Clamp So The Window Stays Onscreen (Logical Screen Size)
        screen_w = max(1, SCREEN_WIDTH)
        screen_h = max(1, SCREEN_HEIGHT)
        width = min(width, screen_w)
        height = min(height, screen_h)
        left = max(0, min(left, max(0, screen_w - width)))
        top = max(0, min(top, max(0, screen_h - height)))
        return left, top, width, height

    def show(self, left, top, width, height):
        """Creates and displays the transparent frameless overlay window.
        Arguments are physical-pixel screen coordinates (same space as _get_areas / capture_frame). They are converted to logical points
        for pywebview.
        """
        left, top, width, height = self._to_window_coords(left, top, width, height)
        if self._open and self._overlay_window:
            # If Already Open, Shift/Resize It Instead Of Duplicating
            self.resize(left, top, width, height, already_logical=True)
            return

        self.left = left
        self.top = top
        self.width = width
        self.height = height
        self._overlay_window = webview.create_window("Fish Overlay", url=self.HTML_FILE, transparent=False, frameless=True, easy_drag=False, on_top=True, resizable=False, focus=False, width=self.width, height=self.height, x=self.left, y=self.top, background_color="#ffffff", min_size=(0.03 * SCREEN_WIDTH, 0.05 * SCREEN_HEIGHT),)
        self._open = True
        self._visible = True
        self._overlay_window.events.closed += self._on_closed
    def hide(self):
        """Destroys the current window instance completely.
        Clear _open BEFORE destroy so concurrent minigame threads that still
        call clear()/draw_box()/_eval skip the disposed WebView2 and avoid
        ObjectDisposedException (logged by pywebview as 'Error occurred in script').
        Destroy is scheduled off the caller thread so a stop/hotkey/shutdown
        path cannot deadlock pywebview the way Eyedropper/AreaSelector did.
        """
        win = self._overlay_window
        if not win or not self._open:
            self._open = False
            self._visible = False
            return

        self._open = False
        self._visible = False
        self._overlay_window = None
        _schedule_webview_destroy(win, after=self._on_closed)
    def resize(self, left, top, width, height, already_logical=False):
        """Resizes and moves the window dynamically if it exists.
        By default arguments are physical pixels (same as show()).
        Pass already_logical=True when the caller has already converted them.
        """
        if not already_logical:
            left, top, width, height = self._to_window_coords(left, top, width, height)
        self.left = left
        self.top = top
        self.width = width
        self.height = height
        if self._overlay_window and self._open:
            try:
                self._overlay_window.move(self.left, self.top)
                self._overlay_window.resize(self.width, self.height)
            except Exception:
                # Window May Already Be Disposed (Race With Stop_Macro / Hide)
                self._open = False
                self._overlay_window = None
    def clear(self):
        """Clears rendering elements inside the web view context."""
        self._eval("window.fishOverlay && window.fishOverlay.clear()")
    def draw_box(self, x1, y1, x2, y2, color, show_bar_center=False):
        """Evaluates JS drawing contexts based on calculations inside the viewport.
        bar_center / box_size / canvas_offset are in physical pixels relative to
        the fish capture region; they are converted to logical CSS pixels for
        the overlay canvas (which matches the logical window size).
        """
        # Ensure The Overlay Exists Before Trying To Execute Scripts On It
        if not self._open or not self._overlay_window:
            return

        # Failsafe if shape is None
        if x1 is None:
            return

        scale = get_scale_factor()
        if scale <= 0:
            scale = 1.0
        shape = {
            "x1": int(x1 / scale),
            "y1": int(y1 / scale),
            "x2": int(x2 / scale),
            "y2": int(y2 / scale),
            "color": str(color),
            "show_bar_center": bool(show_bar_center)
        }
        self._eval(f"window.fishOverlay && window.fishOverlay.draw({json.dumps(shape)})")
    def _eval(self, script):
        """Safely executes JavaScript strings within the running window environment.
        Catches ObjectDisposedException (and any other failure) that can occur
        when the overlay is destroyed from another thread while the minigame
        loop is still drawing."""
        if not (self._overlay_window and self._open):
            return

        try:
            self._overlay_window.evaluate_js(script)
        except Exception:
            # Webview2 May Already Be Disposed; Mark Closed So We Stop Trying
            self._open = False
            self._overlay_window = None
    def _on_closed(self):
        """Internal callback cleaning lifecycle states upon execution exit."""
        self._overlay_window = None
        self._open = False
        self._visible = False
class StatusOverlay:
    # Prevent Pywebview From Walking This Object When The Main Api Is Js_Api.
    # Statusoverlay.Show() Runs During Api.__Init__, So Overlay_Window Is A Live
    # Window By The Time Create_Window(..., Js_Api=Api) Runs — That Is What
    # Produced Status_Overlay.Overlay_Window.Native.Accessibilityobject.Bounds
    # recursion and the WebView2 "must be accessed from the UI thread" errors.
    _serializable = False
    HTML_FILE = os.path.join(UI_PATH, "status_overlay.html")
    def __init__(self, parent_app):
        self.parent_app = parent_app
        self._overlay_window = None
        self._open = False
        self._visible = False
        # Track Active Viewport Geometry
        # (Logical Points For Pywebview)
        self.left = 0
        self.top = 0
        self.width = 0
        self.height = 0
    def _to_window_coords(self, left, top, width, height):
        """
        Convert physical-pixel geometry into logical points
        for pywebview.
        On Windows scale is usually 1.
        On macOS Retina it is typically 2.0.
        """
        scale = get_scale_factor()
        if scale <= 0:
            scale = 1.0
        left = int(left / scale)
        top = int(top / scale)
        width = max(1, int(width / scale))
        height = max(1, int(height / scale))
        # Clamp Window Dimensions To Screen Bounds
        screen_w = max(1, SCREEN_WIDTH)
        screen_h = max(1, SCREEN_HEIGHT)
        width = min(width, screen_w)
        height = min(height, screen_h)
        left = max(0, min(left, max(0, screen_w - width)))
        top = max(0, min(top, max(0, screen_h - height)))
        return left, top, width, height

    def show(self, left, top, width, height):
        """
        Creates and displays the status overlay window.
        Arguments are physical-pixel screen coordinates.
        """
        left, top, width, height = self._to_window_coords(left, top, width, height)
        if self._open and self._overlay_window:
            self.resize(left, top, width, height, already_logical=True)
            return

        self.left = left
        self.top = top
        self.width = width
        self.height = height
        self._overlay_window = webview.create_window("Status Overlay", url=self.HTML_FILE, transparent=False, frameless=True, easy_drag=False, on_top=True, resizable=False, focus=False, width=self.width, height=self.height, x=self.left, y=self.top, background_color="#000000", min_size=(0.1 * SCREEN_WIDTH, 0.1 * SCREEN_HEIGHT),)
        self._open = True
        self._visible = True
        self._overlay_window.events.closed += self._on_closed
    def hide(self):
        """
        Destroys the current window instance completely.
        Scheduled so hide() from stop_macro / main-window close cannot
        deadlock the pywebview GUI thread.
        """
        win = self._overlay_window
        if not win or not self._open:
            self._open = False
            self._visible = False
            return

        self._open = False
        self._visible = False
        self._overlay_window = None
        _schedule_webview_destroy(win, after=self._on_closed)
    def resize(self, left, top, width, height, already_logical=False):
        """
        Resizes and moves the window dynamically.
        By default arguments are physical pixels.
        Pass already_logical=True when already converted.
        """
        if not already_logical:
            left, top, width, height = self._to_window_coords(left, top, width, height)
        self.left = left
        self.top = top
        self.width = width
        self.height = height
        if self._overlay_window and self._open:
            try:
                self._overlay_window.move(self.left, self.top)
                self._overlay_window.resize(self.width, self.height)
            except Exception:
                self._open = False
                self._overlay_window = None
    def set_title(self, title):
        """
        Updates the overlay title.
        """
        self._eval(f"window.statusOverlay && " f"window.statusOverlay.setTitle(" f"{json.dumps(str(title))})")
    def set_main_status(self, status):
        """
        Updates the main process/status label.
        """
        self._eval(f"window.statusOverlay && " f"window.statusOverlay.setMainStatus(" f"{json.dumps(str(status))})")
    def set_line(self, number, label, value):
        """
        Updates one of the four status lines.
        number must be 1, 2, 3, or 4.
        """
        if number not in (1, 2, 3, 4):
            raise ValueError("Status line number must be 1, 2, 3, or 4")

        self._eval(f"window.statusOverlay && " f"window.statusOverlay.setLine(" f"{number}, " f"{json.dumps(str(label))}, " f"{json.dumps(str(value))})")
    def set_status(self, title, main_status, line1, line2, line3, line4=None):
        """
        Updates the entire status overlay.
        Each line should be a (label, value) tuple.
        line4 is optional.
        """
        self.set_title(title)
        self.set_main_status(main_status)
        self.set_line(1, line1[0], line1[1])
        self.set_line(2, line2[0], line2[1])
        self.set_line(3, line3[0], line3[1])
        if line4 is not None:
            self.set_line(4, line4[0], line4[1])
    def clear(self):
        """
        Resets the status overlay to its default state.
        """
        self._eval("window.statusOverlay && " "window.statusOverlay.clear()")
    def _eval(self, script):
        """
        Safely executes JavaScript within the WebView.
        Prevents calls against a WebView that has already been destroyed.
        """
        if not (self._overlay_window and self._open):
            return

        try:
            self._overlay_window.evaluate_js(script)
        except Exception:
            self._open = False
            self._overlay_window = None
    def _on_closed(self):
        """
        Cleans lifecycle state when the window closes.
        """
        self._overlay_window = None
        self._open = False
        self._visible = False
class PointSelect:
    """
    Fullscreen overlay for selecting a screen point as normalized ratios (0-1).
    Captures a frozen screenshot (menu bar cropped so it matches the frameless window), renders it in the canvas, and returns the picked ratios.
    """
    # Prevent Pywebview From Walking This Object When The Main Api Is Js_Api
    # (Window.Native.Accessibilityobject.Bounds Recursion / Webview2 Com).
    _serializable = False
    HTML_FILE = os.path.join(UI_PATH, "point_select.html")
    def __init__(self, parent_app):
        self.parent = parent_app
        self.overlay_window = None
        self._open = False
        self._visible = False
        self.last_picked = None
        self._cancelled = False
        self._field_id = None
        self._scale = 1.0
        self._screen_capture = None
        self._screenshot_b64 = None
        self.left = 0
        self.top = 0
        self.width = 0
        self.height = 0
    def is_open(self):
        return self._open and self.overlay_window is not None

    def _capture_and_crop(self):
        """Capture full screen and remove the macOS menu bar strip so the
        image matches the frameless window geometry (no menu bar)."""
        frame = self.parent.capture_single_frame()
        if frame is None:
            return None

        if frame.ndim == 3 and frame.shape[2] == 4:
            frame = frame[:, :, :3].copy()
        menu_offset = get_macos_menu_offset()
        scale = get_scale_factor()
        if scale <= 0:
            scale = 1.0
        self._scale = scale
        if menu_offset > 0:
            crop = int(round(menu_offset * scale))
            if 0 < crop < frame.shape[0]:
                frame = frame[crop:, :, :].copy()
        return frame

    def _encode_screenshot(self, frame):
        """Encode BGR numpy frame as a JPEG data-URL for the canvas."""
        if frame is None:
            return None

        try:
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not ok:
                return None

            b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            return "data:image/jpeg;base64," + b64

        except Exception:
            return None

    def show(self, field_id=None):
        """Open the point selector overlay. Optional field_id is the settings
        field that should receive the picked ratios (e.g. 'mirror_ratio').
        Thin js_api object — only exposes the methods the HTML page calls.
        Do NOT pass `self` (or any object that holds a reference to the pywebview Window): on macOS Cocoa that triggers infinite recursion
        via AccessibilityObject.Bounds.
        """
        if self._open and self.overlay_window:
            return

        outer = self
        class _PointSelectApi:
            def window_ready(self, win_x, win_y, width=None, height=None):
                return outer.window_ready(win_x, win_y, width, height)

            def get_screenshot_data(self):
                return outer.get_screenshot_data()

            def get_geometry(self):
                return outer.get_geometry()

            def pick_point(self, ratio_x, ratio_y):
                return outer.pick_point(ratio_x, ratio_y)

            def close_point_select(self):
                return outer.close_point_select()

        self.last_picked = None
        self._cancelled = False
        self._field_id = field_id
        self._screen_capture = self._capture_and_crop()
        self._screenshot_b64 = self._encode_screenshot(self._screen_capture)
        menu_offset = get_macos_menu_offset()
        win_h = max(1, SCREEN_HEIGHT - menu_offset)
        self.left = SCREEN_LEFT
        self.top = SCREEN_TOP + int(round(menu_offset))
        self.width = SCREEN_WIDTH
        self.height = win_h
        self.overlay_window = webview.create_window("Point Select", self.HTML_FILE, js_api=_PointSelectApi(), transparent=False, frameless=True, easy_drag=False, on_top=True, resizable=False, focus=True, width=self.width, height=self.height, x=self.left, y=self.top, background_color="#000000",)
        self._open = True
        self._visible = True
        self.overlay_window.events.closed += self._on_closed
        if sys.platform == "win32":
            def maximize_point_select():
                try:
                    hwnd = _get_hwnd(self.overlay_window)
                    if hwnd:
                        user32.ShowWindow(wintypes.HWND(hwnd), SW_MAXIMIZE)
                except Exception:
                    pass

            self.overlay_window.events.shown += maximize_point_select
    def hide(self):
        """Destroys the current window instance completely.
        Destroy is scheduled off the JS-API thread to avoid pywebview deadlock.
        """
        win = self.overlay_window
        if not win or not self._open:
            self._open = False
            self._visible = False
            return

        self._open = False
        self._visible = False
        self.overlay_window = None
        _schedule_webview_destroy(win, after=self._on_closed)
    def window_ready(self, win_x, win_y, width=None, height=None):
        """JS signals the page is ready — push screenshot."""
        if self._screenshot_b64 and self.overlay_window and self._open:
            try:
                self.overlay_window.evaluate_js("window.__applyScreenshot && window.__applyScreenshot()")
            except Exception:
                pass

        return None

    def get_screenshot_data(self):
        """Return the data-URL of the frozen (menu-bar-cropped) screenshot."""
        return self._screenshot_b64 or ""

    def get_geometry(self):
        """Return logical screen geometry so JS can compute full-screen ratios.
        menu_offset is the height of the cropped menu bar (logical pixels).
        screen_w / screen_h are the full logical screen dimensions.
        """
        menu_offset = get_macos_menu_offset()
        return {

            "menu_offset": float(menu_offset),
            "screen_w": float(SCREEN_WIDTH),
            "screen_h": float(SCREEN_HEIGHT),
        }
    def pick_point(self, ratio_x, ratio_y):
        """Called by JS when the user clicks.
        ratio_x / ratio_y are already normalized 0–1 relative to the overlay
        viewport (computed in JS from clientX/Y ÷ innerWidth/Height)."""
        if not self.is_open():
            return None

        try:
            rx = max(0.0, min(1.0, float(ratio_x)))
            ry = max(0.0, min(1.0, float(ratio_y)))
        except (TypeError, ValueError):
            return None

        self.last_picked = (rx, ry)
        self._cancelled = False
        label = f"{rx:.3f}, {ry:.3f}"
        # Write into settings vars when a target key was provided
        field_id = self._field_id
        if field_id:
            try:
                self.parent.vars[field_id] = label
            except Exception:
                pass

        # Notify the main webview so the input updates
        self._notify_main_ui(label, field_id)
        try:
            self.parent.set_status(f"Selected point: {label}")
        except Exception:
            pass

        self.hide()
        return label

    def close_point_select(self):
        """Called by JS on Escape — cancel without picking."""
        if not self.is_open():
            return

        self._cancelled = True
        self.last_picked = None
        try:
            self.parent.set_status("Point select cancelled")
        except Exception:
            pass

        self.hide()
    def _notify_main_ui(self, label, field_id=None):
        """Push the picked ratios into the main pywebview window."""
        try:
            safe = str(label).replace("\\", "\\\\").replace("'", "\\'")
            key_js = "null"
            if field_id:
                key_js = "'" + str(field_id).replace("\\", "\\\\").replace("'", "\\'") + "'"
            script = (
                f"(function(){{"
                f"var v='{safe}',k={key_js};"
                f"if(window.onPointPicked)window.onPointPicked(v,k);"
                f"if(k){{var el=document.getElementById(k)||document.querySelector('[data-point-key=\"'+k+'\"]')"
                f"||document.querySelector('input[name=\"'+k+'\"]');"
                f"if(el){{el.value=v;el.dispatchEvent(new Event('input',{{bubbles:true}}));"
                f"el.dispatchEvent(new Event('change',{{bubbles:true}}));}}"
                f"}}"
                f"}})()"
            )
            if webview.windows:
                webview.windows[0].evaluate_js(script)
        except Exception:
            pass

    def _on_closed(self, *args):
        """Lifecycle cleanup when the overlay is destroyed."""
        self.overlay_window = None
        self._open = False
        self._visible = False
        self._screenshot_b64 = None

class ScreenScanner:
    """
    Soft color seeds → morph → components → box filters.
    Fallbacks: mid-X column scan. Sticky last boxes so color flips don't drop track.
    """

    def __init__(self) -> 'None':
        self._last_zone = None
        self._last_white = None
        self._zone_misses = 0
        self._white_misses = 0
        self._zone_hold_miss_frames = DEFAULT_ZONE_HOLD_MISS_FRAMES
        self._white_hold_miss_frames = DEFAULT_WHITE_HOLD_MISS_FRAMES
        self._zone_rgb = np.zeros((0, 3), dtype=np.int16)
        self._zone_rgb_tol = 28
        try:
            with COLORS_PATH.open('r', encoding='utf-8') as f:
                data = json.load(f)
            samples = list(data.get('yellow') or []) + list(data.get('green') or [])
            self._zone_rgb = _bgr_samples(samples)
            self._zone_rgb_tol = max(28, int(data.get('rgb_tol', 12)) + 16)
        except Exception:
            return

    def configure(self, *, zone_rgb_tol: 'float | None'=None, zone_hold_miss_frames: 'float | None'=None, white_hold_miss_frames: 'float | None'=None) -> 'None':
        if zone_rgb_tol is not None:
            self._zone_rgb_tol = max(4, int(round(float(zone_rgb_tol))))
        if zone_hold_miss_frames is not None:
            self._zone_hold_miss_frames = max(0, int(round(float(zone_hold_miss_frames))))
        if white_hold_miss_frames is not None:
            self._white_hold_miss_frames = max(0, int(round(float(white_hold_miss_frames))))

    def reset_tracking(self) -> 'None':
        self._last_zone = None
        self._last_white = None
        self._zone_misses = 0
        self._white_misses = 0

    @staticmethod
    def _components(mask_u8: 'np.ndarray') -> 'list[tuple[int, int, int, int, int]]':
        n, _lab, stats, _cent = cv2.connectedComponentsWithStats(mask_u8, connectivity=8)
        out = []
        for i in range(1, n):
            x, y, w, h, a = (int(v) for v in stats[i])
            out.append((x, y, w, h, a))
        return out

    def _zone_mask(self, bgr: 'np.ndarray', hsv: 'np.ndarray') -> 'np.ndarray':
        h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
        band_a = (h >= 10) & (h <= 65) & (s >= 12) & (v >= 12)
        band_b = (h >= 60) & (h <= 100) & (s >= 35) & (v >= 35)
        by_hsv = band_a | band_b
        mask = by_hsv.astype(np.uint8) * 255
        if self._zone_rgb.size:
            pix = bgr.astype(np.int16)
            diff = np.abs(pix[:, :, None, :] - self._zone_rgb[None, None, :, :])
            by_rgb = np.any(np.max(diff, axis=3) <= self._zone_rgb_tol, axis=2)
            mask = np.where(by_rgb, 255, mask).astype(np.uint8)
        return mask

    def _find_zone_by_rows(self, bgr: 'np.ndarray', hsv: 'np.ndarray') -> 'Box | None':
        '''
        Fallback: rows with enough zone-colored pixels across the bar width.
        Survives thin borders / washed fills / H-shifted translucency.
        '''

        h, w = bgr.shape[:2]
        mask = self._zone_mask(bgr, hsv)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, max(9, w // 3)), np.uint8))
        row_frac = (mask > 0).sum(axis=1) / max(w, 1)
        for thresh in (0.1, 0.05, 0.03):
            ys = np.flatnonzero(row_frac >= thresh)
            if ys.size < 5:
                continue
            top, bot = int(ys[0]), int(ys[-1])
            height = bot - top + 1
            if height < 14 or height > h * 0.75:
                continue
            bw = max(int(w * 0.55), 24)
            x0 = max(0, (w - bw) // 2)
            return Box(x0, top, min(bw, w - x0), height)

    def _white_mask(self, hsv: 'np.ndarray') -> 'np.ndarray':
        return ((hsv[:, :, 2] >= 145) & (hsv[:, :, 1] <= 110)).astype(np.uint8) * 255

    def _find_white_component(self, bgr: 'np.ndarray', hsv: 'np.ndarray') -> 'Box | None':
        h, w = bgr.shape[:2]
        mask = self._white_mask(hsv)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        best = None
        best_score = -1.0
        for x, y, bw, bh, area in self._components(mask):
            if not bw < 8:
                if bh < 8 or area < 80:
                    continue
                aspect = bw / max(bh, 1)
                fill = area / max(bw * bh, 1)
                if 0.55 <= aspect <= 1.55:
                    if not fill >= 0.4:
                        continue
                if 10 <= bw <= w * 0.7:
                    if not 10 <= bh <= h * 0.35:
                        continue
                score = fill * area
                if self._last_white is not None:
                    dy = abs(y + bh // 2 - self._last_white.mid_y)
                    dx = abs(x + bw // 2 - self._last_white.mid_x)
                    score += max(0.0, 600.0 - (dy + dx) * 2.0)
                if not score > best_score:
                    continue
                best_score = score
                best = Box(x, y, bw, bh)
        return best

    def _find_white_on_column(self, hsv: 'np.ndarray', mid_x: 'int') -> 'Box | None':
        h, w = hsv.shape[:2]
        if mid_x < 0 or mid_x >= w:
            return
        best_run = None
        for dx in range(-4, 5):
            x = mid_x + dx
            if x < 0 or x >= w:
                continue
            col_v = hsv[:, x, 2]
            col_s = hsv[:, x, 1]
            hit = (col_v >= 145) & (col_s <= 110)
            run = _largest_run(hit)
            if run is not None:
                top, bot = run
                height = bot - top + 1
                if height < 8 or height > h * 0.35:
                    continue
                score = height - abs(dx) * 2
                if best_run is None or score > best_run[2]:
                    best_run = top, bot, score
        if best_run is None:
            return
        top, bot, _ = best_run
        side = max(10, bot - top + 1)
        x0 = max(0, mid_x - side // 2)
        return Box(x0, top, min(side, w - x0), bot - top + 1)

    def _find_zone_component(self, bgr: 'np.ndarray', hsv: 'np.ndarray') -> 'Box | None':
        h, w = bgr.shape[:2]
        mask = self._zone_mask(bgr, hsv)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
        best = None
        best_score = -1.0
        for x, y, bw, bh, area in self._components(mask):
            if not bw < 10:
                if bh < 20 or area < 150:
                    continue
                aspect = bw / max(bh, 1)
                fill = area / max(bw * bh, 1)
                min_fill = 0.1 if bw >= w * 0.4 else 0.18
                if 0.5 <= aspect <= 4.5:
                    if not fill >= min_fill:
                        continue
                if not (bw >= w * 0.3 and bh <= h * 0.6):
                    continue
                score = fill * area * (bw / max(w, 1))
                if self._last_zone is not None:
                    dy = abs(y + bh // 2 - self._last_zone.mid_y)
                    dx = abs(x + bw // 2 - self._last_zone.mid_x)
                    score += max(0.0, 1200.0 - (dy + dx) * 2.5)
                if not score > best_score:
                    continue
                best_score = score
                best = Box(x, y, bw, bh)
            continue
        return best

    def _find_zone_on_column(self, bgr: 'np.ndarray', hsv: 'np.ndarray', mid_x: 'int') -> 'Box | None':
        '''GPO-style: largest contiguous zone run on mid_X (very tolerant).'''

        h, w = bgr.shape[:2]
        if mid_x < 0 or mid_x >= w:
            return
        mask = self._zone_mask(bgr, hsv) > 0
        col = np.zeros(h, dtype=bool)
        for dx in range(-5, 6):
            x = mid_x + dx
            if 0 <= x < w:
                col |= mask[:, x]
        run = _largest_run(col)
        if run is None:
            ys = np.flatnonzero(col)
            if ys.size >= 6:
                top, bot = int(ys[0]), int(ys[-1])
                if bot - top + 1 >= 14:
                    run = top, bot
        if run is None:
            return
        top, bot = run
        height = bot - top + 1
        if height < 14 or height > h * 0.7:
            return
        bw = max(int(w * 0.55), 24)
        x0 = max(0, mid_x - bw // 2)
        bw = min(bw, w - x0)
        return Box(x0, top, bw, height)

    def find_white_box(self, bgr: 'np.ndarray') -> 'Box | None':
        if bgr.size == 0:
            return
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        box = self._find_white_component(bgr, hsv)
        if box is None and self._last_white is not None:
            box = self._find_white_on_column(hsv, self._last_white.mid_x)
        if box is None and self._last_zone is not None:
            box = self._find_white_on_column(hsv, self._last_zone.mid_x)
        if box is not None:
            self._last_white = box
            self._white_misses = 0
            return box
        self._white_misses += 1
        if self._last_white is not None and self._white_misses <= self._white_hold_miss_frames:
            return self._last_white
        self._last_white = None

    def find_zone_box(self, bgr: 'np.ndarray') -> 'Box | None':
        if bgr.size == 0:
            return
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        box = self._find_zone_component(bgr, hsv)
        if box is None:
            mid = None
            if self._last_white is not None:
                mid = self._last_white.mid_x
            elif self._last_zone is not None:
                mid = self._last_zone.mid_x
            if mid is not None:
                box = self._find_zone_on_column(bgr, hsv, mid)
        if box is None:
            box = self._find_zone_by_rows(bgr, hsv)
        if box is not None:
            self._last_zone = box
            self._zone_misses = 0
            return box
        self._zone_misses += 1
        if self._last_zone is not None and self._zone_misses <= self._zone_hold_miss_frames:
            return self._last_zone
        self._last_zone = None

    def detect(self, bgr: 'np.ndarray') -> 'tuple[Box | None, Box | None]':
        '''White + zone in one pass (shared HSV).'''

        if bgr.size == 0:
            return (None, None)
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        white = self._find_white_component(bgr, hsv)
        if white is None and self._last_white is not None:
            white = self._find_white_on_column(hsv, self._last_white.mid_x)
        if white is None and self._last_zone is not None:
            white = self._find_white_on_column(hsv, self._last_zone.mid_x)
        if white is not None:
            self._last_white = white
            self._white_misses = 0
        else:
            self._white_misses += 1
            if self._last_white is not None and self._white_misses <= self._white_hold_miss_frames:
                white = self._last_white
            else:
                self._last_white = None
                white = None
        zone = self._find_zone_component(bgr, hsv)
        if zone is None:
            mid = white.mid_x if white is not None else self._last_zone.mid_x if self._last_zone is not None else None
            if mid is not None:
                zone = self._find_zone_on_column(bgr, hsv, mid)
        if zone is None:
            zone = self._find_zone_by_rows(bgr, hsv)
        if zone is not None:
            self._last_zone = zone
            self._zone_misses = 0
            return white, zone
        self._zone_misses += 1
        if self._last_zone is not None and self._zone_misses <= self._zone_hold_miss_frames:
            zone = self._last_zone
            return white, zone
        self._last_zone = None
        zone = None
        return white, zone

    def white_present(self, bgr: 'np.ndarray') -> 'bool':
        '''Fresh white detection (no sticky hold) — for minigame start/end.'''

        if bgr.size == 0:
            return False
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        if self._find_white_component(bgr, hsv) is not None:
            return True
        mid = None
        if self._last_white is not None:
            mid = self._last_white.mid_x
        elif self._last_zone is not None:
            mid = self._last_zone.mid_x
        else:
            mid = bgr.shape[1] // 2
        return self._find_white_on_column(hsv, mid) is not None

    def find_zone_center_x(self, bgr: 'np.ndarray') -> 'tuple[int, int, int, int] | None':
        box = self.find_white_box(bgr)
        if box is None:
            return
        return box.mid_x, box.x, box.x + box.w - 1, box.y

    def find_green_extents_on_x(self, bgr: 'np.ndarray', mid_x: 'int') -> 'tuple[int, int] | None':
        box = self.find_zone_box(bgr)
        if box is None:
            return
        return box.top, box.bottom

    def find_white_mid_y_on_x(self, bgr: 'np.ndarray', mid_x: 'int') -> 'int | None':
        box = self.find_white_box(bgr)
        if box is None:
            return
        return box.mid_y

class Api:
    def __init__(self):
        self.vars = {} # Save Entry Variables Here
        self.current_config = "settings"
        # Load settings.json into vars before hotkeys or the macro run.
        try:
            self.load_settings()
        except Exception:
            pass

        # Start Hotkey Listener
        self.hotkey_state = 0
        self.rebind_target = None
        try:
            self.key_listener = KeyListener(on_press=self.on_key_press)
            self.key_listener.daemon = True
            self.key_listener.start()
        except Exception as e:
            self.set_status(f"Key Listener error: {e}")
        # Store Screen Width And Height To Use Later
        self.SCREEN_WIDTH = SCREEN_WIDTH
        self.SCREEN_HEIGHT = SCREEN_HEIGHT
        self.SCREEN_LEFT = SCREEN_LEFT
        self.SCREEN_TOP = SCREEN_TOP
        self.SCREEN_SCALE = ((self.SCREEN_WIDTH / 1920) + (self.SCREEN_HEIGHT / 1080)) / 2
        # Macro State
        self.macro_running = False
        self.macro_thread = None
        # Screen Capture
        self.capture_thread = None
        self.capture_frame = None
        self.capture_id = 0
        self.scan_delay = 0.1
        # Utility Classes
        self.area_selector = AreaSelector(self)
        self.eyedropper = Eyedropper(self)
        self.fish_overlay = FishOverlay(self)
        self.status_overlay = StatusOverlay(self)
        self.point_select = PointSelect(self)
        # Safe Defaults Before Key Listener Starts (Will Be Overwritten By Load_Misc_Settings)
        self.js_version_info = {}
        scale = get_scale_factor()
        menu_offset = get_macos_menu_offset()
        self.bar_areas = {name: None for name in AREA_ORDER}
        self.roblox_bounds_cache = None
        self.current_rod_name = "Default"
        self.session_start = 0.0
        self.catch_rate = 0.0
        # Message box synchronization (custom banner)
        self.misc_settings = {}
        self._message_box_event = None
        self._message_box_result = None
        self.perfect_catch_rate = 0.0
        self.current_cycle = 0
        self.scale_x_1440 = SCREEN_WIDTH / 2560
        self.scale_y_1440 = SCREEN_HEIGHT / 1440
        self.scale_x_1080 = SCREEN_WIDTH / 1920
        self.scale_y_1080 = SCREEN_HEIGHT / 1080
        self.status_left = 20
        self.status_top = (menu_offset * scale) + 40
        self.status_right = (300 * scale * self.scale_x_1080)
        self.status_bottom = (230 * scale * self.scale_y_1080)
        self.status_overlay.hide()
        self._ensure_default_config()
        # check_setup_guide is called from window.events.loaded (see main window setup)
        # so that the pywebview window exists before evaluate_js is used.
    def _html_attr(self, attrs, name):
        match = re.search(r"""\b""" + re.escape(name) + r"""\s*=\s*(?:['"]([^'"]*)['"]|([^\s>]+))""", attrs, re.IGNORECASE,)
        if not match:
            return None

        return (match.group(1) if match.group(1) is not None else match.group(2) or "").strip()

    def _get_prompt_defaults(self):
        """Defaults from index.html placeholders, value attributes, and first options."""
        global _PROMPT_DEFAULTS
        if _PROMPT_DEFAULTS is not None:
            return dict(_PROMPT_DEFAULTS)

        defaults = {}
        try:
            with open(os.path.join(UI_PATH, "index.html"), "r", encoding="utf-8") as file:
                html = file.read()
        except Exception:
            _PROMPT_DEFAULTS = {}
            return {}

        try:
            for attrs in re.findall(r"<input\b([^>]*)>", html, flags=re.IGNORECASE):
                field_id = self._html_attr(attrs, "id")
                if not field_id or field_id == "config_list" or field_id.startswith("_"):
                    continue

                input_type = (self._html_attr(attrs, "type") or "text").lower()
                if input_type == "range" or field_id.endswith("_slider"):
                    continue

                if input_type == "checkbox":
                    defaults[field_id] = bool(re.search(r"\bchecked\b", attrs, re.IGNORECASE))
                    continue

                if input_type in ("button", "submit", "file", "image", "hidden"):
                    continue

                value = self._html_attr(attrs, "value")
                placeholder = self._html_attr(attrs, "placeholder")
                if value is not None and value != "":
                    defaults[field_id] = value
                elif placeholder is not None and placeholder != "":
                    defaults[field_id] = placeholder
        except Exception:
            pass

        try:
            select_pattern = re.compile(r"<select\b([^>]*)>(.*?)</select>", re.IGNORECASE | re.DOTALL,)
            option_pattern = re.compile(r"<option\b([^>]*)>", re.IGNORECASE,)
            for attrs, body in select_pattern.findall(html):
                field_id = self._html_attr(attrs, "id")
                if not field_id or field_id == "config_list" or field_id.startswith("_"):
                    continue

                chosen = None
                first = None
                for option_attrs in option_pattern.findall(body):
                    option_value = self._html_attr(option_attrs, "value")
                    if option_value is None:
                        continue

                    if first is None:
                        first = option_value
                    if re.search(r"\bselected\b", option_attrs, re.IGNORECASE):
                        chosen = option_value
                        break

                defaults[field_id] = chosen if chosen is not None else (first or "")
        except Exception:
            pass

        defaults.setdefault("start_key", "f5")
        defaults.setdefault("area_selector_key", "f6")
        defaults.setdefault("stop_key", "f7")
        _PROMPT_DEFAULTS = defaults
        return dict(defaults)

    def _get_saved_default_config(self):
        default_path = SETTINGS_PATH
        try:
            with open(default_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            return data if isinstance(data, dict) else {}

        except Exception:
            return {}

    def _get_config_defaults(self):
        defaults = self._get_saved_default_config()
        defaults.update(self._get_prompt_defaults())
        return defaults

    def _is_blank_setting(self, value):
        if value is None:
            return True

        if isinstance(value, str) and value.strip() == "":
            return True

        return False

    def _fill_blank_settings(self, settings):
        """Fill missing or empty keys from Default config + HTML placeholders.
        A single bad key is skipped so one corrupt value cannot wipe the rest.
        """
        filled = {}
        try:
            defaults = self._get_config_defaults()
        except Exception:
            defaults = {}
        try:
            for key, value in defaults.items():
                try:
                    if key and not str(key).startswith("_") and not str(key).endswith("_slider") and key not in ("config_list", "global_settings"):
                        filled[key] = value
                except Exception:
                    continue

        except Exception:
            pass

        try:
            incoming = settings if isinstance(settings, dict) else {}
            for key, value in incoming.items():
                try:
                    if not key or str(key).startswith("_") or str(key).endswith("_slider") or key in ("config_list", "global_settings"):
                        continue

                    if self._is_blank_setting(value):
                        continue

                    filled[key] = value
                except Exception:
                    continue

        except Exception:
            pass

        return filled

    def _ensure_default_config(self):
        path = SETTINGS_PATH                # already defined at module level = EDITABLE_PATH/settings.json
        os.makedirs(EDITABLE_PATH, exist_ok=True)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as file:
                json.dump({}, file, indent=4)
    # Stop pywebview from walking this object when it is used as js_api
    # (Window.native.AccessibilityObject.Bounds recursion / WebView2 COM).
    _serializable = False
    def close_window(self):
        win = window
        if win is None and webview.windows:
            win = webview.windows[0]
        _schedule_webview_destroy(win)
    def minimize_window(self):
        win = window
        if win is None and webview.windows:
            win = webview.windows[0]
        if win is None:
            return

        try:
            win.minimize()
        except Exception:
            pass

    _HOTKEY_LABELS = {
        "start_key": "Start Key",
        "area_selector_key": "Area Selector Key",
        "stop_key": "Stop Key",
    }
    def rebind_hotkeys(self, hotkey):
        """Arm rebind. on_key_press sees hotkey_state == 1 and ignores start/stop/area."""
        name = str(hotkey or "").strip()
        if name not in self._HOTKEY_LABELS:
            self.hotkey_state = 0
            self.rebind_target = None
            self.set_status("Unknown hotkey")
            return

        self.rebind_target = name
        self.hotkey_state = 1
        self.set_status(f"Rebind {self._HOTKEY_LABELS[name]}: press any key")
    def _finish_hotkey_rebind(self, key):
        target = self.rebind_target
        self.hotkey_state = 0
        self.rebind_target = None
        key = str(key or "").strip().lower()
        if not target or target not in self._HOTKEY_LABELS or not key:
            self.set_status("Hotkey rebind cancelled")
            return

        if not isinstance(self.vars, dict):
            self.vars = {}
        self.vars[target] = key
        try:
            self.save_settings(self.vars)
        except Exception:
            pass

        label = self._HOTKEY_LABELS[target]
        try:
            window.evaluate_js("window.applyHotkey && window.applyHotkey(" + json.dumps(target) + ", " + json.dumps(key) + ")")
        except Exception:
            pass

        self.set_status(f"{label} set to {key.upper()}")

    def save_settings(self, settings=None):
        try:
            if settings is None:
                if window is not None:
                    js_data = window.evaluate_js("typeof collectSettingsData === 'function' ? collectSettingsData() : null")
                    if isinstance(js_data, dict):
                        settings = js_data
                    elif isinstance(js_data, str) and js_data.strip():
                        settings = json.loads(js_data)
                if settings is None:
                    settings = self.vars

            if not isinstance(settings, dict):
                return {"success": False, "error": "Settings must be an object."}

            settings = self._migrate_old_bar_colors(dict(settings))
            settings = self._fill_blank_settings(settings)
            os.makedirs(EDITABLE_PATH, exist_ok=True)
            with open(SETTINGS_PATH, "w", encoding="utf-8") as file:
                json.dump(settings, file, indent=4)
            self.vars = self._settings_for_vars(settings)
            self.current_config = "settings"
            self.save_misc_settings()
            return {"success": True, "path": SETTINGS_PATH}

        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _migrate_old_bar_colors(self, settings):
        """Convert 5.12 left_color/right_color into bar_color + bar_color_2."""
        if not isinstance(settings, dict):
            return settings

        changed = False
        # left_color -> bar_color (first)
        if "left_color" in settings and not settings.get("bar_color"):
            settings["bar_color"] = settings["left_color"]
            changed = True
        if "left_tolerance" in settings and not settings.get("bar_tolerance"):
            settings["bar_tolerance"] = settings["left_tolerance"]
            changed = True
        # right_color -> bar_color_2 (second)
        if "right_color" in settings:
            if not settings.get("bar_color_2"):
                settings["bar_color_2"] = settings["right_color"]
                changed = True
            if "right_tolerance" in settings and not settings.get("bar_tolerance_2"):
                settings["bar_tolerance_2"] = settings["right_tolerance"]
                changed = True
            try:
                count = int(settings.get("bar_color_count") or 1)
            except (TypeError, ValueError):
                count = 1
            if count < 2:
                settings["bar_color_count"] = 2
                changed = True
        # Drop the old keys so they don't linger
        for old_key in ("left_color", "left_tolerance", "right_color", "right_tolerance"):
            if old_key in settings:
                settings.pop(old_key, None)
                changed = True
        return settings

    def load_settings(self):
        settings = {}
        load_error = None
        config_path = SETTINGS_PATH
        exc = 0

        try:
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as file:
                    loaded = json.load(file)
                if not isinstance(loaded, dict):
                    raise ValueError(f"{os.path.basename(config_path)} must contain a JSON object.")
                settings = loaded
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            load_error = str(exc)

        settings.pop("global_settings", None)
        settings = self._migrate_old_bar_colors(settings)
        settings = self._fill_blank_settings(settings)
        self.vars = self._settings_for_vars(settings)
        self.current_config = "settings"
        self._load_misc_settings()

        if load_error is None:
            try:
                os.makedirs(EDITABLE_PATH, exist_ok=True)
                with open(SETTINGS_PATH, "w", encoding="utf-8") as file:
                    json.dump(settings, file, indent=4)
            except OSError as exc:
                load_error = str(exc)

        result = {"success": load_error is None, "settings": self._settings_for_vars(settings)}
        if load_error:
            result["error"] = load_error
        return result

    def _load_misc_settings(self):
        """Load miscellaneous settings from misc.json into self.misc_settings and apply them."""
        current_path = os.path.join(EDITABLE_PATH, "misc.json")
        self.misc_settings = load_misc_settings(current_path)
        data = self.misc_settings  # get data from self.misc_settings
        # Bar Areas
        try:
            loaded_areas = data.get("bar_areas", {})
            for key in AREA_ORDER:
                area = loaded_areas.get(key)
                if isinstance(area, dict):
                    self.bar_areas[key] = {
                        "x": float(area.get("x", 0)),
                        "y": float(area.get("y", 0)),
                        "width": float(area.get("width", 0)),
                        "height": float(area.get("height", 0)),
                    }
        except:
            pass

        # Cached Roblox bounds (indicates areas are stored relative to Roblox)
        try:
            cache = data.get("roblox_bounds_cache")
            if isinstance(cache, dict) and float(cache.get("width", 0) or 0) > 0 and float(cache.get("height", 0) or 0) > 0:
                self.roblox_bounds_cache = {
                    "left": float(cache.get("left", 0)),
                    "top": float(cache.get("top", 0)),
                    "width": float(cache.get("width", 0)),
                    "height": float(cache.get("height", 0)),
                }
            else:
                self.roblox_bounds_cache = None
        except Exception:
            self.roblox_bounds_cache = None
        # Hotkeys
        if "start_key" in self.vars and "area_selector_key" in self.vars and "stop_key" in self.vars:
            # Case 1: Hotkeys Are In self.vars
            pass

        elif "start_key" in data and "area_selector_key" in data and "stop_key" in data:
            # Case 2: Hotkeys Are In Data
            self.vars["start_key"] = data["start_key"]
            self.vars["area_selector_key"] = data["area_selector_key"]
            self.vars["stop_key"] = data["stop_key"]
        else:
            # Case 3: Hotkeys Are Not In self.vars And Data
            self.vars["start_key"] = "F5"
            self.vars["area_selector_key"] = "F6"
            self.vars["stop_key"] = "F7"

    def save_misc_settings(self):
        """Save miscellaneous settings using self.misc_settings."""
        path = os.path.join(EDITABLE_PATH, "misc.json")
        # Use self.misc_settings as the source of truth
        if not isinstance(getattr(self, "misc_settings", None), dict):
            self.misc_settings = {}
        # Clean Areas
        clean_bar_areas = {}
        for key in AREA_ORDER:
            area = self.bar_areas.get(key)
            if isinstance(area, dict):
                clean_bar_areas[key] = {
                    "x": float(area.get("x", 0)),
                    "y": float(area.get("y", 0)),
                    "width": float(area.get("width", 0)),
                    "height": float(area.get("height", 0)),
                }
            else:
                clean_bar_areas[key] = None
        # Update self.misc_settings with current values
        self.misc_settings["bar_areas"] = clean_bar_areas
        # Cached Roblox window bounds used when areas were saved (relative origin)
        cache = getattr(self, "roblox_bounds_cache", None)
        if isinstance(cache, dict):
            self.misc_settings["roblox_bounds_cache"] = {
                "left": float(cache.get("left", 0)),
                "top": float(cache.get("top", 0)),
                "width": float(cache.get("width", 0)),
                "height": float(cache.get("height", 0)),
            }
        else:
            self.misc_settings.pop("roblox_bounds_cache", None)
        # Hotkeys
        self.misc_settings["start_key"] = self.vars.get("start_key", "F5")
        self.misc_settings["area_selector_key"] = self.vars.get("area_selector_key", "F6")
        self.misc_settings["stop_key"] = self.vars.get("stop_key", "F7")
        # Terms of Service
        self.misc_settings["tos_accepted"] = bool(getattr(self, "tos_accepted", self.misc_settings.get("tos_accepted", False)))
        with open(path, "w") as f:
            json.dump(self.misc_settings, f, indent=4)
    def _settings_for_vars(self, settings):
        """Copy config values into self.vars. Skip UI-only and private keys."""
        cleaned = {}
        if not isinstance(settings, dict):
            return cleaned

        for key, value in settings.items():
            try:
                if not key or str(key).startswith("_") or str(key).endswith("_slider") or key in ("config_list", "global_settings"):
                    continue

                cleaned[key] = value
            except Exception:
                continue

        return cleaned

    def get_python_version_info(self):
        """Return the Python backend's app version, beta version, developer."""
        return {

            "app_version": APP_VERSION,
            "beta_version": BETA_VERSION,
            "developer": DEVELOPER
        }
    def set_status(self, message):
        """Push a status message to the main webview window's JS."""
        if IS_COMPILED == False:
            # print("Debug: ", message)
            pass

        try:
            safe = message.replace("\\", "\\\\").replace("`", "\\`").replace("'", "\\'")
            window.evaluate_js("window.setStatus && window.setStatus('" + safe + "')")
        except Exception:
            pass

    def message_box_javascript(self, message, dialogue_type="ok"):
        """Show a custom bottom banner instead of browser alert/confirm.
        dialogue_type:
          - "ok" (default): single OK button, returns None after dismiss
          - "askyesno": Yes / No buttons, returns True / False
        """
        try:
            # Escape for embedding in a single-quoted JS string
            safe = ((message or "") .replace("\\", "\\\\") .replace("'", "\\'") .replace("`", "\\`") .replace("\r", "") .replace("\n", "\\n"))
            self._message_box_event = threading.Event()
            self._message_box_result = None
            js = f"showMessageBoxBanner('{safe}', '{dialogue_type}');"
            window.evaluate_js(js)
            # Block until the banner is answered (or timeout)
            if self._message_box_event.wait(timeout=300):
                result = self._message_box_result
                self._message_box_event = None
                return result

            else:
                self._message_box_event = None
                return False if dialogue_type == "askyesno" else None

        except Exception:
            return False if dialogue_type == "askyesno" else None

    def message_box_result(self, result):
        """Callback from the JS banner. Unblocks message_box_javascript."""
        self._message_box_result = result
        if self._message_box_event is not None:
            self._message_box_event.set()
        return True

    def copy_to_clipboard(self, text):
        """Copy text to the system clipboard. Returns True on success."""
        if text is None:
            return False

        text = str(text)
        try:
            if sys.platform == "darwin":
                pasteboard = AppKit.NSPasteboard.generalPasteboard()
                pasteboard.clearContents()
                # NSPasteboardTypeString Is Preferred; Fall Back To Legacy Type Name
                paste_type = getattr(AppKit, "NSPasteboardTypeString", None) or AppKit.NSStringPboardType
                return bool(pasteboard.setString_forType_(text, paste_type))

            elif sys.platform == "win32":
                # Prefer Powershell Setclipboard For Reliable Unicode Support
                try:
                    completed = subprocess.run([ "powershell", "-NoProfile", "-Command", "Set-Clipboard -Value ([Console]::In.ReadToEnd())", ], input=text, text=True, capture_output=True, timeout=5,)
                    if completed.returncode == 0:
                        return True

                except Exception:
                    pass

                # Fallback: Clip.Exe With Utf16Le
                try:
                    completed = subprocess.run(["clip"], input=text.encode("utf-16le"), capture_output=True, timeout=5,)
                    return completed.returncode == 0

                except Exception:
                    return False

            else:
                # Linux: Try Xclip, Then Xsel
                payload = text.encode("utf-8")
                for cmd in (["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"],):
                    try:
                        completed = subprocess.run(cmd, input=payload, capture_output=True, timeout=5,)
                        if completed.returncode == 0:
                            return True

                    except FileNotFoundError:
                        continue

                    except Exception:
                        continue

                return False

        except Exception:
            return False

    def get_error_line(self, lines):
        matches = re.findall(r'\bline\s+(\d+)\b', lines)
        if not matches:
            return None

        return int(matches[-1])

    # Area Selector
    def open_area_selector(self):
        # Detect Roblox window (falls back to full-screen coordinates) and store for the overlay
        self.roblox_bounds = self.detect_roblox()
        # Build Current Areas From Bar_Areas Or Area_Config Defaults (All Keys, Including Appraisal)
        # If a Roblox cache exists, stored areas are relative and must be mapped onto the
        # current Roblox window (or full screen if not found) before rendering.
        self.status_overlay.hide()
        areas = {}
        use_relative = isinstance(getattr(self, "roblox_bounds_cache", None), dict)
        for name in AREA_ORDER:
            a = self.bar_areas.get(name)
            # Valid stored area: map if relative cache exists, else treat as absolute (legacy)
            if (isinstance(a, dict) and float(a.get("width", 0) or 0) > 0
                    and float(a.get("height", 0) or 0) > 0):
                if use_relative:
                    areas[name] = self._map_relative_area_to_screen(a)
                else:
                    areas[name] = dict(a)
            else:
                # Unset area: treat AREA_CONFIG default as relative to the current
                # Roblox window (falls back to full-screen when Roblox is not found).
                # This ensures defaults track the Roblox window instead of the full screen.
                default = dict(AREA_CONFIG[name]["default"])
                areas[name] = self._map_relative_area_to_screen(default)
        if hasattr(self, "area_selector") and self.area_selector and self.area_selector.is_open():
            self.area_selector.request_save_and_close()
        else:
            self.save_settings()
            self.area_selector.show()
            self.area_selector.update(areas, self.vars)
    # Debug Screenshots
    def take_debug_screenshot(self):
        """
        Capture every area in AREA_ORDER plus a full-screen shot, and save
        debug images as debug_<name>.png / debug_full.png.
        """
        full_img = self.capture_single_frame()
        if full_img is None:
            self.set_status("Full screen is empty")
            return

        try:
            cv2.imwrite(os.path.join(EDITABLE_PATH, "debug_full.png"), full_img)
        except Exception as e:
            self.set_status(f"Error saving full screenshot: {e}")
            return

        saved = ["full"]
        try:
            for name in AREA_ORDER:
                left, top, right, bottom, _, _ = self.get_areas(name)
                # Clamp To Image Bounds
                h, w = full_img.shape[:2]
                top = max(0, min(top, h - 1))
                bottom = max(top + 1, min(bottom, h))
                left = max(0, min(left, w - 1))
                right = max(left + 1, min(right, w))
                crop = full_img[top:bottom, left:right]
                if crop.size == 0:
                    continue

                cv2.imwrite(os.path.join(EDITABLE_PATH, f"debug_{name}.png"), crop)
                saved.append(name)
        except Exception as e:
            self.set_status(f"Error saving region screenshots: {e}")
            return

        self.set_status(f"Saved debug screenshots ({', '.join(saved)})")
    def _enumerate_windows(self):
        """Cross-platform window list (similar to SolarAutomateV3.refresh_windows).
        Returns a list of dicts with keys: title, exe, left, top, width, height.
        """
        windows = []
        if sys.platform == "win32":
            if gw is None:
                return windows

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            for window in gw.getAllWindows():
                title = window.title or ""
                hwnd = getattr(window, "_hWnd", None) or getattr(window, "_hwnd", None)
                exe = ""
                if hwnd:
                    try:
                        pid = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
                        if handle:
                            try:
                                size = wintypes.DWORD(260)
                                buf = ctypes.create_unicode_buffer(size.value)
                                if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                                    exe = os.path.basename(buf.value) or ""
                            finally:
                                kernel32.CloseHandle(handle)
                    except Exception:
                        exe = ""
                windows.append({ "title": title, "exe": exe, "left": int(getattr(window, "left", 0) or 0), "top": int(getattr(window, "top", 0) or 0), "width": int(getattr(window, "width", 0) or 0), "height": int(getattr(window, "height", 0) or 0), })
        elif sys.platform == "darwin":
            window_list = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListExcludeDesktopElements | Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID,)
            for window in window_list or []:
                owner = window.get(Quartz.kCGWindowOwnerName, "") or ""
                title = window.get(Quartz.kCGWindowName, "") or ""
                bounds = window.get(Quartz.kCGWindowBounds, {}) or {}
                windows.append({ "title": title, "exe": owner, "left": int(bounds.get("X", 0) or 0), "top": int(bounds.get("Y", 0) or 0), "width": int(bounds.get("Width", 0) or 0), "height": int(bounds.get("Height", 0) or 0), })
        elif sys.platform.startswith("linux"):
            try:
                disp = _get_xdisplay()
                root = disp.screen().root
                NET_CLIENT_LIST = disp.intern_atom("_NET_CLIENT_LIST")
                NET_WM_NAME = disp.intern_atom("_NET_WM_NAME")
                NET_WM_PID = disp.intern_atom("_NET_WM_PID")
                UTF8_STRING = disp.intern_atom("UTF8_STRING")
                prop = root.get_full_property(NET_CLIENT_LIST, X.AnyPropertyType)
                if prop:
                    for win_id in prop.value:
                        try:
                            window = disp.create_resource_object("window", win_id)
                        except Exception:
                            continue

                        title = ""
                        try:
                            net_name = window.get_full_property(NET_WM_NAME, UTF8_STRING)
                            if net_name and net_name.value:
                                raw = net_name.value
                                title = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
                        except Exception:
                            pass

                        if not title:
                            try:
                                wm_name = window.get_wm_name()
                                if wm_name:
                                    title = wm_name if isinstance(wm_name, str) else str(wm_name)
                            except Exception:
                                pass

                        exe = ""
                        try:
                            pid_prop = window.get_full_property(NET_WM_PID, X.AnyPropertyType)
                            if pid_prop and pid_prop.value:
                                comm_path = f"/proc/{int(pid_prop.value[0])}/comm"
                                with open(comm_path, "r", encoding="utf-8") as comm:
                                    exe = comm.read().strip()
                        except Exception:
                            pass

                        left = top = width = height = 0
                        try:
                            geom = window.get_geometry()
                            width, height = geom.width, geom.height
                            try:
                                abs_coords = root.translate_coords(window, 0, 0)
                                left, top = abs_coords.x, abs_coords.y
                            except Exception:
                                left, top = geom.x, geom.y
                        except Exception:
                            pass

                        windows.append({ "title": title or "", "exe": exe, "left": int(left or 0), "top": int(top or 0), "width": int(width or 0), "height": int(height or 0), })
            except Exception:
                pass

        return windows

    def get_window_info(self, window_name):
        """Return (left, top, width, height) of the first matching window.
        Matches on title or process/owner name containing window_name (case-insensitive).
        Prefers larger windows when several match. Falls back to full screen if none found.
        Cross-platform (Windows / macOS / Linux), adapted from SolarAutomateV3 window finding.
        """
        name = (window_name or "").strip().lower()
        candidates = []
        try:
            for info in self._enumerate_windows():
                title = (info.get("title") or "").lower()
                exe = (info.get("exe") or "").lower()
                if name and (name in title or name in exe):
                    # Skip tiny / empty windows
                    if info.get("width", 0) < 50 or info.get("height", 0) < 50:
                        continue

                    candidates.append(info)
        except Exception:
            candidates = []
        if candidates:
            # Prefer windows whose title contains the name, then largest area
            def score(info):
                title = (info.get("title") or "").lower()
                area = (info.get("width") or 0) * (info.get("height") or 0)
                title_hit = 1 if name in title else 0
                return (title_hit, area)

            best = max(candidates, key=score)
            return best["left"], best["top"], best["width"], best["height"]

        # Fallback
        try:
            import pyautogui
            sw, sh = pyautogui.size()
        except Exception:
            sw, sh = getattr(self, "SCREEN_WIDTH", 1920), getattr(self, "SCREEN_HEIGHT", 1080)
        return 0, 0, abs(int(sw)), abs(int(sh))

    def detect_roblox(self):
        """Called from the Detect Roblox button. Prints and reports window bounds."""
        left, top, width, height = self.get_window_info("Roblox")
        return {"left": left, "top": top, "width": width, "height": height}

    # Point Select
    def select_ratio(self, field_id=None):
        """Open the point selector overlay.
        field_id (optional): settings field name to write the result into
        (e.g. 'mirror_ratio'). The main UI is also notified via
        onPointPicked and by updating the matching input element.
        """
        if not hasattr(self, "point_select") or self.point_select is None:
            self.point_select = PointSelect(self)
        # Toggle off if already open
        if self.point_select.is_open():
            self.point_select.hide()
            return None

        self.point_select.show(field_id=field_id)
        return None

    def start_eyedropper(self, color_key=None):
        """Open the color picker overlay.
        color_key (optional): settings field name to write the result into
        (e.g. 'fish_color', 'shake_color'). The main UI is also notified via
        onColorPicked / setPickedColor and by updating matching input elements.
        """
        if not hasattr(self, "eyedropper") or self.eyedropper is None:
            self.eyedropper = Eyedropper(self)
        # Toggle Off If Already Open
        if self.eyedropper.is_open():
            self.eyedropper.hide()
            return None

        self.eyedropper.show(color_key=color_key)
        return None

    def get_last_picked_color(self):
        """Return (and clear) the most recently picked eyedropper color.
        The main UI can poll this after start_eyedropper if it does not
        implement onColorPicked / setPickedColor callbacks."""
        if not hasattr(self, "eyedropper") or self.eyedropper is None:
            return None

        color = self.eyedropper.last_picked_color
        self.eyedropper.last_picked_color = None
        return color

    # Hotkeys
    def _get_hotkeys(self):
        try:
            start_key = self.normalize_key(str(self.vars["start_key"]))
            areas_key = self.normalize_key(str(self.vars["area_selector_key"]))
            stop_key = self.normalize_key(str(self.vars["stop_key"]))
        except Exception as e:
            self.set_status(f"Get hotkeys failed: {e}")
            start_key = "f5"
            areas_key = "f6"
            stop_key = "f7"
        return start_key, areas_key, stop_key

    def normalize_key(self, key):
        try:
            return key.char.lower()  # Letter Keys

        except AttributeError:
            return str(key).replace("Key.", "").replace(" ", "").lower()

    def on_key_press(self, key):
        key = self.normalize_key(key)
        # Rebind capture: hotkeys stay disabled until the next key is stored.
        if self.hotkey_state == 1:
            self._finish_hotkey_rebind(key)
            return

        self.save_settings()
        start_key, area_selector_key, stop_key = self._get_hotkeys()
        if key == start_key:
            window.hide()
            if self.macro_running == True:
                return

            else:
                # Set Flag Before Starting Threads To Avoid Race Where
                # The Capture Thread Starts, Sees Macro_Runningfalse, And Exits Immediately.
                self.macro_running = True
                # Detect Roblox window (falls back to full-screen coordinates)
                self.roblox_bounds = self.detect_roblox()
                # Save Current Settings To Config Before Starting
                self.save_settings(self.vars)
                # Start the camera thread first
                if dxcam is not None:
                    self.camera = dxcam.create(output_color="BGR")
                    self.camera.start(target_fps=60)
                else:
                    if sys.platform == "darwin":
                        if _SCK_AVAILABLE:
                            target = self.capture_loop_screencapturekit
                        else:
                            target = self.capture_loop_quartz
                    else:
                        target = self.capture_loop_mss
                    self.capture_thread = threading.Thread(target=target, daemon=True)
                    self.capture_thread.start()
                # Now start the fishing thread
                self.macro_thread = threading.Thread(target=self.start_macro, daemon=True)
                self.macro_thread.start()
        elif key == area_selector_key:
            # Guard To Prevent Area Selector From Being Opened The Second The Macro Started
            if self.macro_running == True:
                return

            self.open_area_selector()
        elif key == stop_key:
            window.show()
            self.stop_macro()
    def _string_to_key(self, key_string):
        key_string = key_string.strip().lower()
        # Try Special Keys
        if hasattr(Key, key_string):
            return getattr(Key, key_string)

        # Fallback To Character
        return key_string

    # Keyboard/Mouse Functions (Platformspecific)
    # Hold Mouse
    def hold_mouse(self, mouse=False):
        "Hold mouse. True for right click, False for left click."
        if self.macro_running == False:
            return

        if sys.platform == "win32":
            if mouse:
                windll.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
            else:
                windll.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        elif sys.platform == "darwin":
            _mouse_event(button="right" if mouse else "left", press=True)
        else:
            # Linux  Now Uses The Unified X11 Implementation
            _mouse_event(button="right" if mouse else "left", press=True)
    # Release Mouse
    def release_mouse(self, mouse=False):
        "Release mouse. True for right click, False for left click."
        if self.macro_running == False:
            return

        if sys.platform == "win32":
            if mouse:
                windll.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            else:
                windll.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        elif sys.platform == "darwin":
            _mouse_event(button="right" if mouse else "left", press=False)
        else:
            # Linux - Now Uses The Unified X11 Implementation
            _mouse_event(button="right" if mouse else "left", press=False)
    # Click At
    def _click_at(self, x, y, click_count=1):
        if self.macro_running == False:
            return

        if x is None or y is None:
            return

        # Convert Coordinates If Needed (Retina Scaling)
        if sys.platform == "darwin":
            scale = get_scale_factor()
            x = int(x / scale)
            y = int(y / scale)
        # Seperate Branches For Windows And macOS Mouse Events
        if sys.platform == "win32":
            windll.SetCursorPos(x, y)
            windll.mouse_event(MOUSEEVENTF_MOVE, 0, 1, 0, 0)
            for i in range(click_count):
                windll.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                windll.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                if i < click_count - 1:
                    time.sleep(0.03)
        else:
            try:
                _warp_mouse(x, y)
                _warp_mouse(x + 5, y + 5)
                _warp_mouse(x, y)
            except:
                _move_mouse(x, y)
                _move_mouse(x + 5, y + 5)
                _move_mouse(x, y)
            for i in range(click_count):
                _mouse_event(button="left", press=True)
                _mouse_event(button="left", press=False)
                if i < click_count - 1:
                    time.sleep(0.03)
    # Keyboard
    def _send_key(self, key2, delay=0.05, click_type=0):
        """
        Send a keyboard event.
        delay: Delay between send and release
        click_type:
            0 = click (press + release)   [default]
            1 = hold (press only)
            2 = release (release only)
        """
        if self.macro_running == False:
            return

        key = str(key2)
        if sys.platform == "darwin":
            send_key(key2, delay=delay, click_type=click_type)
        else:
            # Convert Special Key Names
            special_keys = {
                "enter": Key.enter,
                "return": Key.enter,
                "tab": Key.tab,
                "space": Key.space,
                "esc": Key.esc,
                "escape": Key.esc,
                "backspace": Key.backspace,
                "delete": Key.delete,
                "up": Key.up,
                "down": Key.down,
                "left": Key.left,
                "right": Key.right,
            }
            key = special_keys.get(key.lower(), key)
            try:
                if click_type == 0:
                    keyboard_controller.press(key)
                    time.sleep(delay)
                    keyboard_controller.release(key)
                elif click_type == 1:
                    keyboard_controller.press(key)
                elif click_type == 2:
                    keyboard_controller.release(key)
            except Exception as e:
                print("Error sending keys:", e)

    # Interruptible Sleep
    def interruptible_sleep(self, duration):
        duration = max(0.01, duration)
        end_time = time.perf_counter() + duration
        while True:
            if not self.macro_running:
                break  # Interrupted

            remaining = end_time - time.perf_counter()
            if remaining <= 0:
                break

            # Sleep For At Most 10Ms Or Whatever Fraction Of Remaining Time Is Left
            time.sleep(min(0.01, remaining))
    # Get Values
    def _map_relative_area_to_screen(self, area):
        """Convert one Roblox-relative area (0–1 within the Roblox window) into
        absolute screen ratios (0–1 of SCREEN_WIDTH/HEIGHT).
        Uses the currently detected Roblox window; falls back to full-screen
        coordinates when Roblox is not found.
        """
        if not isinstance(area, dict):
            return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}

        # Ensure we have current Roblox bounds (detect if missing)
        roblox = getattr(self, "roblox_bounds", None)
        if not isinstance(roblox, dict) or float(roblox.get("width", 0) or 0) < 10:
            try:
                roblox = self.detect_roblox()
                self.roblox_bounds = roblox
            except Exception:
                roblox = {"left": 0, "top": 0, "width": SCREEN_WIDTH, "height": SCREEN_HEIGHT}
        r_left = float(roblox.get("left", 0) or 0)
        r_top = float(roblox.get("top", 0) or 0)
        r_w = float(roblox.get("width", 0) or 0)
        r_h = float(roblox.get("height", 0) or 0)
        if r_w < 10 or r_h < 10:
            # Fallback to full screen
            r_left, r_top, r_w, r_h = 0.0, 0.0, float(SCREEN_WIDTH), float(SCREEN_HEIGHT)
        rel_x = float(area.get("x", 0))
        rel_y = float(area.get("y", 0))
        rel_w = float(area.get("width", area.get("w", 0)))
        rel_h = float(area.get("height", area.get("h", 0)))
        abs_x = r_left + rel_x * r_w
        abs_y = r_top + rel_y * r_h
        abs_w = rel_w * r_w
        abs_h = rel_h * r_h
        return {

            "x": abs_x / float(SCREEN_WIDTH) if SCREEN_WIDTH else 0.0,
            "y": abs_y / float(SCREEN_HEIGHT) if SCREEN_HEIGHT else 0.0,
            "width": abs_w / float(SCREEN_WIDTH) if SCREEN_WIDTH else 0.0,
            "height": abs_h / float(SCREEN_HEIGHT) if SCREEN_HEIGHT else 0.0,
        }
    def get_areas(self, area_key):
        """Apply scale factor.  Area values are ratios 0-1.
        If a Roblox bounds cache exists, stored areas are relative to the Roblox
        window and are mapped onto the current Roblox bounds (or full screen if Roblox is not found).  Otherwise they are treated as absolute screen ratios
        (legacy).  Returns physical pixels.
        """
        scale = get_scale_factor()
        area_data = self.bar_areas.get(area_key)
        use_relative = isinstance(getattr(self, "roblox_bounds_cache", None), dict)
        if (isinstance(area_data, dict) and float(area_data.get("width", 0) or 0) > 0
                and float(area_data.get("height", 0) or 0) > 0):
            if use_relative:
                mapped = self._map_relative_area_to_screen(area_data)
                left   = float(mapped["x"])
                top    = float(mapped["y"])
                width  = float(mapped["width"])
                height = float(mapped["height"])
            else:
                left   = float(area_data["x"])
                top    = float(area_data["y"])
                width  = float(area_data["width"])
                height = float(area_data["height"])
            right  = left + width
            bottom = top + height
        else:
            # Unset area: map the AREA_CONFIG default relative to the current Roblox
            # window so defaults follow Roblox instead of staying full-screen.
            default = AREA_CONFIG.get(area_key, {}).get("default") or {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
            mapped = self._map_relative_area_to_screen(default)
            left   = float(mapped["x"])
            top    = float(mapped["y"])
            width  = float(mapped["width"])
            height = float(mapped["height"])
            right  = left + width
            bottom = top + height
        left2   = int(left * scale * self.SCREEN_WIDTH)
        top2    = int(top * scale * self.SCREEN_HEIGHT)
        right2  = int(right * scale * self.SCREEN_WIDTH)
        bottom2 = int(bottom * scale * self.SCREEN_HEIGHT)
        width2  = int(width * scale * self.SCREEN_WIDTH)
        height2 = int(height * scale * self.SCREEN_HEIGHT)
        return left2, top2, right2, bottom2, width2, height2

    def _get_default_areas(self, area):
        """Return (left, top, right, bottom) as ratios 0-1 from AREA_CONFIG defaults.
        Must stay in ratio space so get_areas can apply scale * SCREEN_* once."""
        cfg = AREA_CONFIG.get(area)
        if cfg:
            d = cfg["default"]
            left   = float(d["x"])
            top    = float(d["y"])
            right  = left + float(d["width"])
            bottom = top + float(d["height"])
        else:
            left, top, right, bottom = 0.0, 0.0, 1.0, 1.0
        return left, top, right, bottom

    def _get_var_number(self, key, default, cast=float):
        """Returns a key from the GUI with Exception handling"""
        try:
            value = self.vars.get(key)
            if value is None:
                # Compatibility Mapping For 1600Plus Key Differences
                if key == "perfect_cast_timing_1600_plus":
                    value = self.vars.get("perfect_cast_timing_1600plus")
                if value is None:
                    return default

            if isinstance(value, str):
                value = value.strip()
                if value == "":
                    return default

            return cast(value)

        except Exception:
            return default

    def _split_ratio(self, item, screen_coords=False):
        # Split
        splitted_items = item.replace(" ", "").split(",")
        try:
            x = float(splitted_items[0])
            y = float(splitted_items[1])
        except:
            x = 0.5
            y = 0.5

        if not screen_coords:
            return x, y

        # Get Roblox window bounds
        window = getattr(self, "roblox_window_bounds", None) or getattr(self, "roblox_bounds", None)

        if window is None:
            window = self.detect_roblox()

        # Convert relative coordinates to screen coordinates
        x_screen = int(window["left"] + x * window["width"])
        y_screen = int(window["top"] + y * window["height"])

        return x_screen, y_screen

    # Detection
    def _hex_to_bgr(self, hex_color):
        "Convert hex color to BGR tuple for OpenCV."
        if hex_color is None or hex_color.lower() in ["none", "# None", ""]:
            return None

        hex_color = hex_color.lstrip('# ').strip()
        if len(hex_color) == 3:
            hex_color = "".join(c * 2 for c in hex_color)
        if len(hex_color) == 6:
            try:
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
                return (b, g, r)  # Bgr Format For Opencv

            except ValueError:
                return None

        return None

    def _normalize_capture_size(self, frame):
        """Ensure the captured frame matches the physical pixel size expected by
        get_areas (SCREEN_* * scale). On macOS Retina, Quartz (kCGWindowImageDefault)
        and some ScreenCaptureKit configurations deliver the logical (point) size
        while area coordinates are scaled to physical pixels. Upscale when needed
        so crops line up. No-op when sizes already match.
        """
        if frame is None or not hasattr(frame, "shape") or len(frame.shape) < 2:
            return frame

        try:
            scale = get_scale_factor() or 1.0
            if scale <= 0:
                scale = 1.0
            expected_w = int(round(SCREEN_WIDTH * scale))
            expected_h = int(round(SCREEN_HEIGHT * scale))
            h, w = frame.shape[:2]
            if w == expected_w and h == expected_h:
                return frame

            # Only upscale/downscale when the ratio is close to an integer scale
            # (avoids accidental resizing of already-correct frames from other backends).
            if expected_w > 0 and expected_h > 0 and w > 0 and h > 0:
                return cv2.resize(frame, (expected_w, expected_h), interpolation=cv2.INTER_LINEAR)

        except Exception:
            pass

        return frame

    def capture_single_frame(self):
        """
        Capture a single full-screen frame without touching self.macro_running.
        Used by debug screenshots, eyedropper freeze, and Discord screenshot logging.
        """
        if sys.platform == "darwin":
            image = Quartz.CGWindowListCreateImage(Quartz.CGRectInfinite, Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID, Quartz.kCGWindowImageBestResolution)
            if image is None:
                return None

            return self._normalize_capture_size(cgimage_to_srgb_numpy(image))

        else:
            scale = get_scale_factor()
            with MSS() as sct:
                monitor = {
                    "top": 0,
                    "left": 0,
                    "width": int(SCREEN_WIDTH * scale),
                    "height": int(SCREEN_HEIGHT * scale),
                }
                return np.asarray(sct.grab(monitor))[:, :, :3]

    def capture_loop_mss(self):
        """Continuous capture loop for the macro (Windows fallback). Assumes self.macro_running is already True."""
        if not self.macro_running:
            return

        self.capture_id = 0
        scale = get_scale_factor()
        with MSS() as sct:
            monitor = {
                "top": 0,
                "left": 0,
                "width": int(SCREEN_WIDTH * scale),
                "height": int(SCREEN_HEIGHT * scale),
            }
            while self.macro_running:
                self.capture_frame = self._normalize_capture_size(np.asarray(sct.grab(monitor))[:, :, :3])
                self.capture_id += 1
                time.sleep(self.scan_delay)
    def capture_loop_quartz(self):
        """Continuous capture loop for the macro (macOS fallback). Assumes self.macro_running is already True."""
        if not self.macro_running:
            return

        self.capture_id = 0
        while self.macro_running:
            if sys.platform == "darwin":
                image = Quartz.CGWindowListCreateImage(Quartz.CGRectInfinite, Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID, Quartz.kCGWindowImageBestResolution)
            else:
                image = None
            if image is None:
                time.sleep(0.01)
                continue

            frame = cgimage_to_srgb_numpy(image)
            if frame is None:
                time.sleep(0.01)
                continue

            self.capture_frame = self._normalize_capture_size(frame)
            self.capture_id += 1
            time.sleep(self.scan_delay)
    def capture_loop_screencapturekit(self):
        """Continuous capture via _RegionCapture (ScreenCaptureKit + MSS fallback).
        Publishes self.capture_frame / self.capture_id for the macro to read.
        """
        if sys.platform != "darwin":
            raise RuntimeError("ScreenCaptureKit is not supported on Windows")
        if not _SCK_AVAILABLE:
            return self.capture_loop_quartz()
        if not self.macro_running:
            return

        scale = get_scale_factor() or 1.0
        region = {"left": 0, "top": 0,
                "width": int(SCREEN_WIDTH), "height": int(SCREEN_HEIGHT)}

        capture = _RegionCapture(fps=60, log=lambda m: None, pixel_scale=scale)
        self._region_capture = capture
        try:
            try:
                frame, _ = capture.grab(region, wait=True)
                self.capture_frame = self._normalize_capture_size(frame)
                self.capture_id += 1
            except Exception as exc:
                self.set_status(f"ScreenCaptureKit unavailable ({exc}); using Quartz")
                return self.capture_loop_quartz()

            while self.macro_running:
                try:
                    frame, _ = capture.grab(region, wait=True)
                    self.capture_frame = self._normalize_capture_size(frame)
                    self.capture_id += 1
                except NoNewFrame:
                    continue
                except Exception as exc:
                    self.set_status(f"ScreenCaptureKit failed ({exc}); using Quartz")
                    return self.capture_loop_quartz()
        finally:
            try:
                capture.__exit__(None, None, None)
            except Exception:
                pass
            self._region_capture = None

    def process_image_for_ocr(self, img):
        # Convert To Grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Upscale
        gray = cv2.resize(gray,None,fx=3,fy=3,interpolation=cv2.INTER_CUBIC)
        # Adaptive Threshold Works Better With Different Text Colors
        binary = cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY,31,8)
        return binary

    def extract_number_from_text(self, text):
        """
        Extracts numeric value from OCR text, handling common issues.
        Returns None if no valid number is found.
        """
        # Clean Up Common OCR Artifacts
        cleaned = text.strip()
        # Replace Common OCR Mistakes (O > 0, L > 1, Etc.)
        cleaned = cleaned.replace('O', '0').replace('o', '0')
        cleaned = cleaned.replace('l', '1').replace('I', '1')
        # Find Number With Optional Decimal
        # This Pattern Handles: 0.5, .5, 100, 100.0, Etc.
        match = re.search(r'(\d+\.?\d*|\.\d+)', cleaned)
        if match:
            try:
                return float(match.group(1))

            except ValueError:
                return None

        return None

    def pixel_search(self, frame, hex, tolerance, scan_mode=0):
        """
        Searches for the first or last pixel based on mode.
        Scan mode 0: First pixel; Mode 1: Last pixel
        Uses the same per-channel tolerance box as _detect_fish_colors_in_frame:
        each BGR channel must be within [color - tolerance, color + tolerance].
        """
        if frame is None or frame.size == 0:
            return None, None

        if scan_mode not in (0, 1):
            raise RuntimeError("Invalid scan mode")

        # Convert tolerance to int, handling string inputs
        try:
            tolerance = int(tolerance)
        except (ValueError, TypeError):
            tolerance = 0
        # Failsafe: None Hex
        if hex is None:
            return None, None

        try:
            tolerance = int(np.clip(tolerance, 0, 255))
            b, g, r = self._hex_to_bgr(hex)
            # Same per-channel bounds as _detect_fish_colors_in_frame
            lower_bound = np.array([ max(0, b - tolerance), max(0, g - tolerance), max(0, r - tolerance) ], dtype=np.uint8)
            upper_bound = np.array([ min(255, b + tolerance), min(255, g + tolerance), min(255, r + tolerance) ], dtype=np.uint8)
            # cv2.inRange gives the same mask as the detection function
            mask = cv2.inRange(frame, lower_bound, upper_bound)
            coords = np.argwhere(mask > 0)
            if coords.size > 0:
                if scan_mode == 0:
                    y, x = coords[0]
                else:
                    y, x = coords[-1]
                return int(x), int(y)

        except:
            return None, None

        return None, None

    def pixel_search_matrix(self, frame, color_id, tolerance_id, scan_mode=0, optimize_mode=0):
        searched = set()
        loop_count = 1
        if optimize_mode not in (0, 1, 2):
            raise RuntimeError("Invalid optimize mode")

        while True:
            try:
                color_id2 = self.vars[f"{color_id}_{loop_count}"]
                tolerance_id2 = self.vars[f"{tolerance_id}_{loop_count}"]
            except KeyError:
                # No more numbered entries -> try the base color once
                color_id2 = self.vars.get(color_id)
                tolerance_id2 = self.vars.get(tolerance_id)
            # Scan optimize mode
            loop_divisible_by_2 = loop_count % 2
            if optimize_mode == 1 and loop_divisible_by_2 == 0:
                loop_count += 1
                continue

            if optimize_mode == 2 and loop_divisible_by_2 == 1:
                loop_count += 1
                continue

            if color_id2 is None:
                return None, None

            if color_id2 in searched:
                return None, None

            searched.add(color_id2)
            x, y = self.pixel_search(frame, color_id2, tolerance_id2, scan_mode)
            if x is not None and y is not None:
                return x, y

            loop_count += 1

    def find_color_cluster(self, frame, target_color_hex, tolerance=8, min_area=10):
        """
        Find the largest color cluster and return its center.
        Args:
            frame: BGR image
            target_color_hex: hex color string
            tolerance: color tolerance
            min_area: minimum cluster size to be valid
        Returns:
            (center_x, center_y) or None
        """
        # Required_Fish_Pixels
        if frame is None:
            return None, None

        # Color Mask (Vectorized Like Your Fast Version)
        target_bgr = np.array(self._hex_to_bgr(target_color_hex), dtype=np.int16)
        frame_int = frame.astype(np.int16)
        tol = int(np.clip(tolerance, 0, 255))
        mask = np.all(np.abs(frame_int - target_bgr) <= tol, axis=2).astype(np.uint8)
        if not np.any(mask):
            return None, None

        # Connected Components (Cluster Detection)
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
        if num_labels <= 1:
            return None, None  # Only Background

        # Skip Label 0 (Background)
        largest_label = None
        largest_area = 0
        for label in range(1, num_labels):
            area = stats[label, cv2.CC_STAT_AREA]
            if area > largest_area and area >= min_area:
                largest_area = area
                largest_label = label
        if largest_label is None:
            return None, None

        # Centroid
        center_x, center_y = centroids[largest_label]
        return int(center_x), int(center_y)

    # Utility Functions
    def test_logging(self):
        logging_mode = self.vars["logging_mode"].capitalize()
        self.send_logging(f"**{logging_mode} is working**", "Macro Stopped")
    def send_logging(self, text, loop_count):
        logging_mode = self.vars["logging_mode"].lower()
        if logging_mode == "disabled":
            self.set_status("⚠ Logging is disabled.")
            return

        webhook_url = None
        if logging_mode != "file":
            webhook_url = self.vars["logging_url"].strip()
            if not webhook_url.startswith("https://discord.com/api/webhooks/"):
                self.set_status("Error: Invalid webhook URL.")
                return

        self.set_status("Sending log...")
        if logging_mode == "screenshot":
            thread = threading.Thread(target=self._discord_screenshot_worker, args=(webhook_url, f"{text}\n", loop_count), daemon=True)
        elif logging_mode == "file":
            thread = threading.Thread(target=self._debug_log_worker, args=(text, loop_count), daemon=True)
        else:
            thread = threading.Thread(target=self._discord_text_worker, args=(webhook_url, f"{text}\n", loop_count), daemon=True)
        thread.start()
        thread.join()  # Wait for Discord/file log to finish before continuing
    def _format_duration(self, seconds):
        if seconds is None or seconds < 0:
            return "N/A"

        seconds = int(seconds)
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if h > 0:
            return f"{h}h {m}m {s}s"

        if m > 0:
            return f"{m}m {s}s"

        return f"{s}s"

    def _build_discord_embed(self, message_prefix, loop_count, include_image=False):
        """Build a rich Discord embed matching the Cycle Checkpoint style."""
        clean_title = (message_prefix or "").replace("**", "").replace("\n", " ").strip()
        if not clean_title:
            clean_title = "Update"
        title = f"Solar Fishing Slayers 2 | {clean_title}"
        # Extract a numeric cycle if present (e.g. "Cycle #1440" -> "1440")
        cycle_display = str(loop_count)
        m = re.search(r"#?\s*(\d+)", str(loop_count))
        if m:
            cycle_display = m.group(1)
        elif getattr(self, "current_cycle", 0):
            cycle_display = str(self.current_cycle)
        running = "N/A"
        if getattr(self, "session_start", None):
            running = self._format_duration(time.time() - self.session_start)
        catch_pct = int(getattr(self, "catch_rate", 0.0) * 100)
        perfect_pct = int(getattr(self, "perfect_catch_rate", 0.0) * 100)
        catch_display = f"{catch_pct}% | {perfect_pct}% Perfect"
        rod = getattr(self, "current_rod_name", None) or "Default"
        embed = {
            "title": title,
            "description": "**Fishing update**\nFishing session update",
            "color": 0x5865F2,
            "fields": [
                {"name": "Rod", "value": str(rod), "inline": False},
                {"name": "Current Cycle", "value": cycle_display, "inline": True},
                {"name": "Running time", "value": running, "inline": True},
                {"name": "Catch Rate", "value": catch_display, "inline": True},
            ],
            "footer": {"text": f"Solar Fishing Slayers 2 V{APP_VERSION}"},
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        if include_image:
            embed["image"] = {"url": "attachment://screenshot.png"}
        return embed

    def _discord_text_worker(self, webhook_url, message_prefix, loop_count):
        """Worker function to send text webhook as a rich embed."""
        logging_name = self.vars["logging_name"]
        try:
            payload = {
                "username": logging_name,
                "embeds": [self._build_discord_embed(message_prefix, loop_count, include_image=False)],
            }
            response = requests.post(webhook_url, json=payload, timeout=10)
            if response.status_code in (200, 204):
                self.set_status(f"Discord text sent ({loop_count})")
            else:
                self.set_status(f"Error: Discord text failed: {response.status_code}")
        except Exception as e:
            self.set_status(f"Error sending Discord text: {e}")
    def _discord_screenshot_worker(self, webhook_url, message_prefix, loop_count):
        logging_name = self.vars["logging_name"]
        try:
            if self.capture_frame is None:
                screenshot = self.capture_single_frame()
            else:
                screenshot = self.capture_frame
            if screenshot is None:
                self.set_status("Error: failed to capture screenshot for Discord")
                return

            # Ensure Bgr For Imencode (MSS Already Bgr; Quartz Conversion Is Bgr)
            if screenshot.shape[2] == 4:
                screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)
            _, buffer = cv2.imencode(".png", screenshot)
            img_byte_arr = io.BytesIO(buffer.tobytes())
            embed = self._build_discord_embed(message_prefix, loop_count, include_image=True)
            payload = {
                "username": logging_name,
                "embeds": [embed],
            }
            files = {"file": ("screenshot.png", img_byte_arr, "image/png")}
            response = requests.post(webhook_url, data={"payload_json": json.dumps(payload)}, files=files, timeout=15,)
            if response.status_code in (200, 204):
                self.set_status(f"Discord screenshot sent ({loop_count})")
            else:
                self.set_status(f"Error: Discord screenshot failed: {response.status_code}")
        except Exception as e:
            self.set_status(f"Error sending Discord screenshot: {e}")
    def _debug_log_worker(self, text, loop_count):
        """Write debug logs to a text file."""
        try:
            # Use Base Path For Logs
            log_dir = EDITABLE_PATH
            os.makedirs(log_dir, exist_ok=True)
            # Daily Log File
            log_file = os.path.join(log_dir, f"debug_{time.strftime('%Y-%m-%d')}.txt")
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            log_entry = ("==========\n" f"🎣 {text}\n" f"🔄 {loop_count}\n" f"🕐 {timestamp}\n" "==========\n\n")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
            self.set_status(f"Debug log saved ({loop_count})")
        except Exception as e:
            self.set_status(f"Error writing debug log: {e}")

    def start_macro(self):
        try:
            self.status_overlay.set_main_status("Initialization")
            # 1. Core Config & Modes
            scale = get_scale_factor()
            self.macro_running = True
            self.session_start = time.time()
            # Catch Metrics (0 - Success, 1 - Failed, 2 - N/A Initial State)
            self.fish_caught = 2
            self.perfect_catch = 2
            self.catch_rate = 0.0
            successful_catches = 0
            perfect_catches = 0
            logging_cycle2 = 0
            # Areas
            fish_left, fish_top, fish_right, fish_bottom, fish_width, fish_height = self.get_areas("fish")
            # Fish Overlay
            fish_overlay = self.vars["fish_overlay"]
            status_overlay = self.vars["status_overlay"]
            logging_mode = self.vars["logging_mode"]
            if fish_overlay == True:
                # Position The Overlay Just Above Or Below The Fish Bar So It Does
                # Not Cover The Actual Minigame.  Show() Expects (Left, Top, Width,
                # Height) In Physical Pixels — Not Right/Bottom.
                fish_center = int((fish_top + fish_bottom) / 2)
                if fish_center > HALF_HEIGHT:
                    fish_top_overlay = fish_top + fish_height + fish_height
                else:
                    fish_top_overlay = fish_top - fish_height - fish_height
                overlay_width = fish_right - fish_left
                overlay_height = int(fish_height / 1.5)
                self.fish_overlay.show(fish_left, fish_top_overlay, overlay_width, overlay_height,)
            else:
                self.fish_overlay.hide()
            # Status Overlay
            if status_overlay == True:
                # Position The Status Overlay At The Top Left, But Avoiding The macOS Menu Offset.
                self.status_overlay.show(self.status_left, self.status_top, self.status_right, self.status_bottom)
            else:
                self.status_overlay.hide()
        except KeyError as e:
            self.stop_macro(f"Config Error: {e}")
            return

        # Main Loop (With Bug Reports)
        try:
            while self.macro_running:
                self.status_overlay.set_main_status("Resetting Statistics")
                self.set_status("Resetting statistics")
                self.capture_id = 0
                # Update Current Cycle
                self.current_cycle = self.current_cycle + 1
                # Auto Buy Bait
                self.execute_buy_bait()
                # Cast
                self.execute_cast()

                # Minigame (white appears → track → white gone)
                if not self.macro_running:
                    break
                ok = self.execute_fish_stage()

                if not ok:
                    # Fail-cast restart: the original returns False to signal "restart"
                    # (fishing_cycle's run_one_cycle → returns False → next loop iteration)
                    # main.py's while loop already does this naturally; just skip stats/collect.
                    continue

                if not self.macro_running:
                    break

                # Collect
                if self.vars.get("collect_after_minigame", True):
                    self.interruptible_sleep(self._get_var_number("after_minigame_sec", 2.0, float))
                    self.execute_collect()
                # Update Catch Rate After The Minigame Finishes
                if self.perfect_catch == 0:
                    perfect_catches += 1
                if self.fish_caught == 0:
                    successful_catches += 1
                self.catch_rate = successful_catches / self.current_cycle
                self.perfect_catch_rate = perfect_catches / self.current_cycle
                if logging_mode != "disabled":
                    if self.current_cycle == logging_cycle:
                        self.send_logging("**Cycle Checkpoint**", f"Cycle #{self.current_cycle}")
                        logging_cycle = logging_cycle2 + self.current_cycle
            self.stop_macro("")
            return

        except Exception as e:
            time.sleep(0.2)
            full_error = traceback.format_exc()
            error_line = self.get_error_line(full_error)
            result = self.message_box_javascript(f"""An error at line {error_line} occured. 
            Please copy the error and report the bug:\\n{e}\\n Would you like to copy the full crash log to your clipboard?""", "askyesno")
            if result == True:
                if self.copy_to_clipboard(full_error):
                    self.message_box_javascript("Error copied over to clipboard")
                else:
                    self.message_box_javascript("Failed to copy error to clipboard")
            if IS_COMPILED == False:
                print(full_error)
            else:
                self.send_logging(f"Error at line {error_line}: {e}", 0)
            self.macro_running = False
            self.stop_macro(f"Error at line {error_line}: {e}")
            return

    def execute_collect(self):
        """Hold-click the collect point for collect_hold_sec (ported from run_collect)."""
        hold_s = max(0.1, self._get_var_number("collect_hold_sec", 3.0, float))
        after_s = max(0.0, self._get_var_number("after_collect_sec", 0.35, float))
        self.status_overlay.set_main_status("Collecting")
        self.set_status(f"Collecting fish ({hold_s:.1f}s hold)…")
        if not self.macro_running:
            return
        try:
            cx, cy = self._split_ratio(str(self.vars.get("collect_point", "0.5,0.5")), screen_coords=True)
        except Exception:
            return
        # Move cursor to the collect point, then hold
        self._click_at(cx, cy)  # single click to position (also releases quickly)
        if not self.macro_running:
            return
        self.hold_mouse(False)
        try:
            self.interruptible_sleep(hold_s)
        finally:
            self.release_mouse(False)
        self.interruptible_sleep(after_s)

    def execute_buy_bait(self):
        """Run the bait purchase sequence using the web UI's settings."""
        if not self.macro_running or not self.vars.get("auto_purchase_bait", False):
            return

        try:
            amount = max(1, int(str(self.vars.get("purchase_amount", "10")).strip()))
        except (TypeError, ValueError):
            amount = 10

        def timing(name, default):
            return max(0.0, self._get_var_number(name, default, float))

        # Point selector values are normalized screen ratios, as in fishing_cycle.py.
        points = {}
        for index in range(1, 8):
            key = f"bait_{index}"
            value = str(self.vars.get(f"{key}_point", "")).strip()
            try:
                x_text, y_text = value.replace(" ", "").split(",", 1)
                x, y = float(x_text), float(y_text)
                if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                    raise ValueError("point is outside the screen")
            except (TypeError, ValueError, IndexError):
                self.set_status(f"Buy bait stopped: set the {key.replace('_', ' ')} point first.")
                return
            points[key] = (x, y)

        clicks = amount - 1
        self.status_overlay.set_main_status("Buying bait")
        self.set_status(f"Buying bait (p4 ×{clicks}, amount {amount})…")

        if not self.macro_running:
            return
        self._send_key("T", delay=timing("key_hold_sec", 0.1))
        self.interruptible_sleep(timing("after_t_sec", 2.0))

        settle = timing("click_settle_sec", 0.18)
        between = timing("between_clicks_sec", 1.5)
        for key in ("bait_1", "bait_2", "bait_3"):
            if not self.macro_running:
                return
            self._click_at(*self._split_ratio(f"{points[key][0]},{points[key][1]}", screen_coords=True))
            self.interruptible_sleep(settle)
            self.interruptible_sleep(between)

        for index in range(clicks):
            if not self.macro_running:
                return
            self.set_status(f"Buying bait — p4 {index + 1}/{clicks}")
            self._click_at(*self._split_ratio(f"{points['bait_4'][0]},{points['bait_4'][1]}", screen_coords=True))
            self.interruptible_sleep(timing("p4_click_settle_sec", 0.02))
            self.interruptible_sleep(timing("between_p4_clicks_sec", 0.08))

        self.interruptible_sleep(between)
        gaps = {"bait_5": timing("between_p5_p6_sec", 1.8),
                "bait_6": timing("between_p6_p7_sec", 1.8),
                "bait_7": between}
        for key in ("bait_5", "bait_6", "bait_7"):
            if not self.macro_running:
                return
            self._click_at(*self._split_ratio(f"{points[key][0]},{points[key][1]}", screen_coords=True))
            self.interruptible_sleep(settle)
            self.interruptible_sleep(gaps[key])

        self.interruptible_sleep(timing("after_purchase_sec", 0.9))

    def execute_cast(self):
        self.status_overlay.set_main_status("Casting")
        cast_use_scan_top_left = bool(self.vars.get("cast_use_scan_top_left", False))
        if cast_use_scan_top_left:
            # Click slightly outside the top-left of the fish/scan area
            fish_left, fish_top, _, _, _, _ = self.get_areas("fish")
            outset = int(round(self._get_var_number("cast_top_left_outset_px", 28.0, float)))
            cx = max(0, fish_left - outset)
            cy = max(0, fish_top - outset)
        else:
            cast_point = self.vars.get("cast_point", "0.5,0.5")
            cx, cy = self._split_ratio(str(cast_point), screen_coords=True)

        if self.macro_running:
            self._click_at(cx, cy)
            # Brief settle then after-cast delay (matches Reference 2 defaults)
            self.interruptible_sleep(self._get_var_number("cast_settle_sec", 0.08, float))
            self.interruptible_sleep(self._get_var_number("cast_after_sec", 0.25, float))

    def execute_fish_stage(self):
        """Track the minigame: wait white → track until white gone.

        Ported from fishing_cycle.py run_minigame(). Returns True if the minigame
        completed (white appeared then left), False on abort / fail-cast timeout.
        """
        # Lazily create the scanner (persist across cycles for warm state)
        if not hasattr(self, "_scanner") or self._scanner is None:
            self._scanner = ScreenScanner()

        scanner = self._scanner

        # ── Timings (map fishing_cycle keys → main.py vars) ──
        def _t(name, default):
            return max(0.0, self._get_var_number(name, default, float))

        target_fps = max(5.0, _t("task_fps", 30.0))
        frame_budget = 1.0 / target_fps
        poll = _t("poll_sec", 0.04)
        gone_need = max(3, int(_t("white_gone_frames", 12)))
        start_timeout = _t("wait_minigame_start_sec", 20.0)
        end_timeout = _t("wait_minigame_end_sec", 120.0)

        # ── Controller settings (ported from main _enter_minigame) ──
        controller_mode = str(self.vars.get("controller_mode", "predictive")).lower()
        kp = max(abs(self._get_var_number("kp", 0.45)), 0.01)
        kd = max(abs(self._get_var_number("kd", 0.35)), 0.01)
        stopping_distance = max(abs(self._get_var_number("stopping_distance", 0.5)), 0.01)
        velocity_smoothing = min(max(abs(self._get_var_number("velocity_smoothing", 0.3)), 0.01), 1.0)
        scan_delay = max(0.001, _t("minigame_scan_delay", 0.02))

        scanner.reset_tracking()

        # Controller state (for Normal / Steady / Predictive)
        last_error = 0.0
        last_white_y = None
        last_zone_c = None
        color_check_bar_velocity = 0.0
        color_check_target_velocity = 0.0
        is_initial_run = True

        # Track local hold state so we only fire press/release once per transition
        mouse_down = False
        def _set_hold(hold):
            nonlocal mouse_down
            if hold and not mouse_down:
                self.hold_mouse(False)
                mouse_down = True
            elif not hold and mouse_down:
                self.release_mouse(False)
                mouse_down = False

        _set_hold(False)

        # ── Scan rect (physical screen pixels) ──
        fish_left, fish_top, fish_right, fish_bottom, fish_width, fish_height = \
            self.get_areas("fish")

        # Overlay draw coords are relative to the overlay window, which is
        # positioned at (fish_left, fish_top_overlay) with size overlay_width × overlay_height.
        # We reconstruct that geometry the same way start_macro did:
        fish_center = int((fish_top + fish_bottom) / 2)
        if fish_center > HALF_HEIGHT:
            fish_top_overlay = fish_top + fish_height + fish_height
        else:
            fish_top_overlay = fish_top - fish_height - fish_height
        overlay_w = fish_right - fish_left
        overlay_h = int(fish_height / 1.5)

        def _draw(box, color, show_center=False):
            """Queue a box for the fish overlay (crop-relative → overlay px)."""
            if box is None:
                return
            try:
                # Map scan-crop px → overlay px (overlay is scaled by 1/1.5 vertically)
                sx = overlay_w / max(1, fish_width)
                sy = overlay_h / max(1, fish_height)
                x1 = int(box.x * sx)
                y1 = int(box.y * sy)
                x2 = int((box.x + box.w) * sx)
                y2 = int((box.y + box.h) * sy)
                # draw_box expects physical px and divides by scale internally
                self.fish_overlay.draw_box(x1, y1, x2, y2, color, show_bar_center=show_center)
            except Exception:
                pass

        self.status_overlay.set_main_status("Fishing")
        self.set_status("Waiting for minigame (white)…")

        started = False
        gone_streak = 0
        start_deadline = time.perf_counter() + start_timeout
        end_deadline = start_deadline + end_timeout
        last_id = -1
        last_time = time.perf_counter()
        try:
            while self.macro_running:
                t0 = time.perf_counter()

                # ── Grab the latest captured frame (background thread updates it) ──
                frame = self.capture_frame
                if frame is None or self.capture_id == last_id:
                    # No new frame yet — yield
                    self.interruptible_sleep(min(poll, 0.01))
                    continue
                last_id = self.capture_id

                # Crop to scan area (clamp to frame bounds)
                h, w = frame.shape[:2]
                l = max(0, min(fish_left, w - 1))
                tp = max(0, min(fish_top, h - 1))
                r = max(l + 1, min(fish_right, w))
                b = max(tp + 1, min(fish_bottom, h))
                crop = frame[tp:b, l:r]
                if crop.size == 0:
                    self.interruptible_sleep(poll)
                    continue

                # Fresh white check (no stick) — mirrors scanner.white_present
                present = scanner.white_present(crop)
                white, zone = scanner.detect(crop)

                now = time.perf_counter()

                if not started:
                    if present:
                        started = True
                        gone_streak = 0
                        end_deadline = now + end_timeout
                        self.status_overlay.set_main_status("Tracking")
                        self.set_status("Minigame — tracking…")
                    elif now >= start_deadline:
                        self.set_status("Fail cast (20s) — no minigame, restarting.")
                        _set_hold(False)
                        self.fish_overlay.clear()
                        return False
                else:
                    if not present:
                        gone_streak += 1
                        _set_hold(False)
                        if gone_streak >= gone_need:
                            self.set_status("Minigame done — white gone.")
                            self.fish_overlay.clear()
                            return True
                    else:
                        gone_streak = 0

                    if white is not None and zone is not None:
                        white_y = float(white.mid_y)
                        zone_top = float(zone.top)
                        zone_bot = float(zone.bottom)
                        zone_c = 0.5 * (zone_top + zone_bot)
                        half = 0.5 * max(1.0, zone_bot - zone_top)

                        # Boundary check (adapted from SolarFishing)
                        if white_y < zone_top:
                            control_signal = -30  # release to go down
                        elif white_y > zone_bot:
                            control_signal = 30   # hold to go up
                        else:
                            error = white_y - zone_c
                            time_delta = now - last_time
                            if time_delta < 0.001:
                                time_delta = 0.001
                            last_time = now

                            if controller_mode == "normal":
                                # Normal: Traditional PD Controller
                                if is_initial_run:
                                    control_signal = 0
                                    last_error = error
                                else:
                                    p_term_multiplier = time_delta / scan_delay
                                    p_term = int(error / p_term_multiplier) * kp
                                    d_term = ((error - last_error) / time_delta) * kd
                                    control_signal = p_term + d_term
                                last_error = error
                            elif controller_mode == "steady":
                                # Steady: Asymmetric damping
                                if is_initial_run:
                                    control_signal = 0
                                    last_error = error
                                else:
                                    p_term_multiplier = time_delta / scan_delay
                                    p_term = int(error / p_term_multiplier) * kp
                                    bar_velocity = (zone_c - (last_zone_c or zone_c))
                                    error_magnitude_decreasing = abs(error) < abs(last_error)
                                    bar_moving_toward_target = (bar_velocity > 0 and error > 0) or (bar_velocity < 0 and error < 0)
                                    if error_magnitude_decreasing and bar_moving_toward_target:
                                        steady_kd_multiplier = 5.0
                                    else:
                                        steady_kd_multiplier = 0.2
                                    d_term = ((error - last_error) / time_delta) * kd * steady_kd_multiplier
                                    control_signal = p_term + d_term
                                last_error = error
                            elif controller_mode == "predictive":
                                # Predictive: stopping distance + counter-thrust
                                if last_white_y is not None and last_zone_c is not None and time_delta > 0:
                                    raw_bar_velocity = (zone_c - last_zone_c) / time_delta
                                    raw_target_velocity = (white_y - last_white_y) / time_delta
                                    color_check_bar_velocity = (velocity_smoothing * raw_bar_velocity +
                                                                (1 - velocity_smoothing) * color_check_bar_velocity)
                                    color_check_target_velocity = (velocity_smoothing * raw_target_velocity +
                                                                    (1 - velocity_smoothing) * color_check_target_velocity)
                                relative_velocity = color_check_bar_velocity - color_check_target_velocity
                                if not np.isfinite(relative_velocity):
                                    relative_velocity = 0.0
                                stopping_distance2 = abs(relative_velocity) * stopping_distance
                                if zone_top <= white_y <= zone_bot:
                                    if error > stopping_distance2:
                                        control_signal = 30
                                    elif error < -stopping_distance2:
                                        control_signal = -30
                                    else:
                                        if relative_velocity > 0:
                                            control_signal = -30
                                        else:
                                            control_signal = 30
                                else:
                                    control_signal = kp * error + kd * relative_velocity
                            else:
                                # Fallback to Normal (PD) if mode is unrecognized
                                if is_initial_run:
                                    control_signal = 0
                                    last_error = error
                                else:
                                    p_term_multiplier = time_delta / scan_delay
                                    p_term = int(error / p_term_multiplier) * kp
                                    d_term = ((error - last_error) / time_delta) * kd
                                    control_signal = p_term + d_term
                                last_error = error

                            last_white_y = white_y
                            last_zone_c = zone_c
                            is_initial_run = False

                        hold = control_signal > 0
                        _set_hold(hold)
                        # Draw overlay boxes (crop-local px)
                        _draw(zone, "#00FF00", show_center=False)
                        _draw(white, "#FFFFFF", show_center=True)
                    else:
                        _set_hold(False)

                    if now >= end_deadline:
                        self.set_status("Minigame timeout — collecting anyway.")
                        _set_hold(False)
                        return True

                # ── Frame budget ──
                elapsed = time.perf_counter() - t0
                leftover = frame_budget - elapsed
                if leftover > 0:
                    # Sleep in small chunks so stop_key is responsive
                    self.interruptible_sleep(min(leftover, 0.02))

        except Exception as exc:
            _set_hold(False)
            self.set_status(f"Minigame error: {exc}")
            return False
        finally:
            # Always release the mouse on exit (abort, exception, timeout)
            _set_hold(False)
            try:
                self.fish_overlay.clear()
            except Exception:
                pass

        return False

    def stop_macro(self, text="Macro Stopped"):
        self.macro_running = False
        try:
            self.fish_overlay.hide()
        except:
            pass

        try:
            self.status_overlay.hide()
        except:
            pass

        if (self.macro_thread and self.macro_thread.is_alive() and self.macro_thread is not threading.current_thread()):
            self.macro_thread.join()
        if (self.capture_thread and self.capture_thread.is_alive() and self.capture_thread is not threading.current_thread()):
            self.capture_thread.join()
        # Fully Release Dxcamera So A Later Dxcam.Create() Does Not Hit The
        # "instance already exists ... Delete the old object with `del obj`" warning.
        try:
            if self.camera is not None:
                try:
                    self.camera.stop()
                except Exception:
                    pass

                try:
                    del self.camera
                except Exception:
                    pass

                self.camera = None
        except Exception:
            pass

        if not text == "":
            self.set_status(text)
        try:
            window.show()
        except Exception:
            pass

# Main Window
def on_closed():
    # Tear down child overlays so webview.start() can return. Overlay hide()
    # methods must not block the GUI thread (eyedropper schedules destroy).
    for closer in (api.fish_overlay.hide, api.status_overlay.hide, 
                   api.eyedropper.hide, api.area_selector.hide):
        try:
            closer()
        except Exception:
            pass

api = Api()
window = webview.create_window(
    f"Solar Fishing Slayers 2 V{APP_VERSION}",
    os.path.join(UI_PATH, "index.html"),
    js_api=api,
    width=880,
    height=660,
    frameless=True,
    easy_drag=False,
    focus=True,
    text_select=True,
)
api._window = window
window.events.closed += on_closed
webview.start()
