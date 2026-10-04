import itertools


from ..common import timed_often


ONSETS=['b','c','d','f','g','h','j','k','l','m','n','p','r','s','t','v','w','z','br','dr','gr','kr','tr','st','sh','th','ch','vl','sk','pr']


VOWELS=['a','e','i','o','u','ai','ei','ou','ia','y','ae','io']


CODAS=['','','','n','r','l','s','m','th','rd','nd','sk','x','k','t']


ENDINGS=['ia','an','or','ar','en','is','ad','um','ea','ost']


GENERIC={'onsets':ONSETS,'vowels':VOWELS,'codas':CODAS,'endings':ENDINGS}


@timed_often
def word(rng,used=None,phonology=GENERIC,syllables=(2,3),ending=True):
    while True:
        text=''.join(rng.choice(phonology['onsets'])+rng.choice(phonology['vowels'])+rng.choice(phonology['codas']) for _ in range(rng.randint(*syllables)))
        text=(text+rng.choice(phonology['endings']) if ending else text).capitalize()
        if used is None or text not in used:
            if used is not None:
                used.add(text)
            return text


@timed_often
def _rgb(rng):
    return ' '.join(str(rng.randrange(40,230)) for _ in range(3))


@timed_often
def _tags(count,taken):
    letters='ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    tags=[t for t in ('X'+a+b for a,b in itertools.product(letters,repeat=2)) if t not in taken]
    if count>len(tags):
        raise ValueError(f'At most {len(tags)} countries are supported')
    return tags[:count]


@timed_often
def level(value,low,mean,top):
    return low+2*value*(mean-low) if value<=.5 else mean+(value-.5)*2*(top-mean)


@timed_often
def _techs(rng,base,count,requires,required=frozenset()):
    if len(required)>count:
        raise ValueError('Technology count cannot support the required starting army')
    techs=set(base)|set(required)
    while len(techs)<count:
        reachable=sorted(tech for tech,needs in requires.items() if tech not in techs and needs<=techs)
        if not reachable:
            raise ValueError(f'Only {len(techs)} technologies are reachable, {count} requested')
        techs.add(rng.choice(reachable))
    while len(techs)>count:
        techs.remove(rng.choice(sorted(tech for tech in techs-required if not any(tech in requires.get(other,()) for other in techs))))
    return techs
