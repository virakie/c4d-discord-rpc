import os
import sys
import time
import c4d
from c4d import plugins, gui
from c4d.threading import C4DThread

# ── Bundle local pypresence ───────────────────────────────────────────────────
_plugin_dir = os.path.dirname(__file__)
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

from pypresence import Presence
from pypresence.exceptions import InvalidPipe

# ─────────────────────────────────────────────────────────────────────────────
#  IDs
# ─────────────────────────────────────────────────────────────────────────────

PLUGIN_ID     = 1057290
PLUGIN_ID_CMD = 1057291

# Widget IDs
ID_HEADER          = 2000
ID_STATUS_BAR      = 2001
ID_GRP_DISPLAY     = 2010
ID_SHOW_SCENE      = 2011
ID_SHOW_VERSION    = 2012
ID_SHOW_TIMER      = 2013
ID_GRP_CUSTOM      = 2020
ID_CUSTOM_TOGGLE   = 2021
ID_CUSTOM_LABEL    = 2022
ID_CUSTOM_TEXT     = 2023
ID_GRP_PREVIEW     = 2030
ID_PREVIEW_LINE1   = 2031
ID_PREVIEW_LINE2   = 2032
ID_PREVIEW_TIMER   = 2033
ID_GRP_BUTTONS     = 2040
ID_BTN_APPLY       = 2041
ID_BTN_CLOSE       = 2042

# ─────────────────────────────────────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────────────────────────────────────

DISCORD_APP_ID  = "843479489245872130"
UPDATE_INTERVAL = 15
LARGE_IMAGE_KEY = "logo"

_settings = {
    "show_scene":   True,
    "show_version": True,
    "show_timer":   True,
    "custom_on":    False,
    "custom_text":  "",
}

# ─────────────────────────────────────────────────────────────────────────────
#  Compat helpers  (safe across R20 → 2026)
# ─────────────────────────────────────────────────────────────────────────────

def _bc_get_string(bc, id):
    """GetString default-arg signature changed between C4D versions."""
    try:
        return bc.GetString(id, "")
    except TypeError:
        return bc.GetString(id)

def _safe_format(template, **kw):
    """str.format() fallback — avoids any f-string Python version edge cases."""
    return template.format(**kw)

# ─────────────────────────────────────────────────────────────────────────────
#  Prefs persistence
# ─────────────────────────────────────────────────────────────────────────────

def _load_settings():
    try:
        bc = plugins.GetWorldPluginData(PLUGIN_ID)
        if bc is None:
            return
        _settings["show_scene"]   = bc.GetBool(ID_SHOW_SCENE,    True)
        _settings["show_version"] = bc.GetBool(ID_SHOW_VERSION,  True)
        _settings["show_timer"]   = bc.GetBool(ID_SHOW_TIMER,    True)
        _settings["custom_on"]    = bc.GetBool(ID_CUSTOM_TOGGLE, False)
        _settings["custom_text"]  = _bc_get_string(bc, ID_CUSTOM_TEXT)
    except Exception as e:
        print("[C4D RPC] Could not load settings: " + str(e))


def _save_settings():
    try:
        bc = c4d.BaseContainer()
        bc.SetBool(ID_SHOW_SCENE,    _settings["show_scene"])
        bc.SetBool(ID_SHOW_VERSION,  _settings["show_version"])
        bc.SetBool(ID_SHOW_TIMER,    _settings["show_timer"])
        bc.SetBool(ID_CUSTOM_TOGGLE, _settings["custom_on"])
        bc.SetString(ID_CUSTOM_TEXT, _settings["custom_text"])
        plugins.SetWorldPluginData(PLUGIN_ID, bc)
    except Exception as e:
        print("[C4D RPC] Could not save settings: " + str(e))

# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _c4d_version():
    try:
        ver   = c4d.GetC4DVersion()
        major = ver // 1000
        minor = ver % 1000
        if major >= 2023:
            return "{0}.{1}".format(major, minor // 10)
        return "R{0}.{1:03d}".format(major, minor)
    except Exception:
        return "Unknown"


def _scene_name():
    try:
        doc = c4d.documents.GetActiveDocument()
        if doc is None:
            return "Untitled"
        name = doc.GetDocumentName() or ""
        base = os.path.splitext(name)[0]
        return base.strip() or "Untitled"
    except Exception:
        return "Untitled"


def _build_presence_fields():
    line1, line2 = [], []

    if _settings["show_scene"]:
        line1.append(_scene_name())
    if _settings["custom_on"] and _settings["custom_text"].strip():
        line1.append(_settings["custom_text"].strip())
    if _settings["show_version"]:
        line2.append("Cinema 4D  " + _c4d_version())

    details = "  \u00b7  ".join(line1) or None
    state   = "  \u00b7  ".join(line2) or None
    start   = _start_time if _settings["show_timer"] else None
    return details, state, start

# ─────────────────────────────────────────────────────────────────────────────
#  Globals
# ─────────────────────────────────────────────────────────────────────────────

_rpc        = None
_thread     = None
_connected  = False
_start_time = 0

# ─────────────────────────────────────────────────────────────────────────────
#  Presence
# ─────────────────────────────────────────────────────────────────────────────

def _connect():
    global _rpc, _connected, _start_time
    try:
        _rpc = Presence(DISCORD_APP_ID)
        _rpc.connect()
        _start_time = int(time.time())
        _connected  = True
        print("[C4D RPC] Connected to Discord.")
        return True
    except InvalidPipe:
        print("[C4D RPC] Discord not running — RPC inactive.")
    except Exception as e:
        print("[C4D RPC] Connection error: " + str(e))
    _connected = False
    return False


def _update():
    global _connected
    if not _connected:
        return
    details, state, start = _build_presence_fields()
    try:
        _rpc.update(
            details     = details,
            state       = state,
            start       = start,
            large_image = LARGE_IMAGE_KEY,
            large_text  = "Cinema 4D " + _c4d_version(),
        )
    except InvalidPipe:
        print("[C4D RPC] Lost connection, reconnecting…")
        _connected = False
        _connect()
    except Exception as e:
        print("[C4D RPC] Update error: " + str(e))

# ─────────────────────────────────────────────────────────────────────────────
#  Background thread
# ─────────────────────────────────────────────────────────────────────────────

class RPCThread(C4DThread):
    def Main(self):
        while not self.TestBreak():
            _update()
            deadline = time.time() + UPDATE_INTERVAL
            while time.time() < deadline:
                if self.TestBreak():
                    return
                time.sleep(0.5)

# ─────────────────────────────────────────────────────────────────────────────
#  Settings dialog
# ─────────────────────────────────────────────────────────────────────────────

# Spacing constants — tweak these to adjust the look
_PAD  = 6    # outer margin
_GAP  = 4    # gap between groups

class SettingsDialog(gui.GeDialog):

    def CreateLayout(self):
        self.SetTitle("Discord RPC")

        # ── Outer padding ────────────────────────────────────────────────────
        self.GroupBegin(0, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 1, 0, "", 0, _PAD, _PAD)
        self.GroupBorderSpace(_PAD, _PAD, _PAD, _PAD)

        # ── Status bar ───────────────────────────────────────────────────────
        self.GroupBegin(0, c4d.BFH_SCALEFIT, 1, 0, "", 0)
        self.GroupBorderSpace(0, 0, 0, _GAP)
        self.AddStaticText(
            ID_STATUS_BAR,
            c4d.BFH_SCALEFIT,
            name = self._status_text(),
        )
        self.GroupEnd()

        self.AddSeparatorH(0, c4d.BFH_SCALEFIT)

        # ── Display group ────────────────────────────────────────────────────
        self.GroupBegin(ID_GRP_DISPLAY, c4d.BFH_SCALEFIT, 1, 0, "Display", c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(_PAD, _PAD, _PAD, _PAD)
        self.AddCheckbox(ID_SHOW_SCENE,   c4d.BFH_LEFT, 0, 0, "  Scene name")
        self.AddCheckbox(ID_SHOW_VERSION, c4d.BFH_LEFT, 0, 0, "  C4D version")
        self.AddCheckbox(ID_SHOW_TIMER,   c4d.BFH_LEFT, 0, 0, "  Elapsed timer")
        self.GroupEnd()

        # ── Custom line group ─────────────────────────────────────────────────
        self.GroupBegin(ID_GRP_CUSTOM, c4d.BFH_SCALEFIT, 1, 0, "Custom Line", c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(_PAD, _PAD, _PAD, _PAD)
        self.AddCheckbox(ID_CUSTOM_TOGGLE, c4d.BFH_LEFT, 0, 0, "  Enable custom text")

        # label + text field row
        self.GroupBegin(0, c4d.BFH_SCALEFIT, 2, 1, "", 0)
        self.GroupBorderSpace(_PAD, 2, 0, 0)
        self.AddStaticText(ID_CUSTOM_LABEL, c4d.BFH_LEFT, 40, 0, "Text")
        self.AddEditText(ID_CUSTOM_TEXT, c4d.BFH_SCALEFIT | c4d.BFV_CENTER, 0, 0)
        self.GroupEnd()
        self.GroupEnd()

        # ── Preview group ─────────────────────────────────────────────────────
        self.GroupBegin(ID_GRP_PREVIEW, c4d.BFH_SCALEFIT, 1, 0, "Preview", c4d.BORDER_GROUP_IN)
        self.GroupBorderSpace(_PAD, _PAD, _PAD, _PAD)
        self.AddStaticText(ID_PREVIEW_LINE1, c4d.BFH_SCALEFIT, 0, 0, "")
        self.AddStaticText(ID_PREVIEW_LINE2, c4d.BFH_SCALEFIT, 0, 0, "")
        self.AddStaticText(ID_PREVIEW_TIMER, c4d.BFH_SCALEFIT, 0, 0, "")
        self.GroupEnd()

        self.AddSeparatorH(0, c4d.BFH_SCALEFIT)

        # ── Buttons ───────────────────────────────────────────────────────────
        self.GroupBegin(ID_GRP_BUTTONS, c4d.BFH_SCALEFIT, 3, 1, "", 0)
        self.GroupBorderSpace(0, _GAP, 0, 0)
        self.AddButton(ID_BTN_APPLY, c4d.BFH_SCALEFIT, 0, 0, "Apply")
        self.AddStaticText(0, c4d.BFH_FIT, 8, 0, "")   # spacer
        self.AddButton(ID_BTN_CLOSE, c4d.BFH_SCALEFIT, 0, 0, "Close")
        self.GroupEnd()

        self.GroupEnd()  # outer padding group
        return True

    # ── Init ─────────────────────────────────────────────────────────────────

    def InitValues(self):
        self.SetBool(ID_SHOW_SCENE,    _settings["show_scene"])
        self.SetBool(ID_SHOW_VERSION,  _settings["show_version"])
        self.SetBool(ID_SHOW_TIMER,    _settings["show_timer"])
        self.SetBool(ID_CUSTOM_TOGGLE, _settings["custom_on"])
        self.SetString(ID_CUSTOM_TEXT, _settings["custom_text"])
        self._sync_custom_field()
        self._refresh_preview()
        return True

    # ── Commands ──────────────────────────────────────────────────────────────

    def Command(self, id, msg):
        if id == ID_CUSTOM_TOGGLE:
            self._sync_custom_field()
            self._refresh_preview()

        elif id in (ID_SHOW_SCENE, ID_SHOW_VERSION, ID_SHOW_TIMER, ID_CUSTOM_TEXT):
            self._refresh_preview()

        elif id == ID_BTN_APPLY:
            _settings["show_scene"]   = self.GetBool(ID_SHOW_SCENE)
            _settings["show_version"] = self.GetBool(ID_SHOW_VERSION)
            _settings["show_timer"]   = self.GetBool(ID_SHOW_TIMER)
            _settings["custom_on"]    = self.GetBool(ID_CUSTOM_TOGGLE)
            _settings["custom_text"]  = self.GetString(ID_CUSTOM_TEXT)
            _save_settings()
            _update()
            self._refresh_status()
            print("[C4D RPC] Settings applied.")

        elif id == ID_BTN_CLOSE:
            self.Close()

        return True

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _status_text(self):
        if _connected:
            return "\u25cf  Connected to Discord"
        return "\u25cb  Not connected  (is Discord running?)"

    def _refresh_status(self):
        try:
            self.SetString(ID_STATUS_BAR, self._status_text())
        except Exception:
            pass

    def _sync_custom_field(self):
        enabled = self.GetBool(ID_CUSTOM_TOGGLE)
        self.Enable(ID_CUSTOM_TEXT,    enabled)
        self.Enable(ID_CUSTOM_LABEL,   enabled)

    def _refresh_preview(self):
        """Rebuild the preview labels from the current widget state."""
        try:
            show_scene   = self.GetBool(ID_SHOW_SCENE)
            show_version = self.GetBool(ID_SHOW_VERSION)
            show_timer   = self.GetBool(ID_SHOW_TIMER)
            custom_on    = self.GetBool(ID_CUSTOM_TOGGLE)
            custom_text  = self.GetString(ID_CUSTOM_TEXT).strip()

            line1_parts = []
            if show_scene:
                line1_parts.append(_scene_name())
            if custom_on and custom_text:
                line1_parts.append(custom_text)

            line1 = "  \u00b7  ".join(line1_parts)
            line2 = ("Cinema 4D  " + _c4d_version()) if show_version else ""
            timer = "00:00 elapsed" if show_timer else ""

            self.SetString(ID_PREVIEW_LINE1, line1 if line1 else "(nothing on line 1)")
            self.SetString(ID_PREVIEW_LINE2, line2 if line2 else "(nothing on line 2)")
            self.SetString(ID_PREVIEW_TIMER, timer)
        except Exception:
            pass


_dialog = None

# ─────────────────────────────────────────────────────────────────────────────
#  Menu command
# ─────────────────────────────────────────────────────────────────────────────

class OpenSettingsCmd(plugins.CommandData):

    def Execute(self, doc):
        global _dialog
        if _dialog is None:
            _dialog = SettingsDialog()
        _dialog.Open(
            dlgtype  = c4d.DLG_TYPE_ASYNC,
            pluginid = PLUGIN_ID_CMD,
            xpos     = -2,
            ypos     = -2,
            defaultw = 320,
            defaulth = 0,
        )
        return True

    def GetState(self, doc):
        return c4d.CMD_ENABLED

# ─────────────────────────────────────────────────────────────────────────────
#  C4D lifecycle
# ─────────────────────────────────────────────────────────────────────────────

def PluginMessage(id, data):
    global _thread, _rpc, _connected

    if id == c4d.C4DPL_PROGRAM_STARTED:
        _load_settings()
        if _connect():
            _update()
            _thread = RPCThread()
            _thread.Start()

    elif id == c4d.C4DPL_ENDPROGRAM:
        if _thread:
            _thread.End()
        if _rpc and _connected:
            try:
                _rpc.clear()
                _rpc.close()
            except Exception:
                pass
        print("[C4D RPC] Disconnected.")

    elif id in (c4d.C4DPL_DOCUMENTIMPORTED, c4d.C4DPL_RELOADPYTHONPLUGINS):
        _update()

    return False


if __name__ == "__main__":
    plugins.RegisterCommandPlugin(
        id   = PLUGIN_ID_CMD,
        str  = "Discord RPC Settings",
        info = 0,
        icon = None,
        help = "Configure Cinema 4D Discord Rich Presence",
        dat  = OpenSettingsCmd(),
    )
