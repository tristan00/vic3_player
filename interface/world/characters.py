import re

from ..common import timed
from ..script import blocks,body,clean,scalar,script_files


@timed
def scripts(game,files):
    choices=[]
    for path in script_files(game,'common/ideologies'):
        text=files.get(path.relative_to(game).as_posix())
        for name,record in blocks(clean(path) if text is None else text):
            if scalar(record,'character_ideology')!='yes' or name=='ideology_child':
                continue
            gates=dict(blocks(body(record)))
            country=body(gates['country_trigger']) if 'country_trigger' in gates else ''
            character=body(gates['non_interest_group_leader_trigger']) if 'non_interest_group_leader_trigger' in gates else ''
            character=re.sub(r'\broot\b','scope:interface_ideology_character',character)
            choices.append(f'1 = {{ trigger = {{ owner = {{ {country} }} {character} }} set_ideology = ideology:{name} }}')
    effect=('interface_uniform_ideology = { if = { limit = { is_adult = yes exists = owner '
            'owner = { has_variable = interface_random_ideology_share } NOT = { has_variable = interface_ideology_sampled } } '
            'set_variable = interface_ideology_sampled save_scope_as = interface_ideology_character '
            'random = { chance = owner.var:interface_random_ideology_share random_list = { '+'\n'.join(choices)+' } } } }')
    files['common/scripted_effects/interface_ideologies.txt']=effect
    path=game/'common/on_actions/00_code_on_actions.txt'
    name=path.relative_to(game).as_posix()
    text=files.get(name,clean(path))
    for key,record in list(blocks(text)):
        if key in ('on_character_creation','on_character_became_adult','on_character_spawned_in_pool','on_character_recruitment'):
            text=text.replace(record,re.sub(r'\beffect\s*=\s*\{','effect = { interface_uniform_ideology = yes ',record,count=1),1)
        elif key in ('on_game_started','on_game_started_after_lobby'):
            text=text.replace(record,re.sub(r'\beffect\s*=\s*\{','effect = { every_character = { interface_uniform_ideology = yes } } ',record,count=1),1)
    files[name]=text
    files['common/scripted_guis/interface_ideologies.txt']='interface_uniform_character = { scope = character effect = { interface_uniform_ideology = yes } }'
    path='gui/generate_character.gui'
    text=files.get(path) or clean(game/path)
    anchor='datacontext = "[Character.GetCountry]"'
    if text.count(anchor)!=1:
        raise ValueError('Character offer layout changed')
    widget=('widget = { size = { 0 0 } state = { name = interface_uniform_offer trigger_on_create = yes duration = 0.01 '
            'on_finish = "[GetScriptedGui(\'interface_uniform_character\').Execute(GuiScope.SetRoot(Character.MakeScope).End)]" } }')
    files[path]=text.replace(anchor,anchor+'\n'+widget,1)
    path='gui/ingame_hud.gui'
    text=files.get(path) or clean(game/path)
    anchor='name = "ingame_hud"'
    if text.count(anchor)!=1:
        raise ValueError('In-game HUD layout changed')
    offers='\n'.join(f'flowcontainer = {{ datamodel = "[AccessPlayer.Access{kind}Offer]" item = {{ {widget} }} }}'
                     for kind in ('Generals','Admirals'))
    files[path]=text.replace(anchor,anchor+'\n'+offers,1)
