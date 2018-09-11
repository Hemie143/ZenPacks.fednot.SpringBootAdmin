# import os
from ZenPacks.zenoss.ZenPackLib import zenpacklib

# CFG = zenpacklib.load_yaml([os.path.join(os.path.dirname(__file__), "zenpack.yaml")], verbose=False, level=30)
# schema = CFG.zenpack_module.schema

CFG = zenpacklib.load_yaml(verbose=False, level=20)
schema = CFG.zenpack_module.schema