from dataclasses import dataclass


TYPES={
    'building':(8,'Building',None),
    'combat_unit':(14,'CombatUnit',None),
    'building_type':(9,'BuildingType','common/buildings'),
    'character':(11,'Character',None),
    'combat_unit_type':(15,'CombatUnitType','common/combat_unit_types'),
    'commander_order_type':(16,'CommanderOrderType','common/commander_orders'),
    'company':(17,'Company',None),
    'company_type':(18,'CompanyType','common/company_types'),
    'country':(5,'Country',None),
    'country_definition':(20,'CountryDefinition','common/country_definitions'),
    'diplomatic_play':(28,'DiplomaticPlay',None),
    'diplomatic_play_type':(29,'DiplomaticPlayType','common/diplomatic_plays'),
    'goods':(38,'Goods','common/goods'),
    'institution':(41,'Institution',None),
    'interest_group':(44,'InterestGroup',None),
    'journal_entry':(48,'JournalEntry',None),
    'law':(49,'Law',None),
    'military_formation':(53,'MilitaryFormation',None),
    'mobilization_option':(92,'MobilizationOption','common/mobilization_options'),
    'naval_mission_type':(56,'NavalMissionType','common/naval_mission_types'),
    'political_movement':(60,'PoliticalMovement',None),
    'power_bloc':(65,'PowerBloc',None),
    'power_bloc_principle':(67,'PowerBlocPrinciple','common/power_bloc_principles'),
    'ship':(71,'Ship',None),
    'ship_type':(74,'ShipType','common/ship_types'),
    'amendment':(105,'Amendment',None),
    'state':(76,'State',None),
    'state_region':(78,'StateRegion',None),
    'strait':(80,'Strait',None),
    'strategic_region':(82,'StrategicRegion','common/strategic_regions'),
    'technology':(84,'Technology','common/technology/technologies'),
    'treaty':(101,'Treaty',None),
    'war':(91,'War',None),
    'war_goal_type':(103,'WarGoalType','common/war_goal_types'),
}


KEYS={
    'decree':'common/decrees',
    'diplomatic_action':'common/diplomatic_actions',
    'interaction':'common/character_interactions',
    'production_method':'common/production_methods',
    'decision':'common/decisions',
    'charter':'common/company_charter_types',
    'power_bloc_identity':'common/power_bloc_identities',
    'ship_modification':'common/ship_modifications',
    'treaty_article':'common/treaty_articles',
}


LISTED=.5
LEVELS=('VeryLow','Low','Medium','High','VeryHigh')
TOLL_LEVELS=('NoTolls','LowTolls','MediumTolls','HighTolls')
ACCESS_STATUSES=('Open','NoMilitary','Closed')
ACCESS_PERMISSIONS=('NoEnemies','OnlyAllies','OnlyController')


def action_folders():
    return {**{kind:folder for kind,(_,_,folder) in TYPES.items() if folder},**KEYS}


@dataclass(frozen=True)
class Action:
    name: str
    params: tuple
    command: str
    datamodels: tuple=()
    context: str=''
    valid: str=''
    choices: tuple=()
    alternatives: tuple=()
    window: tuple=()
    start: tuple=()
    why: str=''
    stages: tuple=()
    cleanup: tuple=()
    transport: bool=False
    overseas: tuple=()
    absent: tuple=()
    admit: str=''
    prepare: tuple=()
    reason: str=''
    deadline: float=0


FORMATION=tuple(((f'AccessPlayer.GetMilitaryFormations{kind}','ObjectsEqual(MilitaryFormation.Self, {military_formation}.Self)'),) for kind in ('Army','Fleet'))


MAP_LIST=('gui/map_list_panel.gui','onclick = "[MapListOption.OnClick]"')


SELECTED_STATE='EqualTo_string(ToString_uint64(MapListOption.GetSelectionIndex), ToString_int32({state}.GetID))'


BROWSER=('gui/building_browser_panel.gui','name = "building_browser_panel"')


OWNERSHIP=('any','owned_national','owned_private','owned_foreign','owned_company')


def browser_filters(values):
    states=['BuildingBrowserPanel.StateFilterHideAllStates'] if 'state' in values else ['BuildingBrowserPanel.StateFilterShowAllStates']
    owners=[f"BuildingBrowserPanel.SetFilterMode('{kind}', '{'yes' if kind==values['ownership'] else 'off'}')" for kind in OWNERSHIP[1:]]
    return ['BuildingBrowserPanel.ResetAllFilters',*states,*owners]


STATE_FILTER=(BROWSER,(('BuildingBrowserPanel.GetAllStates','ObjectsEqual(State.Self, {state}.Self)'),),lambda values:['BuildingBrowserPanel.StateFilterToggleShown(State.AccessSelf)'])


def filter_stages(params):
    return ((BROWSER,(),browser_filters),)+((STATE_FILTER,) if 'state' in params.split() else ())


TYPE_ITEM=('BuildingBrowserPanel.GetBuildingBrowserBuildingTypeItems','EqualTo_string(BuildingBrowserBuildingTypeItem.GetBuildingType.GetKey, {building_type}.GetKey)')


OPEN_BROWSER=(('InformationPanelBar.OpenBuildingBrowserPanel(GetPlayer.Self)',),((),))


PM_MENU=('gui/switch_production_method_menu.gui','name = "switch_production_method_menu"')


SUBSET=(('subsidies_on','ToggleSubsidiesOn'),('subsidies_off','ToggleSubsidiesOff'))


def subset(name,command,params):
    return Action(name,tuple(params.split()),'Building.'+command,
                  datamodels=(('BuildingBrowserPanel.GetSortedAndFilteredBuildings','And(EqualTo_string(Building.GetBuildingType.GetKey, {building_type}.GetKey), ObjectsEqual(Building.GetState.GetOwner.Self, GetPlayer.Self))'),),
                  choices=OWNERSHIP,window=BROWSER,start=OPEN_BROWSER,stages=filter_stages(params),deadline=LISTED)


NATIONALIZE_WINDOW=('gui/popups.gui','name = "nationalize_building_window"')
TRANSPORT_PLANNER=('gui/transport_planner.gui','name = "transport_planner_popup"')


COMPENSATED='NationalizeBuildingWindow.WillGiveCompensation'


def bulk_nationalize(name,params,compensated=True):
    return Action(name,tuple(params.split()),'NationalizeBuildingWindow.NationalizeBuildingGroupsConfirm',
                  valid=f'And(NationalizeBuildingWindow.NationalizeBuildingGroupsIsValid, {COMPENSATED if compensated else f"Not({COMPENSATED})"})',
                  why='NationalizeBuildingWindow.NationalizeBuildingGroupsGetDesc',
                  datamodels=(('',"Not(EqualTo_int32(NationalizeBuildingWindow.GetNumLevelsToNationalize, '(int32)0'))"),),
                  choices=OWNERSHIP,window=NATIONALIZE_WINDOW,deadline=LISTED,cleanup=('PopupManager.HideNationalizeBuildingWindow','InformationPanelBar.ClosePanel','RightClickMenuManager.Close'),start=(('PopupManager.HideNationalizeBuildingWindow',*OPEN_BROWSER[0]),((),)),
                  stages=(*filter_stages(params),(BROWSER,(TYPE_ITEM,),lambda values:['BuildingBrowserBuildingTypeItem.ShowNationalizeBuildingsWindow']),
                          (NATIONALIZE_WINDOW,(('','NationalizeBuildingWindow.HasNationalizableGroup'),),
                           lambda values:['NationalizeBuildingWindow.SetNationalizeToAll',*([] if compensated else ['NationalizeBuildingWindow.ToggleGiveCompensation'])])))


def bulk_method(name,params):
    menu=(TYPE_ITEM,('BuildingBrowserBuildingTypeItem.GetBuildingType.AccessProductionMethodGroups',''),
          ('ProductionMethodGroup.AccessCountryProductionMethods(GetPlayer.Self)','EqualTo_string(ProductionMethod.GetKey, {production_method})'))
    return Action(name,tuple(params.split()),'ChangeProductionMethodMenuItem.Execute',valid='ChangeProductionMethodMenuItem.IsValid',
                  datamodels=(('ChangeProductionMethodsMenuItems.AccessItems','EqualTo_string(ChangeProductionMethodMenuItem.AccessMethod.GetKey, {production_method})'),),
                  choices=OWNERSHIP,window=PM_MENU,start=OPEN_BROWSER,deadline=LISTED,
                  stages=(*filter_stages(params),
                          (BROWSER,menu,lambda values:['BuildingBrowserBuildingTypeItem.ToggleSwitchProductionMethodMenu(ProductionMethodGroup.AccessSelf, PdxGuiWidget.AccessSelf)'])))


MILITARY_PANEL=('gui/panel_military.gui','name = "panel_military"')
OPEN_MILITARY=(("InformationPanelBar.OpenMilitaryPanelTab('army')",),((),))


TRANSFER=('gui/transfer_formation.gui','name = "transfer_formation_popup"')
TARGET_ARMY=(('AccessPlayer.GetMilitaryFormationsArmy','ObjectsEqual(MilitaryFormation.Self, {target}.Self)'),)
TARGET_FLEET=(('AccessPlayer.GetMilitaryFormationsFleet','ObjectsEqual(MilitaryFormation.Self, {target}.Self)'),)
SHOW_TRANSFER=('PopupManager.ShowTransferFormation(MilitaryFormation.AccessSelf)',)
SET_LEFT='TransferFormationPopup.SetSelectedLeftFormation(MilitaryFormation.AccessSelf)'
SET_RIGHT='TransferFormationPopup.SetSelectedRightFormation(MilitaryFormation.AccessSelf)'
NEW_RIGHT='TransferFormationPopup.DeselectRightFormation'
HALF="TransferFormationPopup.MovePercentageRight('(int32)50')"
STAGED_SHIP=(('@TransferFormationPopup.GetLeftStagedFormation',''),('StagedFormation.GetShipTypes',''),('StagedShipsWithType.GetShips','ObjectsEqual(Ship.Self, {ship}.Self)'))
OWN_SHIP=(('AccessPlayer.GetMilitaryFormationsFleet',''),('GetShipGroups',''),
          ('MilitaryFormation.GetShipList.GetFilterOfGroup(ShipGroup.Self).GetShipsFiltered','ObjectsEqual(Ship.Self, {ship}.Self)'))
FORMATION_PANEL=('gui/military_formation_panel.gui','name = "military_formation_panel"')
OPEN_NAVY=(("InformationPanelBar.OpenMilitaryPanelTab('navy')",),((),))
MERGE_WHY="Concatenate(' selected formations: ', ToString_int32(GetNumSelectedFormations))"
NAVAL_REGION='ObjectsEqual(MapListOption.GetNavalMissionData.GetSeaRegion.GetStateRegion.GetStrategicRegion.Self, {strategic_region}.Self)'
HQ_REGION='ObjectsEqual(MapListOption.GetDestinationData.GetHQ.GetStrategicRegion.Self, {strategic_region}.Self)'


def transfer(name,params,side,chain,stages):
    return Action(name,tuple(params.split()),'TransferFormationPopup.Confirm',window=TRANSFER,start=(SHOW_TRANSFER,(chain,)),cleanup=('PopupManager.HideTransferFormation',),deadline=LISTED,
                  stages=((TRANSFER,chain,lambda values:[SET_LEFT,*side]),*((TRANSFER,inner,lambda values,calls=calls:list(calls)) for inner,calls in stages)))


def merge(name,select,listing):
    return Action(name,('military_formation','source:military_formation'),'MergeSelectedFormations',window=FORMATION_PANEL,start=select,why=MERGE_WHY,deadline=LISTED,
                  stages=((FORMATION_PANEL,((listing,'ObjectsEqual(MilitaryFormation.Self, {source}.Self)'),),lambda values:['MilitaryFormation.Select']),))


SELECT_ARMY=(("InformationPanelBar.OpenMilitaryFormationPanelTab(MilitaryFormation.Self, 'default')",'MilitaryFormation.Select'),FORMATION[:1])
SELECTION="Concatenate(' selected armies: ', ToString_int32(GetNumSelectedArmies))"
SELECT_FLEET=(("InformationPanelBar.OpenMilitaryFormationPanelTab(MilitaryFormation.Self, 'default')",'MilitaryFormation.Select'),FORMATION[1:])
FLEET_SELECTION="Concatenate(' selected fleets: ', ToString_int32(GetNumSelectedFleets))"


def selected(name,params,command):
    return Action(name,tuple(params.split()),command,start=SELECT_ARMY,why=SELECTION)




OPEN_SHIPS=(("InformationPanelBar.OpenConstructionPanelTab(GetPlayer.Self, 'ships')",),((),))
SHIP_PAGES=('gui/construction_panel.gui','name = "ship_construction_queue_pages"')
SHIP_PAGE=12


DIPLOMATIC_WINDOW=('gui/popups.gui','name = "diplomatic_action_window"')
OPEN_ACTION=(('GetCountryDiplomaticAction({diplomatic_action}, GetPlayer.Self, {country}.Self).ExecuteWithConfirmation',),((),))
NO_STATES='And(DiplomaticActionWindow.HasStateSelectionTarget, IsDataModelEmpty(DiplomaticActionWindow.AccessPossibleStates))'
PICK_STATE=['DiplomaticActionWindow.SelectState(State.Self)','DiplomaticActionWindow.ClearStateSelectionTarget']
OBLIGATIONS=('None','CallInObligation','OweObligation')


def state_target(side,clear=()):
    return (DIPLOMATIC_WINDOW,(),lambda values:[*clear,f'DiplomaticActionWindow.SetStateSelectionTarget(DiplomaticActionWindow.GetDiplomaticAction.Get{side}Country)'])


UNPICK=('DiplomaticActionWindow.ClearFirstState','DiplomaticActionWindow.ClearSecondState')


def state_pick(param):
    return (DIPLOMATIC_WINDOW,(('DiplomaticActionWindow.AccessPossibleStates','ObjectsEqual(State.Self, {'+param+'}.Self)'),),lambda values:PICK_STATE)


def owed(values):
    return [] if values['obligation']=='None' else ['DiplomaticActionWindow.Toggle{obligation}']


def state_action(name,side):
    return Action(name,('country','diplomatic_action','state','obligation:choice'),'DiplomaticActionWindow.ExecuteAction',choices=OBLIGATIONS,
                  window=DIPLOMATIC_WINDOW,cleanup=('PopupManager.HideDiplomaticActionConfirmation',),start=OPEN_ACTION,absent=((0,NO_STATES),),deadline=LISTED,
                  stages=(state_target(side,UNPICK),state_pick('state'),(DIPLOMATIC_WINDOW,(),owed)))


def map_list(name,params,target,start,transport=False,chains=FORMATION[:1],deadline=0):
    return Action(name,tuple(params.split()),'MapListOption.OnClick',datamodels=(('',target),),valid='MapListOption.CanClick',why='MapListOption.GetTooltip',window=MAP_LIST,
                  start=((start,'MapListPanelManager.OpenCurrentPanel'),chains),transport=transport,deadline=deadline)


def lens(name):
    return Action(name,('state',),'MapListOption.OnClick',datamodels=(('',SELECTED_STATE),),valid='MapListOption.CanClick',why='MapListOption.GetTooltip',window=MAP_LIST,
                  start=((f"GetLensToolbar.ActivateOption('{name}_lens_option')",'MapListPanelManager.OpenCurrentPanel'),((),)),deadline=LISTED)


CHARTER=(('AccessPlayer.GetCompanies','ObjectsEqual(Company.Self, {company}.Self)'),
         ('GetCompanyCharterTypes','EqualTo_string(CompanyCharterType.GetNameNoFormatting, GetCompanyCharterType({charter}).GetNameNoFormatting)'))


EVENT_WINDOW=('gui/eventwindow.gui','datamodel = "[EventWindow.GetOptions]"')


PROPOSALS=('gui/topfrontend.gui','datamodel = "[TopFrontend.AccessProposals]"')
ADD_WAR_GOAL=('gui/add_wargoal_panel.gui','datamodel = "[AddWarGoalPanel.AccessShownWarGoals]"')
ADD_WAR_GOAL_PANEL=('gui/add_wargoal_panel.gui','name = "add_wargoal_panel"')
BLOC_FORMATION=('gui/power_bloc_formation_panel.gui','name = "power_bloc_formation_panel"')
PRINCIPLE_WINDOW=('gui/principle_selection_window.gui','name = "principle_selection_window"')
BLOC_PANEL=('gui/power_bloc_panel.gui','name = "power_bloc_panel"')
POLITICS=('gui/politics_panel.gui','name = "politics_panel"')
REFORM=('@PoliticsPanel.AccessReformGovernment','')
PLAY_CONFIRMATION=('gui/popups.gui','name = "diplomatic_play_confirmation"')
DESIGNER=('gui/ship_designer_popup.gui','name = ship_designer_popup')
TEMPLATE_ITEM=(('ShipTemplateList.GetTemplatesOfType({ship_type}.Self)','EqualTo_int32(PdxGuiWidget.AccessParent.GetIndexInDataModel, {index})'),)


EMBARK_FLEETS=('gui/right_click_menu.gui','datamodel = "[MilitaryFormationWrapped.GetFleetsSortedByMarineCapacity]"')
INVASION_PLANNER=('gui/invasion_planner.gui','name = "invasion_planner_popup"')
INVADING_ARMY=(('AccessPlayer.GetMilitaryFormationsArmy','ObjectsEqual(MilitaryFormation.Self, {military_formation}.Self)'),)
INVADING_FLEET=(('InvasionPlannerPopup.GetSortedFleets','ObjectsEqual(MilitaryFormation.Self, {fleet}.Self)'),)
SWAY_PANEL=('gui/sway_country_panel.gui','name = "sway_country_panel"')
SWAY='SwayCountryPanel.AccessDiplomaticPlay.CreateSway(GetPlayer.Self, SwayCountryPanel.GetCountry, SwayOffer.Self)'


def invasion(name,params,stages):
    return Action(name,tuple(params.split()),'InvasionPlannerPopup.StartInvasion',window=INVASION_PLANNER,
                  start=(('PopupManager.HideInvasionPlannerPopup','PopupManager.ShowInvasionPlannerPopup({state}.Self)'),((),)),cleanup=('PopupManager.HideInvasionPlannerPopup',),
                  stages=tuple((INVASION_PLANNER,chain,lambda values,call=call:[call]) for chain,call in stages))


def principle(name,command='PowerBlocPrincipleSelectionWindow.SubmitPrincipleSelection'):
    return Action(name,('slot:int','power_bloc_principle'),command,window=PRINCIPLE_WINDOW,
                  start=(('InformationPanelBar.OpenPowerBlocPanel(GetPlayer.GetPowerBloc.Self)',),((),)),
                  cleanup=('PopupManager.HidePowerBlocPrincipleSelectionWindow','InformationPanelBar.ClosePanel'),
                  stages=((BLOC_PANEL,(('@PowerBlocPanel.GetPrincipleSlot({slot})',''),),lambda values:['PowerBlocPanel.ToggleSelectionWindow(PowerBlocPrincipleSlot.AccessSelf)']),
                          (PRINCIPLE_WINDOW,(('PowerBlocPrincipleSelectionWindow.GetAvailableGroups',''),('PowerBlocPrincipleGroup.GetLevels','ObjectsEqual(PowerBlocPrinciple.Self, {power_bloc_principle}.Self)')),
                           lambda values:['PowerBlocPrincipleSelectionWindow.TogglePrincipleSelection(PowerBlocPrinciple.Self)'])))


TREATY_DRAFT=('gui/treaty_draft_panel.gui','name = "treaty_draft_panel"')
ARTICLE_CONFIRM=('gui/right_click_menu.gui','onclick = "[TreatyDraft.AddArticleDraft(ArticleDraft.Self)]"')
DRAFT=('@TreatyDraftPanel.GetDraft','')
OPEN_DRAFT=(('InformationPanelBar.OpenTreatyDraftPanelForNewDraft(GetPlayer.Self, {country}.Self)',),((),))
TREATY_SIDES=(('offer','Offers','Left'),('demand','Demands','Right'),('agree','MutualAgreements','Left'))
ARTICLE_MENU="RightClickMenuManager.ToggleArticleTypeInput(TreatyDraft.Self, ArticleType.Self, Country.Self, PdxGuiWidget.AccessSelf, 'article_input_right_click_menu_right')"


ADMITTED="EqualTo_string(GetVariableSystem.Get('interface_admit'), '1')"


ARTICLE='GetArticleType({treaty_article})'


def includable(holder,article=ARTICLE):
    draft='TreatyDraftPanel.GetDraft'
    country=f'{draft}.Get{holder}Country'
    return f'{draft}.CanIncludeArticleType({article}.Self, {country}.Self, {draft}.GetOtherCountry({country}.Self).Self)'


RESET='TreatyDraftPanel.GetDraft.ResetAll'


def available(holder,article=ARTICLE):
    draft='TreatyDraftPanel.GetDraft'
    country=f'{draft}.Get{holder}Country'
    return f'{article}.IsAvailable({country}.Self, {draft}.GetOtherCountry({country}.Self).Self)'


def admissible(holder,article=ARTICLE):
    return f'And({available(holder,article)}, {includable(holder,article)})'


def unfit(holder,article=ARTICLE):
    return (f"Select_CString({available(holder,article)}, {includable(holder,article).replace('CanIncludeArticleType','GetCanIncludeArticleTypeDesc')}, "
            f"{available(holder,article).replace('IsAvailable','GetIsAvailableDesc')})")


def potential(listing,holder):
    return ((DRAFT[0],ADMITTED),(f'@TreatyDraft.Get{holder}Country',''),(f'TreatyDraft.GetPotential{listing}','ArticleType.HasType({treaty_article})'))


def treaty(name,listing,holder):
    return Action(name,('country','treaty_article'),'TreatyDraft.SendProposal',datamodels=(DRAFT,),window=TREATY_DRAFT,start=OPEN_DRAFT,deadline=LISTED,cleanup=(RESET,'InformationPanelBar.ClosePanel'),
                  admit=admissible(holder),prepare=(RESET,),reason=unfit(holder),
                  stages=((TREATY_DRAFT,potential(listing,holder),
                           lambda values:['TreatyDraft.AddArticle(ArticleType.Self, Country.Self, TreatyDraft.GetOtherCountry(Country.Self).Self)']),))


def goods_treaty(name,listing,holder):
    return Action(name,('country','treaty_article','goods'),'TreatyDraft.SendProposal',datamodels=(DRAFT,),window=TREATY_DRAFT,start=OPEN_DRAFT,deadline=LISTED,
                  cleanup=('RightClickMenuManager.Close',RESET,'InformationPanelBar.ClosePanel'),admit=admissible(holder),prepare=(RESET,),reason=unfit(holder),
                  stages=((TREATY_DRAFT,potential(listing,holder),lambda values:[ARTICLE_MENU]),
                          (ARTICLE_CONFIRM,(),lambda values:['ArticleDraft.SetGood({goods}.Self)']),
                          (ARTICLE_CONFIRM,(),lambda values:['TreatyDraft.AddArticleDraft(ArticleDraft.Self)'])))


ADD='TreatyDraft.AddArticle(ArticleType.Self, Country.Self, TreatyDraft.GetOtherCountry(Country.Self).Self)'
VERDICT="GetVariableSystem.Get('interface_verdict')"
JUDGE="GetVariableSystem.Set('interface_verdict', Select_CString(TreatyDraft.CanIncludeArticleDraft(ArticleDraft.Self), '1', '0'))"
EXPLAIN="GetVariableSystem.Set('interface_verdict_desc', TreatyDraft.GetCanIncludeArticleDraftDesc(ArticleDraft.Self))"
EXPLAINED="GetVariableSystem.Get('interface_verdict_desc')"
JUDGED=f"EqualTo_string({VERDICT}, '1')"
UNJUDGED=f"EqualTo_string({VERDICT}, '0')"
FORGET="GetVariableSystem.Clear('interface_verdict')"
SHARES=('0','1','2','3','4')
SHARE=("ArticleDraft.SetQuantity(Add_int32(ArticleDraft.GetMinValidQuantity, Divide_int32(Multiply_int32(Subtract_int32(ArticleDraft.GetMaxValidQuantity, "
       "ArticleDraft.GetMinValidQuantity), '(int32){share}'), '(int32)4')))")
INPUTS={'state':('state',('ArticleDraft.SetState({state}.Self)',)),
        'region':('strategic_region',('ArticleDraft.SetStrategicRegion({strategic_region}.Self)',)),
        'law':('commitment:law',('ArticleDraft.SetLaw({commitment}.GetLawType.Self)',)),
        'subject':('subject:country',('ArticleDraft.SetCountry({subject}.Self)',)),
        'ship':('ship',('ArticleDraft.SetShip({ship}.Self)',)),
        'monopoly':('company building_type',('ArticleDraft.SetCompany({company}.Self)','ArticleDraft.SetBuildingType({building_type}.Self)')),
        'money':('share:choice',(SHARE,)),
        'goods_amount':('goods share:choice',('ArticleDraft.SetGood({goods}.Self)',SHARE))}
LEFT='TreatyDraftPanel.GetDraft.GetLeftCountry.Self'
DAYS=('1825','3650','5475','9125','18250','36135')
PROMISES=('OweObligation','CallInObligation','AskForObligation')
PLAIN=('guarantee_independence','support_independence','take_on_debt','foreign_investment_rights','join_power_bloc','host_power_bloc_embassy','offer_embassy',
       'military_assistance','military_access','transit_rights','trade_privilege','amend_succession','recognize_independence','toll_exemption','no_tolls',
       'strait_access','no_strait_closure','non_piracy_agreement','abandon_piracy')
DEMANDED="GetArticleType('{demand}')"
WANTED=admissible('Right',DEMANDED)
BOTH=('And(Not(IsDataModelEmpty(TreatyDraftPanel.GetDraft.GetSelectedDirectedArticles('+LEFT+'))), '
      'Not(IsDataModelEmpty(TreatyDraftPanel.GetDraft.GetSelectedDirectedArticles(TreatyDraftPanel.GetDraft.GetRightCountry.Self))))')
REDRAFT=(('InformationPanelBar.OpenTreatyDraftPanel({treaty}.Self)',),((),))
NEGOTIABLE='And(Not({treaty}.IsEnforced), And(Not({treaty}.IsThreateningHostilities), Not({treaty}.DoesCallInObligation({treaty}.GetRightCountry.Self))))'


def input_treaty(name,listing,holder,kind):
    params,setters=INPUTS[kind]
    return Action(name,('country','treaty_article',*params.split()),'TreatyDraft.SendProposal',datamodels=(DRAFT,),window=TREATY_DRAFT,start=OPEN_DRAFT,deadline=LISTED,
                  choices=SHARES if 'share:choice' in params.split() else (),cleanup=(FORGET,'RightClickMenuManager.Close',RESET,'InformationPanelBar.ClosePanel'),admit=available(holder),prepare=(RESET,),
                  reason=available(holder).replace('IsAvailable','GetIsAvailableDesc'),
                  absent=((len(setters)+1,UNJUDGED,EXPLAINED),),
                  stages=((TREATY_DRAFT,potential(listing,holder),lambda values:[ARTICLE_MENU]),
                          *((ARTICLE_CONFIRM,(),lambda values,call=call:[call]) for call in setters),
                          (ARTICLE_CONFIRM,(),lambda values:[EXPLAIN,JUDGE]),
                          (ARTICLE_CONFIRM,(('',JUDGED),),lambda values:['TreatyDraft.AddArticleDraft(ArticleDraft.Self)'])))


def term(condition,call):
    return (TREATY_DRAFT,((DRAFT[0],condition),),lambda values:[call])


def timed_treaty(name,listing,holder):
    kept="EqualTo_int32(TreatyDraftPanel.GetDraft.GetBindingDays, '(int32){days}')"
    return Action(name,('country','treaty_article','days:choice'),'TreatyDraft.SendProposal',choices=DAYS,datamodels=((DRAFT[0],kept),),window=TREATY_DRAFT,start=OPEN_DRAFT,deadline=LISTED,
                  cleanup=(RESET,'InformationPanelBar.ClosePanel'),admit=admissible(holder),prepare=(RESET,),reason=unfit(holder),absent=((1,'Not('+kept+')'),),
                  stages=((TREATY_DRAFT,potential(listing,holder),lambda values:[ADD]),term('',"TreatyDraft.SetBindingDays('(int32){days}')")))


def backed_treaty(name,listing,holder,can,told,done,call,choices=()):
    return Action(name,('country','treaty_article',*(['obligation:choice'] if choices else [])),'TreatyDraft.SendProposal',choices=choices,datamodels=((DRAFT[0],done),),
                  window=TREATY_DRAFT,start=OPEN_DRAFT,deadline=LISTED,cleanup=(RESET,'InformationPanelBar.ClosePanel'),admit=admissible(holder),prepare=(RESET,),reason=unfit(holder),
                  absent=((0,'Not('+can+')',told),(1,'Not('+done+')',told)),
                  stages=((TREATY_DRAFT,potential(listing,holder),lambda values:[ADD]),term(can,call)))


def obliged_treaty(name,listing,holder):
    return backed_treaty(name,listing,holder,'TreatyDraftPanel.GetDraft.Can{obligation}('+LEFT+')','TreatyDraftPanel.GetDraft.Get{obligation}Desc('+LEFT+')',
                         'TreatyDraftPanel.GetDraft.Will{obligation}('+LEFT+')','TreatyDraft.Toggle{obligation}(TreatyDraft.GetLeftCountry.Self)',PROMISES)


def amend_add(name,listing,holder):
    return Action(name,('treaty','treaty_article'),'TreatyDraft.SendProposal',datamodels=(DRAFT,),window=TREATY_DRAFT,start=REDRAFT,deadline=LISTED,
                  cleanup=(RESET,'InformationPanelBar.ClosePanel'),admit='And('+NEGOTIABLE+', '+admissible(holder)+')',reason=unfit(holder),
                  stages=((TREATY_DRAFT,potential(listing,holder),lambda values:[ADD]),))


def amend_remove(name,listing,holder):
    held=f'TreatyDraftPanel.GetDraft.HasSelectedArticle(GetArticleType({{treaty_article}}).Self, TreatyDraftPanel.GetDraft.Get{holder}Country.Self)'
    return Action(name,('treaty','treaty_article'),'TreatyDraft.SendProposal',datamodels=((DRAFT[0],'Not('+held+')'),),window=TREATY_DRAFT,start=REDRAFT,deadline=LISTED,
                  cleanup=(RESET,'InformationPanelBar.ClosePanel'),admit='And('+NEGOTIABLE+', '+held+')',absent=((0,held),),
                  stages=((TREATY_DRAFT,((DRAFT[0],ADMITTED),(f'TreatyDraft.GetSelected{listing}','And(ArticleDraft.HasType({treaty_article}), ArticleDraft.CanBeModified)')),
                           lambda values:['TreatyDraft.RemoveArticle(ArticleDraft.Self)']),))


SWAY_ARTICLE=('gui/right_click_menu.gui','onclick = "[SwayOffer.SetArticleInputsFromDraft(ArticleDraft.Self)]"')
OPEN_SWAY=(('InformationPanelBar.OpenSwayCountryPanel({diplomatic_play}.Self, {country}.Self)',),((),))
SWAY_GOAL=(SWAY_PANEL,(('SwayCountryPanel.AccessSwayOfferWarGoalTypes','ObjectsEqual(WarGoalType.Self, {war_goal_type}.Self)'),),
           lambda values:['SwayCountryPanel.SetSwayOfferWarGoalType(WarGoalType.Self)'])
SWAY_MENU="RightClickMenuManager.ToggleSwayOfferArticleTypeInput(SwayOffer.Self, PdxGuiWidget.AccessSelf, 'article_input_right_click_menu_right')"
ARTICLE_PARAMS=(('goods','goods'),('state','state'),('region','strategic_region'),('law','commitment:law'))
ARTICLE_SETTERS={'goods':'ArticleDraft.SetGood({goods}.Self)','state':'ArticleDraft.SetState({state}.Self)',
                 'strategic_region':'ArticleDraft.SetStrategicRegion({strategic_region}.Self)','commitment:law':'ArticleDraft.SetLaw({commitment}.GetLawType.Self)'}


FIRST_OFFER="EqualTo_int32(PdxGuiWidget.AccessParent.GetIndexInDataModel, '(int32)0')"


def sway_type(name):
    return (SWAY_PANEL,(('SwayCountryPanel.AccessSwayOfferTypes',f"EqualTo_string(SwayOfferType.GetName, Localize('{name}'))"),),
            lambda values:['SwayCountryPanel.SetSwayOfferType(SwayOfferType.Self)'])


def sway(name,params,match,kind,goal=False):
    return Action(name,('diplomatic_play','country',*params.split()),SWAY,window=SWAY_PANEL,cleanup=('InformationPanelBar.ClosePanel',),start=OPEN_SWAY,
                  datamodels=(('SwayCountryPanel.AccessShownSwayOffers',match),),deadline=LISTED,stages=(sway_type(kind),SWAY_GOAL) if goal else (sway_type(kind),))


def article_sway(name,param):
    return Action(name,('diplomatic_play','country','war_goal_type','treaty_article',param),SWAY,window=SWAY_ARTICLE,
                  cleanup=('RightClickMenuManager.Close','InformationPanelBar.ClosePanel'),start=OPEN_SWAY,deadline=LISTED,
                  stages=(sway_type('WARGOALS'),SWAY_GOAL,
                          (SWAY_PANEL,(('SwayCountryPanel.AccessShownSwayOffers','And(SwayOffer.RequiresAnyInput, SwayOffer.GetOfferedWarGoal.GetArticleType.HasType({treaty_article}))'),),
                           lambda values:[SWAY_MENU]),
                          (SWAY_ARTICLE,(),lambda values:[ARTICLE_SETTERS[param]]),
                          (SWAY_ARTICLE,(),lambda values:['SwayOffer.SetArticleInputsFromDraft(ArticleDraft.Self)'])))


OPEN_GOALS=(('InformationPanelBar.OpenAddWarGoalPanel(DiplomaticPlay.Self, GetPlayer.Self)',),
            ((('AccessPlayer.AccessActiveDiplomaticPlays','ObjectsEqual(DiplomaticPlay.Self, {diplomatic_play}.Self)'),),))
GOAL_TYPE=(ADD_WAR_GOAL_PANEL,(('AddWarGoalPanel.AccessShownWarGoalTypes','ObjectsEqual(WarGoalType.Self, {war_goal_type}.Self)'),),
           lambda values:['AddWarGoalPanel.SetSelectedWarGoalType(WarGoalType.Self)'])
HELD='ObjectsEqual(WarGoalDraft.GetHolder.Self, {holder}.Self)'
GOAL_ARTICLE=('gui/right_click_menu.gui','onclick = "[WarGoalDraft.SetArticleInputsFromDraft(ArticleDraft.Self)]"')
ARTICLE_DRAFT='And(WarGoalDraft.HoldsArticle, And(WarGoalDraft.GetArticleType.HasType({treaty_article}), ObjectsEqual(WarGoalDraft.GetTarget.Self, {country}.Self)))'
GOAL_MENU="RightClickMenuManager.ToggleWarGoalArticleTypeInput(WarGoalDraft.Self, PdxGuiWidget.AccessSelf, 'article_input_right_click_menu_right')"


def goal(name,params,match):
    return Action(name,('diplomatic_play','war_goal_type',*params.split()),'AddWarGoalPanel.AccessDiplomaticPlay.AddWarGoal(WarGoalDraft.Self)',
                  datamodels=(('',match),),why='AddWarGoalPanel.GetDiplomaticPlay.GetCanAddWarGoalDesc(WarGoalDraft.Self)',
                  window=ADD_WAR_GOAL,cleanup=('InformationPanelBar.ClosePanel',),start=OPEN_GOALS,deadline=LISTED,stages=(GOAL_TYPE,))


def article_goal(name,param):
    return Action(name,('diplomatic_play','war_goal_type','country','treaty_article',param),'WarGoalDraft.GetDiplomaticPlay.AddWarGoal(WarGoalDraft.Self)',
                  window=GOAL_ARTICLE,cleanup=('RightClickMenuManager.Close','InformationPanelBar.ClosePanel'),start=OPEN_GOALS,deadline=LISTED,
                  stages=(GOAL_TYPE,(ADD_WAR_GOAL,(('',ARTICLE_DRAFT),),lambda values:[GOAL_MENU]),
                          (GOAL_ARTICLE,(),lambda values:[ARTICLE_SETTERS[param]]),
                          (GOAL_ARTICLE,(),lambda values:['WarGoalDraft.SetArticleInputsFromDraft(ArticleDraft.Self)'])))


PROPOSAL_KINDS=(('treaty','GetTreaty','Proposal.GetTreaty.IsValid',(('accept','AcceptTreatyProposal'),('decline','DeclineTreatyProposal'))),
                ('demand','GetDiplomaticDemand','Proposal.GetDiplomaticDemand.IsValid',(('accept','AcceptDiplomaticDemand'),('reject','RejectDiplomaticDemand'))),
                ('action_proposal','GetDiplomaticAction','Not(Or(Or(Proposal.GetTreaty.IsValid, Proposal.GetDiplomaticDemand.IsValid), Proposal.GetDiplomaticPlay.IsValid))',
                 (('accept','AcceptActionProposal'),('decline','DeclineActionProposal'))),
                ('sway','GetDiplomaticPlay.GetIncomingSway(Proposal.GetActor.Self, Proposal.GetRecipient.Self)',
                 'And(Proposal.GetDiplomaticPlay.IsValid, Not(Or(Proposal.GetTreaty.IsValid, Proposal.GetDiplomaticDemand.IsValid)))',(('accept','AcceptSway'),('reject','RejectSway'))))


TIME_WHY="Select_CString(TimeKeeper.CanTogglePause, Select_CString(TimeKeeper.IsPaused, 'paused', 'running'), 'toggle locked')"


def act(name,params,command,**options):
    return Action(name,tuple(params.split()) if params else (),command,**options)


ACTIONS=(
    act('build','state building_type','{state}.GetBuilding({building_type}.GetKey).QueueConstruction'),
    act('cancel_construction','building','{building}.CancelConstruction'),
    act('downsize','building','{building}.Downsize'),
    act('pause_construction','','GetPlayer.PauseConstruction'),
    act('resume_construction','','GetPlayer.ResumeConstruction'),
    act('pause_all_construction','','PauseAllConstruction'),
    act('resume_all_construction','','ResumeAllConstruction'),
    act('pause_construction_output','building','{building}.PauseConstructionOutput'),
    act('resume_construction_output','building','{building}.ResumeConstructionOutput'),
    act('nationalize','building levels:int','{building}.NationalizeBuildingLevels({levels})'),
    act('toggle_privatization','building','{building}.TogglePrivatization'),
    act('toggle_monopoly','building_type','{building_type}.ToggleMonopoly'),
    act('subsidies_on','building','{building}.ToggleSubsidiesOn'),
    act('subsidies_off','building','{building}.ToggleSubsidiesOff'),
    *(subset(f'subset_{name}_state',command,'building_type state ownership:choice') for name,command in SUBSET),
    bulk_nationalize('bulk_nationalize_state','building_type state ownership:choice'),
    bulk_nationalize('bulk_expropriate_state','building_type state ownership:choice',False),
    bulk_method('bulk_switch_production_method_state','building_type state production_method ownership:choice'),
    act('switch_production_method','building production_method','ProductionMethod.GetSwitch(Building.Self)',context='{building}',
        datamodels=(('Building.AccessProductionMethodGroups',''),
                    ('ProductionMethodGroup.AccessBuildingProductionMethods(Building.Self)','EqualTo_string(ProductionMethod.GetKey, {production_method})'))),
    act('reset_building_production_methods','building','{building}.ResetProductionMethodsToStandard'),
    lens('reset_production_methods'),
    lens('move_capital'),
    lens('move_market_capital'),
    *(act(f'{verb}_queue_item','state building_type',f'ConstructionQueueElement.{command}',
          datamodels=(('AccessPlayer.AccessGovernmentConstructionQueue',
                       'And(ObjectsEqual(ConstructionQueueElement.GetState.Self, {state}.Self), '
                       'EqualTo_string(ConstructionQueueElement.GetBuilding.GetBuildingType.GetKey, {building_type}.GetKey))'),))
      for verb,command in (('cancel','CancelConstruction'),('raise','MoveUp'),('lower','MoveDown'),('first','MoveToTop'),('last','MoveToBottom'))),
    act('set_tax_level','level:choice','GetPlayer.SetTaxLevel{level}',choices=LEVELS),
    act('set_government_wages','level:choice','GetPlayer.SetGovernmentWageLevel{level}',choices=LEVELS),
    act('set_military_wages','level:choice','GetPlayer.SetMilitaryWageLevel{level}',choices=LEVELS),
    act('toggle_consumption_tax','goods','{goods}.ToggleTaxation(GetPlayer)'),
    act('set_import_tariff','goods level:choice','GetPlayer.SetImportTariffs{level}({goods}.Self)',choices=('None','Low','High','Max')),
    act('set_export_tariff','goods level:choice','GetPlayer.SetExportTariffs{level}({goods}.Self)',choices=('None','Low','High','Max')),
    act('set_import_subvention','goods level:choice','GetPlayer.SetImportSubventions{level}({goods}.Self)',choices=('Low','High','Max')),
    act('set_export_subvention','goods level:choice','GetPlayer.SetExportSubventions{level}({goods}.Self)',choices=('Low','High','Max')),
    act('declare_bankruptcy','','GetPlayer.DeclareBankruptcy'),
    act('set_strait_toll','strait level:choice','{strait}.SetControllerTollRate{level}(GetPlayer.Self)',choices=TOLL_LEVELS),
    act('set_strait_access','strait state access:choice','{strait}.SetStateAccess{access}({state}.Self)',choices=ACCESS_STATUSES),
    act('set_strait_allowed','strait state allowed:choice','{strait}.SetStateAllowedCountries{allowed}({state}.Self)',choices=ACCESS_PERMISSIONS),
    act('enact_law','law','{law}.StartEnacting'),
    act('cancel_enactment','','GetPlayer.GetLawBeingEnacted.StopEnacting'),
    act('impose_law','law','{law}.StartImposing'),
    act('repeal_amendment','amendment','Amendment.Repeal',alternatives=tuple(
        ((f'AccessPlayer.AccessActive{group}Laws',''),('Law.GetAllAmendments','ObjectsEqual(Amendment.Self, {amendment}.Self)'))
        for group in ('PowerStructure','Economy','HumanRights','Other'))),
    act('toggle_bolster_movement','political_movement','{political_movement}.ToggleBolstering'),
    act('toggle_suppress_movement','political_movement','{political_movement}.ToggleSuppression'),
    act('negotiate','interest_group','GetPlayer.StartNegotiationWith({interest_group}.Self)'),
    Action('reform_government',('interest_group','mode:choice'),'ReformGovernment.Confirm',choices=('Potential','Staged'),
           window=POLITICS,start=(("InformationPanelBar.OpenPanelTabDontToggle('politics', 'default')",),((),)),datamodels=(REFORM,),
           cleanup=("GetVariableSystem.Clear('reform_government')",),
           stages=((POLITICS,(REFORM,),lambda values:['ReformGovernment.Reset',"GetVariableSystem.Set('reform_government', '1')"]),
                   (POLITICS,(REFORM,('ReformGovernment.GetAll{mode}InterestGroups','ObjectsEqual(InterestGroup.Self, {interest_group}.Self)')),
                    lambda values:[f"ReformGovernment.{'Stage' if values['mode']=='Potential' else 'Unstage'}InterestGroup(InterestGroup.AccessSelf)"]))),
    Action('reform_government_party',('member:interest_group','mode:choice'),'ReformGovernment.Confirm',choices=('Potential','Staged'),
           window=POLITICS,start=(("InformationPanelBar.OpenPanelTabDontToggle('politics', 'default')",),((),)),datamodels=(REFORM,),
           cleanup=("GetVariableSystem.Clear('reform_government')",),
           stages=((POLITICS,(REFORM,),lambda values:['ReformGovernment.Reset',"GetVariableSystem.Set('reform_government', '1')"]),
                   (POLITICS,(REFORM,('ReformGovernment.GetAll{mode}Parties',''),('Party.GetMembers','ObjectsEqual(InterestGroup.Self, {member}.Self)')),
                    lambda values:[f"ReformGovernment.{'Stage' if values['mode']=='Potential' else 'Unstage'}Party(Party.AccessSelf)"]))),
    act('set_institution_level','institution level:int','{institution}.StartChangingLevelTo({level})'),
    act('stop_institution_change','institution','{institution}.StopSizeChange'),
    act('issue_decree','state decree','GetDecreeType({decree}).GetSetCommand({state}.Self)'),
    act('remove_decree','state decree','Decree.GetRemoveCommand',context='{state}',
        datamodels=(('State.AccessDecrees','EqualTo_string(Decree.GetType.GetNameNoFormatting, GetDecreeType({decree}).GetNameNoFormatting)'),)),
    act('research','technology','{technology}.Research(GetPlayer.Self)'),
    act('queue_research','technology','{technology}.AddToQueue(GetPlayer.Self)'),
    act('dequeue_research','technology','{technology}.RemoveFromQueue(GetPlayer.Self)'),
    act('recruit','building military_formation combat_unit_type','{building}.QueueMilitaryConstruction({military_formation}.Self, {combat_unit_type}.Self)'),
    act('mobilize','military_formation','{military_formation}.Mobilize'),
    act('demobilize','military_formation','{military_formation}.Demobilize'),
    act('raise_conscripts','military_formation','{military_formation}.RaiseConscripts'),
    act('disband_formation','military_formation','MilitaryFormation.Disband',alternatives=FORMATION),
    act('mobilize_all','','GetPlayer.MobilizeAllArmies'),
    act('demobilize_all','','GetPlayer.DemobilizeAllArmies'),
    act('toggle_mobilization_option','military_formation mobilization_option','MobilizationOption.Toggle(MilitaryFormation.AccessSelf)',context='{military_formation}',
        datamodels=(('MilitaryFormation.GetMobilizationOptions','EqualTo_string(MobilizationOption.GetNameNoFormatting, {mobilization_option}.GetNameNoFormatting)'),)),
    act('set_supply_priority','military_formation level:choice',"{military_formation}.SelectSupplyPriority('{level}')",choices=('low','medium','high')),
    act('disband_regulars','military_formation combat_unit_type','{military_formation}.GetDisbandUnitTypeRegularCommand({combat_unit_type}.Self)'),
    act('disband_conscripts','military_formation combat_unit_type','{military_formation}.GetDisbandUnitTypeConscriptCommand({combat_unit_type}.Self)'),
    act('upgrade_regulars','military_formation combat_unit_type','{military_formation}.GetUpgradeRegularUnitTypeCommand({combat_unit_type}.Self)'),
    act('upgrade_conscripts','military_formation combat_unit_type','{military_formation}.GetUpgradeConscriptUnitTypeCommand({combat_unit_type}.Self)'),
    act('set_default_unit_type','military_formation combat_unit_type','{military_formation}.GetSetDefaultUnitTypeCommand({combat_unit_type}.Self)'),
    act('commander_order','character commander_order_type','Character.SelectOrder(CommanderOrderType.Self)',context='{character}',
        datamodels=(('Character.AccessOrders','EqualTo_string(CommanderOrderType.GetNameNoFormatting, {commander_order_type}.GetNameNoFormatting)'),)),
    act('hire_commander','character','{character}.GetRecruitCommandNoFormation'),
    act('hire_commander_for','character military_formation','{character}.GetRecruitCommand({military_formation}.Self)'),
    act('promote_commander','character','{character}.GetPromoteCommand'),
    act('assign_commander','character military_formation','{character}.AssignToFormation({military_formation}.Self)'),
    act('unassign_commander','character','{character}.UnassignFromFormation'),
    act('start_naval_mission','military_formation naval_mission_type','MilitaryFormation.CreateNavalMission(NavalMissionType.AccessSelf)',context='{military_formation}',
        datamodels=(('MilitaryFormation.GetPotentialMissionsTypes','EqualTo_string(NavalMissionType.GetNameNoFormatting, {naval_mission_type}.GetNameNoFormatting)'),)),
    act('end_naval_mission','military_formation','MilitaryFormation.RemoveNavalMission',alternatives=FORMATION[1:]),
    Action('start_naval_mission_selected',('military_formation','naval_mission_type'),'CreateNavalMissionsForSelectedFleets(NavalMissionType.AccessSelf)',start=SELECT_FLEET,why=FLEET_SELECTION,
           datamodels=(('GetSelectedFleetsPotentialAndPossibleMissions','EqualTo_string(NavalMissionType.GetNameNoFormatting, {naval_mission_type}.GetNameNoFormatting)'),)),
    Action('end_naval_mission_selected',('military_formation',),'RemoveSelectedFleetsMissions',start=SELECT_FLEET,why=FLEET_SELECTION),
    act('set_default_construction_fleet','military_formation','GetPlayer.SetDefaultConstructionFleet({military_formation}.Self)'),
    act('clear_default_construction_fleet','','GetPlayer.ClearDefaultConstructionFleet'),
    act('decommission_ship','ship','Ship.Decommission',
        datamodels=(('AccessPlayer.GetMilitaryFormationsFleet',''),('GetShipGroups',''),
                    ('MilitaryFormation.GetShipList.GetFilterOfGroup(ShipGroup.Self).GetShipsFiltered','ObjectsEqual(Ship.Self, {ship}.Self)'))),
    act('build_ship','ship_type','ShipTemplateList.GetDefaultTemplateOfType({ship_type}.Self).QueueConstruction'),
    act('build_ship_for','ship_type military_formation',
        'ShipTemplateList.GetDefaultTemplateForFleetOfType({military_formation}.Self, {ship_type}.Self).QueueConstructionForFleet({military_formation}.Self)'),
    act('cancel_ship','ship_type','ShipTemplateList.GetDefaultTemplateOfType({ship_type}.Self).CancelConstruction'),
    map_list('station_formation','military_formation state',SELECTED_STATE,'MilitaryFormation.OnStationClicked',transport=True),
    map_list('rehome_formation','military_formation strategic_region',
             'ObjectsEqual(MapListOption.GetDestinationData.GetHQ.GetStrategicRegion.Self, {strategic_region}.Self)','MilitaryFormation.OnRehomeClicked',transport=True),
    act('upgrade_all_units','','PanelMilitary.GetUpgradeAllUnitsInAllFormationsCommand',window=MILITARY_PANEL,start=OPEN_MILITARY),
    Action('create_army',('option:int',),'MapListOption.OnClick',valid='MapListOption.CanClick',window=MAP_LIST,start=OPEN_MILITARY,
           datamodels=(('','EqualTo_int32(PdxGuiWidget.AccessParent.GetIndexInDataModel, {option})'),),
           stages=((MILITARY_PANEL,(),lambda values:['PanelMilitary.OnClickRecruitArmyFormation']),)),
    transfer('transfer_battalions','military_formation target:military_formation',(),FORMATION[0],((TARGET_ARMY,(SET_RIGHT,)),((),(HALF,)))),
    transfer('transfer_ships','military_formation target:military_formation',(),FORMATION[1],((TARGET_FLEET,(SET_RIGHT,)),((),(HALF,)))),
    transfer('split_army','military_formation',(NEW_RIGHT,),FORMATION[0],(((),(HALF,)),)),
    transfer('split_fleet','military_formation',(NEW_RIGHT,),FORMATION[1],(((),(HALF,)),)),
    transfer('transfer_ship','ship target:military_formation',(),OWN_SHIP,((TARGET_FLEET,(SET_RIGHT,)),(STAGED_SHIP,('StagedShipsWithType.ToggleShipSelected(Ship.Self)','TransferFormationPopup.MoveShips(StagedShipsWithType.AccessSelf)')))),
    merge('merge_armies',SELECT_ARMY,'AccessPlayer.GetMilitaryFormationsArmy'),
    merge('merge_fleets',SELECT_FLEET,'AccessPlayer.GetMilitaryFormationsFleet'),
    Action('create_fleet',('option:int',),'MapListOption.OnClick',valid='MapListOption.CanClick',why='MapListOption.GetTooltip',window=MAP_LIST,start=OPEN_NAVY,deadline=LISTED,
           datamodels=(('','EqualTo_int32(PdxGuiWidget.AccessParent.GetIndexInDataModel, {option})'),),
           stages=((MILITARY_PANEL,(),lambda values:['PanelMilitary.OnClickRecruitFleetFormation']),)),
    map_list('toggle_naval_mission_region','military_formation strategic_region',NAVAL_REGION,'MilitaryFormation.OnEditMissionSeaRegionsClicked',chains=FORMATION[1:],deadline=LISTED),
    act('change_naval_mission_type','military_formation naval_mission_type','MilitaryFormation.CreateNavalMissionWithPreviousArea(NavalMissionType.AccessSelf)',context='{military_formation}',deadline=LISTED,
        datamodels=(('MilitaryFormation.GetPotentialMissionsTypes','EqualTo_string(NavalMissionType.GetNameNoFormatting, {naval_mission_type}.GetNameNoFormatting)'),)),
    map_list('station_fleet','military_formation state',SELECTED_STATE,'MilitaryFormation.OnStationClicked',chains=FORMATION[1:],deadline=LISTED),
    map_list('rehome_fleet','military_formation strategic_region',HQ_REGION,'MilitaryFormation.OnRehomeClicked',chains=FORMATION[1:],deadline=LISTED),
    act('defend_invasion_fleet','military_formation front:int','Invasion.DeployFleetToDefend({military_formation}.Self)',deadline=LISTED,
        datamodels=(('AccessPlayer.AccessWars',''),('War.GetInvasions','EqualTo_string(ToString_uint32(Invasion.GetFront.GetID), ToString_int32({front}))'))),
    *(act(name,'ship','Ship.'+command,datamodels=OWN_SHIP,deadline=LISTED) for name,command in (('assign_flagship','AssignAsFlagship'),('unassign_flagship','UnassignAsFlagship'),
                                                                               ('retrofit_ship','Retrofit'),('cancel_retrofit_ship','CancelRetrofit'))),
    act('change_ship_template','ship index:int','{ship}.ChangeTemplate(ShipTemplate.Self)',deadline=LISTED,
        datamodels=(('ShipTemplateList.GetTemplatesOfType({ship}.GetType.Self)','EqualTo_int32(PdxGuiWidget.AccessParent.GetIndexInDataModel, {index})'),)),
    act('retrofit_fleet_and_station','military_formation','MilitaryFormation.RetrofitShipsAndStation',alternatives=FORMATION[1:]),
    act('retrofit_all_and_station','','RetrofitShipsAndStation'),
    act('disband_unit','combat_unit','CombatUnit.GetMilitaryFormation.GetDisbandUnitCommand(CombatUnit.Self)',deadline=LISTED,
        datamodels=(('AccessPlayer.GetMilitaryFormationsArmy',''),('MilitaryFormation.GetCombatUnitEntries',''),
                    ('MilitaryFormationUnitEntry.GetCombatUnits','ObjectsEqual(CombatUnit.Self, {combat_unit}.Self)'))),
    act('cancel_ship_for','ship_type military_formation',
        'ShipTemplateList.GetDefaultTemplateForFleetOfType({military_formation}.Self, {ship_type}.Self).CancelConstructionForFleet({military_formation}.Self)'),
    Action('deploy_selected_to_front',('military_formation','front:int'),'Front.GetDeploySelectedFormationsCommand',start=SELECT_ARMY,why=SELECTION,
           datamodels=(('AccessPlayer.AccessWars',''),('War.AccessFronts','EqualTo_string(ToString_uint32(Front.GetID), ToString_int32({front}))'))),
    Action('station_selected',('military_formation','strategic_region'),'Hq.GetStationSelectedFormationsCommand',start=SELECT_ARMY,why=SELECTION,transport=True,
           overseas=('Hq.GetStates','State.RequiresNavalTransportForSelectedFormations','State.ShowTransportPlannerForSelectedFormation'),
           datamodels=(('AccessPlayer.AccessLandHQs','ObjectsEqual(Hq.GetStrategicRegion.Self, {strategic_region}.Self)'),)),
    *(act(f'{verb}_ship_item','index:int',f'ShipConstruction.{command}',window=SHIP_PAGES,start=OPEN_SHIPS,
          stages=((SHIP_PAGES,(),lambda values:['ConstructionPanel.ShowMilitaryShipConstructions']),),
          datamodels=(('ConstructionPanel.GetShipConstructions','EqualTo_int32(ShipConstruction.GetIndex, {index})'),))
      for verb,command in (('raise','MoveUp'),('lower','MoveDown'),('first','MoveToTop'),('last','MoveToBottom'),('cancel','Cancel'))),
    act('recall_fleet','military_formation','MilitaryFormation.RecallForRepairs',alternatives=FORMATION[1:]),
    act('retrofit_fleet','military_formation','MilitaryFormation.RetrofitShips',alternatives=FORMATION[1:]),
    act('cancel_retrofit_fleet','military_formation','MilitaryFormation.CancelRetrofitShips',alternatives=FORMATION[1:]),
    act('retrofit_all','','RetrofitShips'),
    act('set_default_ship_template','ship_type index:int','ShipTemplate.SetAsDefaultForCountry',datamodels=TEMPLATE_ITEM),
    act('set_fleet_ship_template','ship_type index:int military_formation','ShipTemplate.SetAsDefaultForFleet({military_formation}.Self)',datamodels=TEMPLATE_ITEM),
    act('delete_ship_template','ship_type index:int','ShipTemplate.DeleteTemplate',datamodels=TEMPLATE_ITEM),
    act('cancel_retrofit_all','','CancelRetrofitShips'),
    act('set_borrow_setting','military_formation index:int','MilitaryFormationBorrowSetting.OnClicked',valid='IsValid(MilitaryFormationBorrowSetting.GetBorrowingCommand)',
        cleanup=('Execute(MilitaryFormationBorrowSetting.GetBorrowingCommand)',),
        alternatives=tuple((*chain,('MilitaryFormation.GetBorrowSettings','EqualTo_int32(PdxGuiWidget.GetIndexInDataModel, {index})')) for chain in FORMATION)),
    act('defend_invasion','military_formation front:int','Invasion.DeployArmyToDefend({military_formation}.Self)',
        datamodels=(('AccessPlayer.AccessWars',''),('War.GetInvasions','EqualTo_string(ToString_uint32(Invasion.GetFront.GetID), ToString_int32({front}))'))),
    selected('mobilize_selected','military_formation','MobilizeSelectedArmies'),
    selected('demobilize_selected','military_formation','DemobilizeSelectedArmies'),
    selected('raise_conscripts_selected','military_formation','RaiseConscriptsInSelectedArmies'),
    selected('cancel_strategic_objective_selected','military_formation state','SetStrategicObjectiveForSelectedFormations({state}.Self)'),
    map_list('recruit_from_formation','military_formation combat_unit_type state',SELECTED_STATE,'MilitaryFormation.OnClickRecruitCombatUnit({combat_unit_type}.Self)'),
    map_list('activate_conscription_center','military_formation combat_unit_type state',SELECTED_STATE,'MilitaryFormation.OnClickRecruitConscript({combat_unit_type}.Self)'),
    act('disembark','military_formation','{military_formation}.DisembarkFormation'),
    map_list('deploy_to_front','military_formation front:int',
             'EqualTo_string(ToString_uint32(MapListOption.GetFrontData.GetFront.GetID), ToString_int32({front}))','MilitaryFormation.OnDeployToFrontClicked',transport=True),
    map_list('set_strategic_objective','military_formation state',
             SELECTED_STATE,'MilitaryFormation.OnSetStrategicObjectiveClicked',transport=True),
    act('cancel_invasion','military_formation','MilitaryFormation.GetInvasion.Cancel',alternatives=FORMATION),
    act('pause_ship_construction','','GetPlayer.PauseShipConstruction'),
    act('resume_ship_construction','','GetPlayer.ResumeShipConstruction'),
    act('set_supply_ship_construction','level:choice','GetPlayer.SetSupplyShipConstructionLevel{level}',choices=LEVELS),
    Action('design_ship_template',('ship_type','ship_modification'),'PopupManager.AccessShipDesignerPopup.CreateTemplate',
           window=DESIGNER,start=(('PopupManager.HideShipDesignerPopup','PopupManager.ToggleShipDesignerPopup'),((),)),cleanup=('PopupManager.HideShipDesignerPopup',),
           stages=((DESIGNER,(),lambda values:['PopupManager.AccessShipDesignerPopup.SetShipType({ship_type}.Self)']),
                   (DESIGNER,(('PopupManager.AccessShipDesignerPopup.GetModificationSlots',''),
                              ('ShipDesignerModSlot.GetModifications','EqualTo_string(ShipModificationType.GetNameNoFormatting, GetShipModificationType({ship_modification}).GetNameNoFormatting)')),
                    lambda values:['ShipDesignerModSlot.OnSelectModificationForSlot(ShipModificationType.Self)']))),
    Action('edit_ship_template',('ship_type','index:int','ship_modification'),'PopupManager.AccessShipDesignerPopup.EditTemplate',
           window=DESIGNER,start=(('PopupManager.HideShipDesignerPopup','PopupManager.ToggleShipDesignerPopup'),((),)),cleanup=('PopupManager.HideShipDesignerPopup',),
           stages=((DESIGNER,(),lambda values:['PopupManager.AccessShipDesignerPopup.SetShipType({ship_type}.Self)']),
                   (DESIGNER,TEMPLATE_ITEM,lambda values:['PopupManager.AccessShipDesignerPopup.SetShipTemplate(ShipTemplate.Self)']),
                   (DESIGNER,(('PopupManager.AccessShipDesignerPopup.GetModificationSlots',''),
                              ('ShipDesignerModSlot.GetModifications','EqualTo_string(ShipModificationType.GetNameNoFormatting, GetShipModificationType({ship_modification}).GetNameNoFormatting)')),
                    lambda values:['ShipDesignerModSlot.OnSelectModificationForSlot(ShipModificationType.Self)']))),
    act('character_interaction','character interaction','Character.GetInteraction({interaction}).ExecuteCommand(Character.Self)',
        valid='Character.GetInteraction({interaction}).IsCommandValid(Character.Self)',context='{character}'),
    act('diplomatic_action','country diplomatic_action','GetCountryDiplomaticAction({diplomatic_action}, GetPlayer.Self, {country}.Self).ExecuteAction'),
    Action('diplomatic_action_obligation',('country','diplomatic_action','obligation:choice'),'DiplomaticActionWindow.ExecuteAction',choices=('CallInObligation','OweObligation'),
           window=DIPLOMATIC_WINDOW,cleanup=('PopupManager.HideDiplomaticActionConfirmation',),
           start=(('GetCountryDiplomaticAction({diplomatic_action}, GetPlayer.Self, {country}.Self).ExecuteWithConfirmation',),((),)),
           stages=((DIPLOMATIC_WINDOW,(),lambda values:['DiplomaticActionWindow.Toggle{obligation}']),)),
    state_action('diplomatic_action_first_state','First'),
    state_action('diplomatic_action_second_state','Second'),
    Action('diplomatic_action_states',('country','diplomatic_action','given:state','taken:state','obligation:choice'),'DiplomaticActionWindow.ExecuteAction',choices=OBLIGATIONS,
           window=DIPLOMATIC_WINDOW,cleanup=('PopupManager.HideDiplomaticActionConfirmation',),start=OPEN_ACTION,deadline=LISTED,
           stages=(state_target('First',UNPICK),state_pick('given'),state_target('Second'),state_pick('taken'),(DIPLOMATIC_WINDOW,(),owed))),
    act('start_play_liberation','country country_definition diplomatic_play_type',
        '{diplomatic_play_type}.GetStartCommandCountryWithDefinition(GetPlayer.Self, {country}.Self, {country_definition}.Self)'),
    act('start_play_country','country diplomatic_play_type','{diplomatic_play_type}.GetStartCommandCountry(GetPlayer.Self, {country}.Self)'),
    Action('start_play_confirmed',('country','diplomatic_play_type','mode:choice'),'DiplomaticPlayConfirmation.ConfirmAction',choices=('AsDemand','ForcePlay'),
           window=PLAY_CONFIRMATION,cleanup=('PopupManager.HideDiplomaticPlayConfirmation',),
           start=(('{diplomatic_play_type}.ShowConfirmationCountry({country}.Self)',),((),)),
           stages=((PLAY_CONFIRMATION,(),lambda values:['DiplomaticPlayConfirmation.ToggleForceDiplomaticPlay'] if values['mode']=='ForcePlay' else []),)),
    act('start_play_state','state diplomatic_play_type','{diplomatic_play_type}.GetStartCommandState(GetPlayer.Self, {state}.Self)'),
    *(act(name,'diplomatic_play','{diplomatic_play}.'+command+'(GetPlayer)')
      for name,command in (('support_initiator','SupportInitiator'),('support_target','SupportTarget'),('lean_initiator','LeanTowardsInitiator'),
                           ('lean_target','LeanTowardsTarget'),('stay_on_fence','BeOnTheFence'),('declare_neutrality','DeclareNeutrality'),
                           ('back_down','Yield'))),
    *(act(name,'war','{war}.'+command+'(GetPlayer.Self)')
      for name,command in (('propose_peace','ProposePeaceDeal'),('white_peace','SetWhitePeace'),('capitulate','Capitulate'),('toggle_accept_peace','ToggleAcceptPeace'))),
    *(act(name,'diplomatic_play war_goal_type country','WarGoal.'+command+'(GetPlayer.Self)',alternatives=tuple(
          ((outer,condition),(inner,'And(ObjectsEqual(WarGoal.GetType.Self, {war_goal_type}.Self), ObjectsEqual(WarGoal.GetTarget.Self, {country}.Self))'))
          for outer,condition,inners in (('AccessPlayer.AccessActiveDiplomaticPlays','And(Not(DiplomaticPlay.HasEscalatedIntoWar), ObjectsEqual(DiplomaticPlay.Self, {diplomatic_play}.Self))',
                                          ('DiplomaticPlay.GetInitiatorWarGoals','DiplomaticPlay.GetTargetWarGoals')),
                                         ('AccessPlayer.AccessWars','ObjectsEqual(War.GetDiplomaticPlay.Self, {diplomatic_play}.Self)',
                                          ('War.GetAttackersWarGoals','War.GetDefendersWarGoals')))
          for inner in inners))
      for name,command in (('toggle_press_war_goal','ToggleIsPressedInPotentialPeaceDeal'),('make_primary_demand','MakeWarGoalPrimaryDemand'))),
    *(treaty(f'{verb}_treaty_article',listing,holder) for verb,listing,holder in TREATY_SIDES),
    *(goods_treaty(f'{verb}_goods_treaty_article',listing,holder) for verb,listing,holder in TREATY_SIDES[:2]),
    *(input_treaty(f'{verb}_{kind}_treaty_article',listing,holder,kind) for verb,listing,holder in TREATY_SIDES[:2] for kind in INPUTS),
    *(timed_treaty(f'{verb}_timed_treaty_article',listing,holder) for verb,listing,holder in TREATY_SIDES),
    *(obliged_treaty(f'{verb}_obliged_treaty_article',listing,holder) for verb,listing,holder in TREATY_SIDES),
    backed_treaty('threaten_treaty_article','Demands','Right','TreatyDraftPanel.GetDraft.CanThreatenNavalHostilities','TreatyDraftPanel.GetDraft.GetThreatenNavalHostilitiesDesc',
                  'TreatyDraftPanel.GetDraft.WillThreatenNavalHostilities','TreatyDraft.ToggleThreatenNavalHostilities'),
    backed_treaty('work_out_treaty_article','Demands','Right','TreatyDraftPanel.GetDraft.CanMakeThisWork(AccessPlayer.Self)','TreatyDraftPanel.GetDraft.GetCanMakeThisWorkDesc(AccessPlayer.Self)',
                  'TreatyDraftPanel.GetDraft.WillAIAccept(TreatyDraftPanel.GetDraft.GetRightCountry.Self)','TreatyDraft.MakeThisWork(AccessPlayer.Self)'),
    Action('exchange_treaty_articles',('country','treaty_article','demand:choice'),'TreatyDraft.SendProposal',choices=PLAIN,datamodels=((DRAFT[0],BOTH),),
           window=TREATY_DRAFT,start=OPEN_DRAFT,deadline=LISTED,cleanup=(RESET,'InformationPanelBar.ClosePanel'),admit=admissible('Left'),prepare=(RESET,),reason=unfit('Left'),
           absent=((0,'Not('+WANTED+')',unfit('Right',DEMANDED)),),
           stages=((TREATY_DRAFT,potential('Offers','Left'),lambda values:[ADD]),
                   (TREATY_DRAFT,((DRAFT[0],WANTED),('@TreatyDraft.GetRightCountry',''),('TreatyDraft.GetPotentialDemands',"ArticleType.HasType('{demand}')")),lambda values:[ADD]))),
    *(amend_add(f'amend_{verb}_treaty_article',listing,holder) for verb,listing,holder in TREATY_SIDES),
    *(amend_remove(f'amend_drop_{verb}_treaty_article',listing,holder) for verb,listing,holder in TREATY_SIDES),
    sway('offer_sway','',FIRST_OFFER,'OBLIGATIONS'),
    sway('offer_sway_ally','',FIRST_OFFER,'SWAY_TYPE_CALL_ALLY'),
    sway('offer_sway_state','state','ObjectsEqual(SwayOffer.GetState.Self, {state}.Self)','SWAY_TYPE_TRANSFER_STATE'),
    sway('offer_sway_subject','subject:country','ObjectsEqual(SwayOffer.GetThirdPartyCountry.Self, {subject}.Self)','SWAY_TYPE_TRANSFER_SUBJECT'),
    *(sway(name,'diplomatic_action','EqualTo_string(SwayOffer.GetDiplomaticActionType.GetKey, {diplomatic_action})',kind)
      for name,kind in (('offer_sway_pact','SWAY_TYPE_DIPLOMATIC_PACT'),('offer_sway_subjection','SWAY_TYPE_BECOME_SUBJECT'))),
    sway('offer_sway_goal_country','war_goal_type target:country',
         'And(Not(SwayOffer.RequiresAnyInput), ObjectsEqual(SwayOffer.GetOfferedWarGoal.GetTarget.Self, {target}.Self))','WARGOALS',goal=True),
    sway('offer_sway_goal_state','war_goal_type state','ObjectsEqual(SwayOffer.GetOfferedWarGoal.GetTargetState.Self, {state}.Self)','WARGOALS',goal=True),
    *(article_sway(f'offer_sway_{kind}_article',param) for kind,param in ARTICLE_PARAMS),
    goal('add_war_goal_country','holder:country country',
         'And('+HELD+', And(Not(WarGoalDraft.HoldsArticle), And(Not(WarGoalDraft.HasCountryCreation), ObjectsEqual(WarGoalDraft.GetTarget.Self, {country}.Self))))'),
    goal('add_war_goal_state','holder:country state','And('+HELD+', ObjectsEqual(WarGoalDraft.GetTargetState.Self, {state}.Self))'),
    goal('add_war_goal_liberation','country country_definition',
         'And(ObjectsEqual(WarGoalDraft.GetTarget.Self, {country}.Self), ObjectsEqual(WarGoalDraft.GetCountryCreation.GetDefinition.Self, {country_definition}.Self))'),
    goal('add_war_goal_article','country treaty_article',
         'And(WarGoalDraft.HoldsArticle, And(WarGoalDraft.GetArticleType.HasType({treaty_article}), ObjectsEqual(WarGoalDraft.GetTarget.Self, {country}.Self)))'),
    *(article_goal(f'add_{kind}_war_goal',param) for kind,param in ARTICLE_PARAMS),
    act('withdraw_treaty','treaty','Treaty.WithdrawFromTreaty',datamodels=(('AccessPlayer.GetInForceTreaties','ObjectsEqual(Treaty.Self, {treaty}.Self)'),)),
    Action('form_power_bloc',('power_bloc_identity','power_bloc_principle'),'PowerBlocFormationPanel.GetPowerBlocFormation.Confirm',
           window=BLOC_FORMATION,start=(('InformationPanelBar.OpenPowerBlocFormationPanel',),((),)),
           cleanup=('PopupManager.HidePowerBlocPrincipleSelectionWindow','InformationPanelBar.ClosePanel'),
           stages=((BLOC_FORMATION,(('PowerBlocFormationPanel.GetPowerBlocFormation.GetIdentities','EqualTo_string(PowerBlocIdentity.GetNameNoFormatting, GetPowerBlocIdentity({power_bloc_identity}).GetNameNoFormatting)'),),
                    lambda values:['PowerBlocFormationPanel.GetPowerBlocFormation.ResetPrinciples','PowerBlocFormationPanel.GetPowerBlocFormation.SelectIdentity(PowerBlocIdentity.AccessSelf)']),
                   (BLOC_FORMATION,(("@PowerBlocFormationPanel.GetPowerBlocFormation.GetPrincipleSlot('(int32)0')",''),),
                    lambda values:['PowerBlocPanel.ToggleFormationSelectionWindow(PowerBlocFormationPrincipleSlot.AccessSelf)']),
                   (PRINCIPLE_WINDOW,(('PowerBlocPrincipleSelectionWindow.GetAvailableGroups',''),('PowerBlocPrincipleGroup.GetLevels','ObjectsEqual(PowerBlocPrinciple.Self, {power_bloc_principle}.Self)')),
                    lambda values:['PowerBlocPrincipleSelectionWindow.TogglePrincipleSelection(PowerBlocPrinciple.Self)']),
                   (PRINCIPLE_WINDOW,(),lambda values:['PowerBlocPrincipleSelectionWindow.SubmitFormationPrincipleSelection','PopupManager.HidePowerBlocPrincipleSelectionWindow']))),
    act('request_join_power_bloc','power_bloc','{power_bloc}.GetRequestToJoin(GetPlayer.Self).ExecuteAction'),
    act('kick_from_power_bloc','country','GetPlayer.GetPowerBloc.Kick({country}.Self)'),
    act('leave_power_bloc','','GetPlayer.LeavePowerBloc'),
    principle('pick_principle'),
    principle('replace_principle'),
    act('upgrade_principle','power_bloc_principle','PowerBlocPrinciple.UpgradeToNextLevel',
        datamodels=(('AccessPlayer.AccessPowerBloc.GetPrinciples','ObjectsEqual(PowerBlocPrinciple.Self, {power_bloc_principle}.Self)'),)),
    act('create_company','company_type','GetPlayer.CreateCompany({company_type}.Self)'),
    act('remove_company','company_type','GetPlayer.RemoveCompany({company_type}.Self)'),
    act('toggle_charter','company charter','Company.ToggleCharter(CompanyCharterType.Self)',datamodels=CHARTER),
    act('grant_building_charter','company charter building_type','Company.ToggleBuildingCharter(CompanyCharterType.Self, BuildingType.Self)',deadline=LISTED,
        datamodels=(*CHARTER,('CompanyCharterType.GetPotentialBuildings(Company.Self)','EqualTo_string(BuildingType.GetKey, {building_type}.GetKey)'))),
    act('revoke_building_charter','company charter building_type','Company.ToggleBuildingCharter(CompanyCharterType.Self, CompanyCharter.GetBuildingType.Self)',deadline=LISTED,
        datamodels=(*CHARTER,('Company.GetActiveCharters(CompanyCharterType.Self)','EqualTo_string(CompanyCharter.GetBuildingType.GetKey, {building_type}.GetKey)'))),
    act('grant_region_charter','company charter state','Company.ToggleRegionCharter(CompanyCharterType.Self, StateRegion.Self)',deadline=LISTED,
        datamodels=(*CHARTER,('CompanyCharterType.GetPotentialRegions(Company.Self)','ObjectsEqual(StateRegion.Self, {state}.GetStateRegion.Self)'))),
    act('revoke_region_charter','company charter state','Company.ToggleRegionCharter(CompanyCharterType.Self, CompanyCharter.GetStateRegion.Self)',deadline=LISTED,
        datamodels=(*CHARTER,('Company.GetActiveCharters(CompanyCharterType.Self)','ObjectsEqual(CompanyCharter.GetStateRegion.Self, {state}.GetStateRegion.Self)'))),
    act('colonize','state','{state}.GetStateRegion.Colonize'),
    act('toggle_pause_colonization','state','{state}.TogglePauseColonization'),
    act('abandon_colony','state','{state}.AbandonColony'),
    act('incorporate','state','{state}.IncorporateState'),
    act('unincorporate','state','{state}.UnincorporateState'),
    act('press_journal_button','journal_entry button:int','ScriptedButton.ExecuteEffect',
        datamodels=(('AccessPlayer.AccessActiveJournalEntries','ObjectsEqual(JournalEntry.Self, {journal_entry}.Self)'),
                    ('JournalEntry.GetScriptedButtons','EqualTo_int32(PdxGuiWidget.AccessParent.GetIndexInDataModel, {button})'))),
    act('choose_event_option','event:event option:int','EventOption.Select',valid='EventOption.IsEnabled',window=EVENT_WINDOW,
        datamodels=((EVENT_WINDOW[1],'And(EqualTo_string(EventWindow.GetEvent.GetKey, {event}), EqualTo_int32(PdxGuiWidget.AccessParent.GetIndexInDataModel, {option}))'),)),
    *(act(f'{verb}_{kind}','country',f'Proposal.{getter}.{command}',window=PROPOSALS,
          datamodels=((PROPOSALS[1],f'And(ObjectsEqual(Proposal.GetActor.Self, {{country}}.Self), {condition})'),))
      for kind,getter,condition,pairs in PROPOSAL_KINDS for verb,command in pairs),
    act('quick_decline_proposal','country','PopupManager.DeclineProposal(Proposal.AccessSelf)',valid='Proposal.GetActor.IsValid',window=PROPOSALS,
        datamodels=((PROPOSALS[1],'ObjectsEqual(Proposal.GetActor.Self, {country}.Self)'),)),
    act('break_pact','country diplomatic_action','DiplomaticAction.ExecuteAction',deadline=LISTED,
        datamodels=(('@GetCountryDiplomaticAction({diplomatic_action}, GetPlayer.Self, {country}.Self)','DiplomaticAction.IsActivePact'),)),
    Action('embark_formation',('military_formation','fleet:military_formation'),'MilitaryFormationWrapped.EmbarkFormation(MilitaryFormation.Self)',window=EMBARK_FLEETS,
           start=(('RightClickMenuManager.ShowForEmbarkSelectFleet(MilitaryFormation.AccessSelf)',),FORMATION[:1]),cleanup=('RightClickMenuManager.Close',),
           datamodels=((EMBARK_FLEETS[1],'ObjectsEqual(MilitaryFormation.Self, {fleet}.Self)'),)),
    invasion('plan_land_invasion','military_formation state',((INVADING_ARMY,'InvasionPlannerPopup.OnSelectedArmy(MilitaryFormation.AccessSelf)'),)),
    invasion('plan_naval_invasion','military_formation fleet:military_formation state',
             ((INVADING_FLEET,'InvasionPlannerPopup.OnSelectedFleet(MilitaryFormation.AccessSelf)'),(INVADING_ARMY,'InvasionPlannerPopup.OnSelectedArmy(MilitaryFormation.AccessSelf)'))),
    act('pause','','TimeKeeper.TogglePause',valid='And(TimeKeeper.CanTogglePause, Not(TimeKeeper.IsPaused))',why=TIME_WHY),
    act('unpause','','TimeKeeper.TogglePause',valid='And(TimeKeeper.CanTogglePause, TimeKeeper.IsPaused)',why=TIME_WHY),
    act('set_speed','speed:choice',"TimeKeeper.SetGameSpeed('(int32){speed}')",valid='TimeKeeper.CanSetGameSpeed',choices=('0','1','2','3','4')),
    act('take_decision','decision','Decision.TakeDecision(GetPlayer)',
        datamodels=(('AccessPlayer.GetDecisions','EqualTo_string(Decision.GetName, Localize({decision}))'),)),
    act('toggle_ignore_decision','decision','GetPlayer.ToggleIgnoreDecision(Decision.Self)',
        datamodels=(('AccessPlayer.GetDecisions','EqualTo_string(Decision.GetName, Localize({decision}))'),)),
)


BY_NAME={action.name:action for action in ACTIONS}


GROUPS={
    'construction':('build','cancel_construction','downsize','pause_construction','resume_construction','pause_all_construction','resume_all_construction','pause_construction_output','resume_construction_output',
                    'cancel_queue_item','raise_queue_item','lower_queue_item','first_queue_item','last_queue_item'),
    'buildings':('nationalize','toggle_privatization','toggle_monopoly','subsidies_on','subsidies_off',
                 'switch_production_method',*(f'subset_{name}_state' for name,_ in SUBSET),
                 'bulk_switch_production_method_state','bulk_nationalize_state','bulk_expropriate_state','reset_building_production_methods','reset_production_methods'),
    'budget':('set_tax_level','set_government_wages','set_military_wages','toggle_consumption_tax','set_import_tariff','set_export_tariff',
              'set_import_subvention','set_export_subvention','declare_bankruptcy','set_strait_toll','set_strait_access','set_strait_allowed'),
    'politics':('enact_law','cancel_enactment','impose_law','repeal_amendment','toggle_bolster_movement','toggle_suppress_movement','negotiate','reform_government','reform_government_party',
                'set_institution_level','stop_institution_change','issue_decree','remove_decree'),
    'research':('research','queue_research','dequeue_research'),
    'army':('defend_invasion','station_selected','deploy_selected_to_front','mobilize_selected','demobilize_selected','raise_conscripts_selected','cancel_strategic_objective_selected','set_borrow_setting','transfer_battalions','upgrade_all_units','create_army','recruit_from_formation','activate_conscription_center','disembark','deploy_to_front','station_formation','rehome_formation','set_strategic_objective','cancel_invasion','recruit','mobilize','demobilize','raise_conscripts','disband_formation','mobilize_all','demobilize_all','toggle_mobilization_option',
            'set_supply_priority','disband_regulars','disband_conscripts','upgrade_regulars','upgrade_conscripts','set_default_unit_type','embark_formation','plan_land_invasion','plan_naval_invasion','split_army','merge_armies','disband_unit'),
    'navy':('recall_fleet','raise_ship_item','lower_ship_item','first_ship_item','last_ship_item','cancel_ship_item','set_default_construction_fleet','clear_default_construction_fleet','decommission_ship','build_ship','build_ship_for','cancel_ship','start_naval_mission','end_naval_mission','start_naval_mission_selected','end_naval_mission_selected','pause_ship_construction','resume_ship_construction','set_supply_ship_construction','design_ship_template','edit_ship_template','retrofit_fleet','cancel_retrofit_fleet','retrofit_all','cancel_retrofit_all',
            'set_default_ship_template','set_fleet_ship_template','delete_ship_template','transfer_ships','split_fleet','transfer_ship','merge_fleets','create_fleet',
            'toggle_naval_mission_region','change_naval_mission_type','station_fleet','rehome_fleet','defend_invasion_fleet','assign_flagship','unassign_flagship','retrofit_ship',
            'cancel_retrofit_ship','change_ship_template','retrofit_fleet_and_station','retrofit_all_and_station','cancel_ship_for'),
    'characters':('commander_order','hire_commander','hire_commander_for','promote_commander','assign_commander','unassign_commander','character_interaction'),
    'diplomacy':('diplomatic_action','diplomatic_action_obligation','start_play_confirmed','withdraw_treaty','offer_treaty_article','demand_treaty_article','agree_treaty_article',
                 'offer_goods_treaty_article','demand_goods_treaty_article',*(f'{verb}_{kind}_treaty_article' for verb in ('offer','demand') for kind in INPUTS),
                 *(f'{verb}_{kind}_treaty_article' for verb in ('offer','demand','agree') for kind in ('timed','obliged')),'threaten_treaty_article','work_out_treaty_article',
                 'exchange_treaty_articles',*(f'amend_{verb}_treaty_article' for verb in ('offer','demand','agree','drop_offer','drop_demand','drop_agree')),
                 'diplomatic_action_first_state','diplomatic_action_second_state','diplomatic_action_states','accept_treaty','decline_treaty','accept_demand','reject_demand','accept_action_proposal',
                 'decline_action_proposal','quick_decline_proposal','request_join_power_bloc','form_power_bloc','kick_from_power_bloc','leave_power_bloc','upgrade_principle','pick_principle',
                 'replace_principle','break_pact'),
    'plays':('start_play_country','start_play_state','start_play_liberation','support_initiator','support_target','lean_initiator','lean_target','stay_on_fence',
             'declare_neutrality','back_down','accept_sway','reject_sway','toggle_press_war_goal','make_primary_demand','offer_sway','offer_sway_ally','offer_sway_state','offer_sway_subject','offer_sway_pact','offer_sway_subjection',
             'offer_sway_goal_country','offer_sway_goal_state',*(f'offer_sway_{kind}_article' for kind in ('goods','state','region','law')),'add_war_goal_country',
             'add_war_goal_state','add_war_goal_liberation','add_war_goal_article',*(f'add_{kind}_war_goal' for kind in ('goods','state','region','law'))),
    'war':('propose_peace','white_peace','capitulate','toggle_accept_peace'),
    'companies':('create_company','remove_company','toggle_charter','grant_building_charter','revoke_building_charter','grant_region_charter','revoke_region_charter'),
    'expansion':('colonize','toggle_pause_colonization','abandon_colony','incorporate','unincorporate','move_capital','move_market_capital'),
    'journal':('press_journal_button','choose_event_option','take_decision','toggle_ignore_decision'),
    'time':('pause','unpause','set_speed'),
}


GROUP={name:group for group,names in GROUPS.items() for name in names}
