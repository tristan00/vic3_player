from .random_picker import RandomAdvisor
from .random_smac_weighting import RandomSmacWeightingAdvisor
from .random_svr_weighting import RandomSvrWeightingAdvisor

ADVISORS={advisor.name:advisor for advisor in (RandomAdvisor,RandomSmacWeightingAdvisor,RandomSvrWeightingAdvisor)}
