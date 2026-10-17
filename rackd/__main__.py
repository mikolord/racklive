from . import updater

updater.boot_guard()                      # a freshly installed version that cannot start is rolled back here, before anything else is imported
from .server import main

main()
