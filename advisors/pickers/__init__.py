from .first import PickFirst
from .catboost import CatBoostPicker
from .piecewise import CatBoostPiecewisePicker

PICKERS={picker.name:picker for picker in (PickFirst,CatBoostPicker,CatBoostPiecewisePicker)}
