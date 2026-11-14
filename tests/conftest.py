import os

# Run GUI tests without opening real windows (also needed on CI without a display).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
