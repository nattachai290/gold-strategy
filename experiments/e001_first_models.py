"""R001 batch: first honest look. Four trials, fixed before any market result was seen.
Long-only spot: each model's P(up) > 0.5 -> long, else flat (goldml.evaluate.default_position).

E001a  logistic, price features, next-day direction (h=1)
E001b  logistic, price features, 5-day direction, overlapping book (h=5)
E002a  LightGBM, price+macro features, 5-day direction (h=5)
E002b  LightGBM, price+macro features, 20-day direction (h=20)
"""
from lightgbm import LGBMClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from goldml.evaluate import Experiment
from goldml.features import FEATURE_SETS


def logit():
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=1000))


def lgbm():
    return LGBMClassifier(n_estimators=300, learning_rate=0.02, num_leaves=7, min_child_samples=200,
                          subsample=0.7, subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0,
                          random_state=0, n_jobs=1, verbose=-1)


EXPERIMENTS = [
    Experiment("E001a_logit_price_h1", FEATURE_SETS["price"], horizon=1, make_model=logit,
               params={"C": 0.1}, description="logistic, price features, h=1"),
    Experiment("E001b_logit_price_h5", FEATURE_SETS["price"], horizon=5, make_model=logit,
               params={"C": 0.1}, description="logistic, price features, h=5, overlapping book"),
    Experiment("E002a_lgbm_pricemacro_h5", FEATURE_SETS["price_macro"], horizon=5, make_model=lgbm,
               params={"leaves": 7, "n": 300}, description="LightGBM, price+macro, h=5"),
    Experiment("E002b_lgbm_pricemacro_h20", FEATURE_SETS["price_macro"], horizon=20, make_model=lgbm,
               params={"leaves": 7, "n": 300}, description="LightGBM, price+macro, h=20"),
]
