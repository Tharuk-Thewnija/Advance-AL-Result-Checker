"""Compatibility import for the isolated comparison launcher."""
import sys
from al_results.nonecap import collector as implementation
sys.modules[__name__] = implementation
