"""Smart Fitness Session Analyzer: a file-based analysis package.

The package reads participant profiles and session measurements from CSV
files, rejects records it cannot trust, analyses what remains and writes
three report files.

Module map, in the order data flows through them:

``errors``      the exception types the package raises
``validation``  identifier patterns, type conversion and range checks
``models``      the domain objects Participant, Observation and Session
``loading``     reads CSV files and turns rows into domain objects
``analysis``    standalone calculations on lists of numbers
``rules``       the classification rule hierarchy
``analyzer``    applies the rules and builds the result dictionary
``reporting``   writes the console text and the three output files
``cli``         command line handling and the completion summary
"""

__all__ = ["errors", "validation", "models", "loading", "analysis",
           "rules", "analyzer", "reporting", "cli"]
