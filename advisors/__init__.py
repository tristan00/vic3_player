from .random_picker import RandomAdvisor
from .random_smac_weighting import RandomSmacWeightingAdvisor

ADVISORS={advisor.name:advisor for advisor in (RandomAdvisor,RandomSmacWeightingAdvisor)}
