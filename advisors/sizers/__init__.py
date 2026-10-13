from .random import RandomSizer
from .catboost import CatBoostSizer

SIZERS={sizer.name:sizer for sizer in (RandomSizer,CatBoostSizer)}
