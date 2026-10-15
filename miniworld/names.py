from . import timed, timed_often

ONSETS=('b','br','c','ch','d','dr','f','g','gr','h','k','l','m','n','p','r','s','st','t','tr','v','z','')
VOWELS=('a','e','i','o','u','ae','ia','ou')
CODAS=('','n','r','l','s','m','th','nd','rk')


@timed_often
def name(rng,taken):
    while True:
        text=''.join(rng.choice(ONSETS)+rng.choice(VOWELS)+rng.choice(CODAS) for _ in range(rng.integers(2,4))).capitalize()
        if 4<=len(text)<=12 and text not in taken:
            taken.add(text)
            return text


@timed
def label(rng,world):
    taken=set()
    labels={f'STATE_MW_{index+1}':name(rng,taken) for index in range(len(world.states))}
    labels.update({f'STATE_MW_SEA_{index+1}':name(rng,taken)+' Sea' for index in range(len(world.seas))})
    labels.update({f'region_mw_{index+1}':name(rng,taken) for index in range(len(world.regions))})
    labels.update({f'region_mw_sea_{index+1}':labels[f'STATE_MW_SEA_{index+1}'] for index in range(len(world.seas))})
    return labels,[[int(c) for c in rng.integers(40,255,3)] for _ in world.regions]
