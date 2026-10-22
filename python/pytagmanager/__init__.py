from pytagmanager.discovery.crawl import crawl_site
from pytagmanager.export.gtm import build_gtm_container, export_gtm_json
from pytagmanager.intent.base import IntentClassifier, IntentResult, PageContext
from pytagmanager.intent.ollama_classifier import OllamaIntentClassifier
from pytagmanager.recommend.heuristics import recommend_for_graph
from pytagmanager.recommend.models import TrackingRecommendation

__version__ = "0.6.0"

__all__ = [
    "crawl_site",
    "recommend_for_graph",
    "TrackingRecommendation",
    "build_gtm_container",
    "export_gtm_json",
    "IntentClassifier",
    "IntentResult",
    "PageContext",
    "OllamaIntentClassifier",
]
