from .random import RandomAdvisor
from .forest import RandomForestWeightingAdvisor
from .svr import RandomSvrWeightingAdvisor

ADVISORS={advisor.name:advisor for advisor in (RandomAdvisor,RandomForestWeightingAdvisor,RandomSvrWeightingAdvisor)}
