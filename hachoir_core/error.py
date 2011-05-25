"""
Functions to display an error (error, warning or information) message.
"""

from hachoir_core.log import log
from hachoir_core.tools import makePrintable, makeUnicode
import sys, traceback

def getBacktrace(empty="Empty backtrace."):
    """
    Try to get backtrace as string.
    Returns "Error while trying to get backtrace" on failure.
    """
    try:
        info = sys.exc_info()
        trace = traceback.format_exception(*info)
        sys.exc_clear()
        if trace[0] != "None\n":
            return "".join(trace)
    except:
        # No i18n here (imagine if i18n function calls error...)
        return "Error while trying to get backtrace"
    return empty

class HachoirError(Exception):
    """
    Parent of all errors in Hachoir library
    """
    def __init__(self, message):
        self.message = makeUnicode(message)

    def __str__(self):
        return makePrintable(self.message, "ASCII")

    def __unicode__(self):
        return self.message

# Error classes which may be raised by Hachoir core
# FIXME: Add EnvironmentError (IOError or OSError) and AssertionError?
# FIXME: Remove ArithmeticError and RuntimeError?
HACHOIR_ERRORS = (HachoirError, LookupError, NameError, AttributeError,
    TypeError, ValueError, ArithmeticError, RuntimeError)

info    = log.info
warning = log.warning
error   = log.error
