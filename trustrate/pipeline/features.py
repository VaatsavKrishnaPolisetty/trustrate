"""Ten causal features, returned in caller order; learned statistics are frozen."""
from __future__ import annotations

from collections import Counter
import math
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from .data import float_timestamp

FEATURE_NAMES = [
    "reviews_per_ip_1h", "reviews_per_ip_24h", "accounts_per_ip_24h",
    "account_burst_10m", "product_burst_ratio", "rating_deviation",
    "text_max_similarity", "text_len_z", "account_age_log", "ua_rarity",
]
IDENTITY_FIELDS = ("id", "product_id", "user_id", "ip_hash", "ip_prefix", "user_agent")
REASON_DETAILS = {
    "reviews_per_ip_1h": ("IP_REVIEWS_1H", "Reviews from this IP in the preceding hour"),
    "reviews_per_ip_24h": ("IP_REVIEWS_24H", "Reviews from this IP in the preceding 24 hours"),
    "accounts_per_ip_24h": ("IP_ACCOUNTS_24H", "Distinct accounts using this IP in the preceding 24 hours"),
    "account_burst_10m": ("ACCOUNT_REVIEWS_10M", "Reviews by this account in the preceding 10 minutes"),
    "product_burst_ratio": ("PRODUCT_RATE_RATIO", "Product's last-30-minute rate relative to its preceding 23.5-hour baseline"),
    "rating_deviation": ("RATING_DEVIATION", "Absolute rating difference from the earlier product average"),
    "text_max_similarity": ("PRODUCT_TEXT_SIMILARITY", "Maximum text similarity to strictly earlier reviews of this product"),
    "text_len_z": ("TEXT_LENGTH_Z", "Text length deviation from genuine training, in standard deviations"),
    "account_age_log": ("ACCOUNT_AGE_LOG_HOURS", "Natural log of one plus account age in hours"),
    "ua_rarity": ("USER_AGENT_RARITY", "Negative log of this user agent's genuine-training frequency"),
}


def preprocess_features(X):
    """Copy raw features and log1p F1–F5 before any learned standardization."""
    X = np.asarray(X, dtype=float)
    if X.ndim != 2 or X.shape[1] != len(FEATURE_NAMES) or not np.isfinite(X).all():
        raise ValueError("Expected a finite n-by-10 feature matrix")
    if (X[:, :5] < 0).any():
        raise ValueError("F1–F5 counts/rate ratio must be nonnegative")
    transformed = X.copy()
    transformed[:, :5] = np.log1p(transformed[:, :5])
    return transformed


def validate_review(row):
    for field in IDENTITY_FIELDS:
        if not isinstance(row.get(field), (str, int)) or isinstance(row.get(field), bool) or not str(row[field]).strip():
            raise ValueError(f"{field} is required and must be a nonempty identifier")
    if not isinstance(row.get("body"), str) or not row["body"].strip() or len(row["body"]) > 20000:
        raise ValueError("body must contain 1–20000 characters")
    rating = row.get("rating")
    if isinstance(rating, bool) or not isinstance(rating, (int, float)) or not math.isfinite(rating) or not 1 <= rating <= 5:
        raise ValueError("rating must be finite and between 1 and 5")
    if not isinstance(row.get("revision"), int) or isinstance(row["revision"], bool) or row["revision"] < 1:
        raise ValueError("revision must be a positive integer")
    created = float_timestamp(row.get("created_at"))
    account = float_timestamp(row.get("account_created"))
    if not math.isfinite(created) or not math.isfinite(account) or account > created:
        raise ValueError("Timestamps must be finite and account_created <= created_at")
    return row


class FeatureExtractor:
    def fit(self, genuine_train):
        if not genuine_train:
            raise ValueError("Genuine training rows are required")
        for row in genuine_train:
            validate_review(row)
            if row.get("true_label") != 0 or row.get("split") != "train":
                raise ValueError("Feature transforms may only fit genuine training rows")
        self.vectorizer = TfidfVectorizer(lowercase=True, ngram_range=(1, 2), max_features=5000,
                                          token_pattern=r"(?u)\b\w+\b")
        self.vectorizer.fit([r["body"] for r in genuine_train])
        lengths = np.array([len(r["body"]) for r in genuine_train], dtype=float)
        self.length_mean = float(lengths.mean())
        self.length_std = max(float(lengths.std()), 1.0)
        self.rating_mean = float(np.mean([r["rating"] for r in genuine_train]))
        counts = Counter(r["user_agent"] for r in genuine_train)
        self.ua_probabilities = {ua: (n + 1) / (len(genuine_train) + len(counts) + 1) for ua, n in counts.items()}
        self.unseen_ua_probability = 1 / (len(genuine_train) + len(counts) + 1)
        self.fit_ids = tuple(r["id"] for r in genuine_train)
        return self

    def transform(self, rows, history=()):
        """History plus earlier batch rows are context, never equal/future rows.

        The current review ID (including any old revision) is excluded. Duplicate
        context IDs are rejected: callers should supply their current snapshot.
        """
        rows, history = list(rows), list(history)
        if not rows:
            return np.empty((0, len(FEATURE_NAMES)))
        by_id = {}
        for row in history:
            validate_review(row)
            rid = str(row["id"])
            if rid in by_id:
                raise ValueError("Duplicate history review IDs")
            by_id[rid] = row
        query_ids = set()
        for row in rows:
            validate_review(row)
            rid = str(row["id"])
            if rid in query_ids:
                raise ValueError("Duplicate query review IDs")
            query_ids.add(rid)
            by_id[rid] = row
        context = list(by_id.values())
        times = np.array([float_timestamp(r["created_at"]) for r in context])
        ids = np.array([str(r["id"]) for r in context])
        ips = np.array([r["ip_hash"] for r in context])
        users = np.array([r["user_id"] for r in context])
        products = np.array([r["product_id"] for r in context])
        ratings = np.array([r["rating"] for r in context], dtype=float)
        vectors = self.vectorizer.transform([r["body"] for r in context])
        query_vectors = self.vectorizer.transform([r["body"] for r in rows])
        out = []
        for i, row in enumerate(rows):
            now = float_timestamp(row["created_at"])
            delta = now - times
            past = (delta > 0) & (ids != str(row["id"]))
            day = past & (delta <= 86400)
            hour = past & (delta <= 3600)
            ten = past & (delta <= 600)
            ip_day = day & (ips == row["ip_hash"])
            product = products == row["product_id"]
            recent = past & (delta <= 1800)
            baseline = day & (delta > 1800)
            # Disjoint windows: recent 0.5h vs preceding 23.5h. A one-event
            # pseudocount per half-hour bucket gives both rates the same prior.
            recent_rate = (np.count_nonzero(recent & product) + 1) / .5
            baseline_rate = (np.count_nonzero(baseline & product) + 47) / 23.5
            product_ratio = recent_rate / baseline_rate
            product_history = past & product
            mean_rating = float(ratings[product_history].mean()) if product_history.any() else self.rating_mean
            similarity = float((vectors[product_history] @ query_vectors[i].T).max()) if product_history.any() else 0.0
            age_hours = (now - float_timestamp(row["account_created"])) / 3600
            out.append([
                np.count_nonzero(hour & (ips == row["ip_hash"])), np.count_nonzero(ip_day),
                len(set(users[ip_day])), np.count_nonzero(ten & (users == row["user_id"])),
                product_ratio, abs(row["rating"] - mean_rating), similarity,
                (len(row["body"]) - self.length_mean) / self.length_std, math.log1p(age_hours),
                -math.log(self.ua_probabilities.get(row["user_agent"], self.unseen_ua_probability)),
            ])
        return np.asarray(out, dtype=float)


def extract_features(rows, extractor=None, history=()):
    """Explicit fitted extractor prevents accidental fitting on evaluation rows."""
    if extractor is None:
        raise ValueError("Pass a FeatureExtractor fitted on genuine training rows")
    return extractor.transform(rows, history)
