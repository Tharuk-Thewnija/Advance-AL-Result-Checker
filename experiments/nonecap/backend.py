"""Keep the isolated launcher while using the promoted controller."""
from qt_app.backend import Bridge

class PrototypeBridge(Bridge):
    def __init__(self, **kwargs):
        super().__init__(prototype=True, **kwargs)
