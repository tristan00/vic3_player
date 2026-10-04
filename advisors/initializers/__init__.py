from .random import RandomAdvisor
from .smac import RandomSmacWeightingAdvisor
from .svr import RandomSvrWeightingAdvisor

ADVISORS={advisor.name:advisor for advisor in (RandomAdvisor,RandomSmacWeightingAdvisor,RandomSvrWeightingAdvisor)}
