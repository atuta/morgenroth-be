from django.apps import AppConfig


class MappConfig(AppConfig):
    name = "mapp"

    def ready(self):
        import mapp.signals

