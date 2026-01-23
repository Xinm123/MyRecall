# Backward compatibility for existing code
# This allows 'from openrecall.server.database import ...' to work as before
# by re-exporting everything from the legacy module.

from .legacy import *
