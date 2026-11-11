"""What the page tells her about the present moment, per turn (switches, language, camera, scene). One object instead of nine loose globals in app.py:
the chat engine writes it at the start of each turn, the prompt builder and the routes read it. Tests set fields directly (app.S.agent = True)."""


class Session:
    def __init__(self):
        self.agent = False      # the Actions switch: she may propose hands (every one still waits for the creator's press)
        self.work = False       # work mode: code, commands, projects, engines, documents (off for everyday talk)
        self.unreal = False     # the creator also allowed her to build in Unreal Engine (a fixed list of operations)
        self.control = False    # the creator also allowed her to work the mouse and keyboard (desktop window only)
        self.camera_on = False  # the page tells us per turn whether the camera is active
        self.presence = False   # "live conversation" mode: she behaves like a person sharing the room
        self.scene = 'night'    # the backdrop she stands in front of; the page reports it each turn
        self.ui_lang = 'en'
        self.last_lang = None


S = Session()
