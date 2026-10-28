"""atwork: exit 0 if it is currently working time, 1 if not.

Designed for chaining in cron jobs:

    */15 * * * *  atwork && /usr/local/bin/send-reminders
"""

__version__ = "0.1.0"
