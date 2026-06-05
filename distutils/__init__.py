"""Compatibility shim for Python 3.12+.

Flask-Moment 0.9.0 imports distutils.version.StrictVersion, but distutils was
removed from the Python stdlib in 3.12. This package provides the minimal
module path the dependency expects.
"""

