"""Job Discovery — daily fan-out fetcher across public ATS feeds + CSE.

Pipeline:
    RawPosting -> Normalizer -> H1BFilter -> Deduper -> Persister
"""
