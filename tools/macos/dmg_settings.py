# dmgbuild settings for the Econoclast disk image; tools/macos/build.py passes the paths with -D.
# The window is the size of the background (660 x 400 points); Finder reads the bounds as content.
import os.path

application = defines["app"]  # noqa: F821 - injected by dmgbuild
appname = os.path.basename(application)

format = "ULMO"  # lzma: smallest, opens on macOS 10.15+
files = [application]
symlinks = {"Applications": "/Applications"}
icon = defines["icon"]  # noqa: F821 - the volume icon
background = defines["background"]  # noqa: F821

window_rect = ((200, 140), (660, 400))
default_view = "icon-view"
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
show_icon_preview = False
arrange_by = None
icon_size = 112
text_size = 13
label_pos = "bottom"
icon_locations = {appname: (165, 206), "Applications": (495, 206)}
