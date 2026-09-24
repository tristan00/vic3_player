from dataclasses import dataclass


TYPES={
    'building':(8,'Building',None),
    'building_type':(9,'BuildingType','common/buildings'),
    'character':(11,'Character',None),
    'combat_unit_type':(15,'CombatUnitType','common/combat_unit_types'),
    'commander_order_type':(16,'CommanderOrderType','common/commander_orders'),
    'company':(17,'Company',None),
    'company_type':(18,'CompanyType','common/company_types'),
    'country':(5,'Country',None),
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
}


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


BULK=(('subsidies','ToggleAllSubsidies'),('auto_expand','ToggleAllAutoExpand'),('privatization','ToggleAllPrivatization'),
      ('remove_privatization','RemoveAllPrivatization'))


TYPE_ITEM=('BuildingBrowserPanel.GetBuildingBrowserBuildingTypeItems','EqualTo_string(BuildingBrowserBuildingTypeItem.GetBuildingType.GetKey, {building_type}.GetKey)')


OPEN_BROWSER=(('InformationPanelBar.OpenBuildingBrowserPanel(GetPlayer.Self)',),((),))


PM_MENU=('gui/switch_production_method_menu.gui','name = "switch_production_method_menu"')


UNFILTERED=(BROWSER,(),lambda values:['BuildingBrowserPanel.ResetAllFilters','BuildingBrowserPanel.StateFilterShowAllStates'])


def bulk(name,command):
    return Action(name,('building_type',),'BuildingBrowserBuildingTypeItem.'+command,datamodels=(TYPE_ITEM,),
                  window=BROWSER,start=OPEN_BROWSER,stages=(UNFILTERED,))


SUBSET=(('subsidies_on','ToggleSubsidiesOn'),('subsidies_off','ToggleSubsidiesOff'),('auto_expand_on','ToggleAutoExpandOn'),('auto_expand_off','ToggleAutoExpandOff'))


def subset(name,command,params):
    return Action(name,tuple(params.split()),'Building.'+command,
                  datamodels=(('BuildingBrowserPanel.GetSortedAndFilteredBuildings','And(EqualTo_string(Building.GetBuildingType.GetKey, {building_type}.GetKey), ObjectsEqual(Building.GetState.GetOwner.Self, GetPlayer.Self))'),),
                  choices=OWNERSHIP,window=BROWSER,start=OPEN_BROWSER,stages=filter_stages(params))


NATIONALIZE_WINDOW=('gui/popups.gui','name = "nationalize_building_window"')
TRANSPORT_PLANNER=('gui/transport_planner.gui','name = "transport_planner_popup"')


def bulk_nationalize(name,params):
    return Action(name,tuple(params.split()),'NationalizeBuildingWindow.NationalizeBuildingGroupsConfirm',valid='NationalizeBuildingWindow.NationalizeBuildingGroupsIsValid',why='NationalizeBuildingWindow.NationalizeBuildingGroupsGetDesc',
                  datamodels=(('',"Not(EqualTo_int32(NationalizeBuildingWindow.GetNumLevelsToNationalize, '(int32)0'))"),),
                  choices=OWNERSHIP,window=NATIONALIZE_WINDOW,cleanup=('PopupManager.HideNationalizeBuildingWindow','InformationPanelBar.ClosePanel','RightClickMenuManager.Close'),start=(('PopupManager.HideNationalizeBuildingWindow',*OPEN_BROWSER[0]),((),)),
                  stages=(*filter_stages(params),(BROWSER,(TYPE_ITEM,),lambda values:['BuildingBrowserBuildingTypeItem.ShowNationalizeBuildingsWindow']),
                          (NATIONALIZE_WINDOW,(('','NationalizeBuildingWindow.HasNationalizableGroup'),),lambda values:['NationalizeBuildingWindow.SetNationalizeToAll'])))


def bulk_method(name,params):
    menu=(TYPE_ITEM,('BuildingBrowserBuildingTypeItem.GetBuildingType.AccessProductionMethodGroups',''),
          ('ProductionMethodGroup.AccessCountryProductionMethods(GetPlayer.Self)','EqualTo_string(ProductionMethod.GetKey, {production_method})'))
    return Action(name,tuple(params.split()),'ChangeProductionMethodMenuItem.Execute',valid='ChangeProductionMethodMenuItem.IsValid',
                  datamodels=(('ChangeProductionMethodsMenuItems.AccessItems','EqualTo_string(ChangeProductionMethodMenuItem.AccessMethod.GetKey, {production_method})'),),
                  choices=OWNERSHIP,window=PM_MENU,start=OPEN_BROWSER,
                  stages=(*filter_stages(params),
                          (BROWSER,menu,lambda values:['BuildingBrowserBuildingTypeItem.ToggleSwitchProductionMethodMenu(ProductionMethodGroup.AccessSelf, PdxGuiWidget.AccessSelf)'])))


MILITARY_PANEL=('gui/panel_military.gui','name = "panel_military"')
OPEN_MILITARY=(("InformationPanelBar.OpenMilitaryPanelTab('army')",),((),))


TRANSFER=('gui/transfer_formation.gui','name = "transfer_formation_popup"')
TARGET_ARMY=(('AccessPlayer.GetMilitaryFormationsArmy','ObjectsEqual(MilitaryFormation.Self, {target}.Self)'),)


SELECT_ARMY=(("InformationPanelBar.OpenMilitaryFormationPanelTab(MilitaryFormation.Self, 'default')",'MilitaryFormation.Select'),FORMATION[:1])
SELECTION="Concatenate(' selected armies: ', ToString_int32(GetNumSelectedArmies))"
SELECT_FLEET=(("InformationPanelBar.OpenMilitaryFormationPanelTab(MilitaryFormation.Self, 'default')",'MilitaryFormation.Select'),FORMATION[1:])
FLEET_SELECTION="Concatenate(' selected fleets: ', ToString_int32(GetNumSelectedFleets))"


def selected(name,params,command):
    return Action(name,tuple(params.split()),command,start=SELECT_ARMY,why=SELECTION)


RENAME_POPUP=('gui/military_formation_panel.gui','name = military_formation_change_name_popup')


OPEN_SHIPS=(("InformationPanelBar.OpenConstructionPanelTab(GetPlayer.Self, 'ships')",),((),))
SHIP_PAGES=('gui/construction_panel.gui','name = "ship_construction_queue_pages"')
SHIP_PAGE=12


def map_list(name,params,target,start,transport=False):
    return Action(name,tuple(params.split()),'MapListOption.OnClick',datamodels=(('',target),),valid='MapListOption.CanClick',why='MapListOption.GetTooltip',window=MAP_LIST,start=((start,'MapListPanelManager.OpenCurrentPanel'),FORMATION[:1]),transport=transport)


EVENT_WINDOW=('gui/eventwindow.gui','datamodel = "[EventWindow.GetOptions]"')


PROPOSALS=('gui/topfrontend.gui','datamodel = "[TopFrontend.AccessProposals]"')
ADD_WAR_GOAL=('gui/add_wargoal_panel.gui','datamodel = "[AddWarGoalPanel.AccessShownWarGoals]"')
ADD_WAR_GOAL_PANEL=('gui/add_wargoal_panel.gui','name = "add_wargoal_panel"')
BLOC_FORMATION=('gui/power_bloc_formation_panel.gui','name = "power_bloc_formation_panel"')
PRINCIPLE_WINDOW=('gui/principle_selection_window.gui','name = "principle_selection_window"')
BLOC_PANEL=('gui/power_bloc_panel.gui','name = "power_bloc_panel"')
DIPLOMATIC_WINDOW=('gui/popups.gui','name = "diplomatic_action_window"')
RELEASE_WINDOW=('gui/popups.gui','name = "release_country_window"')
POLITICS=('gui/politics_panel.gui','name = "politics_panel"')
REFORM=('@PoliticsPanel.AccessReformGovernment','')
PLAY_CONFIRMATION=('gui/popups.gui','name = "diplomatic_play_confirmation"')
DESIGNER=('gui/ship_designer_popup.gui','name = ship_designer_popup')
TEMPLATE_ITEM=(('ShipTemplateList.GetTemplatesOfType({ship_type}.Self)','EqualTo_int32(PdxGuiWidget.AccessParent.GetIndexInDataModel, {index})'),)


PROPOSAL_KINDS=(('treaty','GetTreaty','Proposal.GetTreaty.IsValid',(('accept','AcceptTreatyProposal'),('decline','DeclineTreatyProposal'))),
                ('demand','GetDiplomaticDemand','Proposal.GetDiplomaticDemand.IsValid',(('accept','AcceptDiplomaticDemand'),('reject','RejectDiplomaticDemand'))),
                ('action_proposal','GetDiplomaticAction','Not(Or(Or(Proposal.GetTreaty.IsValid, Proposal.GetDiplomaticDemand.IsValid), Proposal.GetDiplomaticPlay.IsValid))',
                 (('accept','AcceptActionProposal'),('decline','DeclineActionProposal'))),
                ('sway','GetDiplomaticPlay.GetIncomingSway(Proposal.GetActor.Self, Proposal.GetRecipient.Self)',
                 'And(Proposal.GetDiplomaticPlay.IsValid, Not(Or(Proposal.GetTreaty.IsValid, Proposal.GetDiplomaticDemand.IsValid)))',(('accept','AcceptSway'),('reject','RejectSway'))))


CHARACTER_MATCH='ObjectsEqual(Character.Self, {character}.Self)'


CHARACTER_SOURCES=((('@AccessPlayer.AccessRuler',CHARACTER_MATCH),),
                   (('@AccessPlayer.AccessHeir',f'And({CHARACTER_MATCH}, Not(Character.IsRulerOfOwnCountry))'),),
                   (('AccessPlayer.AccessGenerals',f'And({CHARACTER_MATCH}, Not(Or(Character.IsRulerOfOwnCountry, Character.IsHeirOfOwnCountry)))'),),
                   (('AccessPlayer.AccessAdmirals',f'And({CHARACTER_MATCH}, Not(Or(Character.IsRulerOfOwnCountry, Character.IsHeirOfOwnCountry)))'),),
                   (('GetExilePool.GetExiles',CHARACTER_MATCH),),
                   (('AccessPlayer.AccessAllInterestGroups',''),
                    ('@InterestGroup.AccessLeader',f'And({CHARACTER_MATCH}, Not(Or(Or(Character.IsRulerOfOwnCountry, Character.IsHeirOfOwnCountry), Character.IsCommander)))')))


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
    act('auto_expand_on','building','{building}.ToggleAutoExpandOn'),
    act('auto_expand_off','building','{building}.ToggleAutoExpandOff'),
    *(bulk(f'bulk_{name}',command) for name,command in BULK),
    *(subset(f'subset_{name}{suffix}',command,params) for name,command in SUBSET
      for suffix,params in (('','building_type ownership:choice'),('_state','building_type state ownership:choice'))),
    bulk_nationalize('bulk_nationalize','building_type ownership:choice'),
    bulk_nationalize('bulk_nationalize_state','building_type state ownership:choice'),
    bulk_method('bulk_switch_production_method','building_type production_method ownership:choice'),
    bulk_method('bulk_switch_production_method_state','building_type state production_method ownership:choice'),
    act('switch_production_method','building production_method','ProductionMethod.GetSwitch(Building.Self)',context='{building}',
        datamodels=(('Building.AccessProductionMethodGroups',''),
                    ('ProductionMethodGroup.AccessBuildingProductionMethods(Building.Self)','EqualTo_string(ProductionMethod.GetKey, {production_method})'))),
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
    Action('transfer_battalions',('military_formation','target:military_formation'),'TransferFormationPopup.Confirm',window=TRANSFER,
           start=(('PopupManager.ShowTransferFormation(MilitaryFormation.AccessSelf)',),FORMATION[:1]),cleanup=('PopupManager.HideTransferFormation',),
           stages=((TRANSFER,FORMATION[0],lambda values:['TransferFormationPopup.SetSelectedLeftFormation(MilitaryFormation.AccessSelf)']),
                   (TRANSFER,TARGET_ARMY,lambda values:['TransferFormationPopup.SetSelectedRightFormation(MilitaryFormation.AccessSelf)']),
                   (TRANSFER,(),lambda values:["TransferFormationPopup.MovePercentageRight('(int32)50')"]))),
    Action('deploy_selected_to_front',('military_formation','front:int'),'Front.GetDeploySelectedFormationsCommand',start=SELECT_ARMY,why=SELECTION,
           datamodels=(('AccessPlayer.AccessWars',''),('War.AccessFronts','EqualTo_string(ToString_uint32(Front.GetID), ToString_int32({front}))'))),
    Action('station_selected',('military_formation','strategic_region'),'Hq.GetStationSelectedFormationsCommand',start=SELECT_ARMY,why=SELECTION,transport=True,
           overseas=('Hq.GetStates','State.RequiresNavalTransportForSelectedFormations','State.ShowTransportPlannerForSelectedFormation'),
           datamodels=(('AccessPlayer.AccessLandHQs','ObjectsEqual(Hq.GetStrategicRegion.Self, {strategic_region}.Self)'),)),
    Action('set_formation_flag',('military_formation','flag:int'),'MilitaryFormationChangeNamePopup.Confirm',window=RENAME_POPUP,
           start=(('PopupManager.ShowMilitaryFormationChangeName(MilitaryFormation.Self)',),FORMATION[:1]),cleanup=('PopupManager.HideMilitaryFormationChangeName',),
           stages=((RENAME_POPUP,(('MilitaryFormationChangeNamePopup.GetArmyFormationFlags','EqualTo_int32(PdxGuiWidget.AccessParent.GetIndexInDataModel, {flag})'),),
                    lambda values:['MilitaryFormationChangeNamePopup.OnSelectFlag(MilitaryFormationFlag.AccessSelf)']),)),
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
        valid='Character.GetInteraction({interaction}).IsCommandValid(Character.Self)',alternatives=CHARACTER_SOURCES),
    act('diplomatic_action','country diplomatic_action','GetCountryDiplomaticAction({diplomatic_action}, GetPlayer.Self, {country}.Self).ExecuteAction'),
    Action('diplomatic_action_state',('country','diplomatic_action','state','side:choice'),'DiplomaticActionWindow.ExecuteAction',choices=('First','Second'),
           window=DIPLOMATIC_WINDOW,cleanup=('DiplomaticActionWindow.ClearStateSelectionTarget','PopupManager.HideDiplomaticActionConfirmation'),
           start=(('GetCountryDiplomaticAction({diplomatic_action}, GetPlayer.Self, {country}.Self).ExecuteWithConfirmation',),((),)),
           stages=((DIPLOMATIC_WINDOW,(('@DiplomaticActionWindow.GetDiplomaticAction',''),),lambda values:['DiplomaticActionWindow.SetStateSelectionTarget(DiplomaticAction.Get{side}Country)']),
                   (DIPLOMATIC_WINDOW,(('DiplomaticActionWindow.AccessPossibleStates','ObjectsEqual(State.Self, {state}.Self)'),),
                    lambda values:['DiplomaticActionWindow.SelectState(State.Self)']))),
    Action('diplomatic_action_obligation',('country','diplomatic_action','obligation:choice'),'DiplomaticActionWindow.ExecuteAction',choices=('CallInObligation','OweObligation'),
           window=DIPLOMATIC_WINDOW,cleanup=('PopupManager.HideDiplomaticActionConfirmation',),
           start=(('GetCountryDiplomaticAction({diplomatic_action}, GetPlayer.Self, {country}.Self).ExecuteWithConfirmation',),((),)),
           stages=((DIPLOMATIC_WINDOW,(),lambda values:['DiplomaticActionWindow.Toggle{obligation}']),)),
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
    Action('add_war_goal',('diplomatic_play','war_goal_type','index:int'),'AddWarGoalPanel.AccessDiplomaticPlay.AddWarGoal(WarGoalDraft.Self)',
           datamodels=(('','EqualTo_int32(PdxGuiWidget.AccessParent.GetIndexInDataModel, {index})'),),
           why='AddWarGoalPanel.GetDiplomaticPlay.GetCanAddWarGoalDesc(WarGoalDraft.Self)',
           window=ADD_WAR_GOAL,cleanup=('InformationPanelBar.ClosePanel',),
           start=(('InformationPanelBar.OpenAddWarGoalPanel(DiplomaticPlay.Self, GetPlayer.Self)',),
                  ((('AccessPlayer.AccessActiveDiplomaticPlays','ObjectsEqual(DiplomaticPlay.Self, {diplomatic_play}.Self)'),),)),
           stages=((ADD_WAR_GOAL_PANEL,(('AddWarGoalPanel.AccessShownWarGoalTypes','ObjectsEqual(WarGoalType.Self, {war_goal_type}.Self)'),),
                    lambda values:['AddWarGoalPanel.SetSelectedWarGoalType(WarGoalType.Self)']),)),
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
    Action('pick_principle',('slot:int','power_bloc_principle'),'PowerBlocPrincipleSelectionWindow.SubmitPrincipleSelection',window=PRINCIPLE_WINDOW,
           start=(('InformationPanelBar.OpenPowerBlocPanel(GetPlayer.GetPowerBloc.Self)',),((),)),
           cleanup=('PopupManager.HidePowerBlocPrincipleSelectionWindow','InformationPanelBar.ClosePanel'),
           stages=((BLOC_PANEL,(('@PowerBlocPanel.GetPrincipleSlot({slot})',''),),lambda values:['PowerBlocPanel.ToggleSelectionWindow(PowerBlocPrincipleSlot.AccessSelf)']),
                   (PRINCIPLE_WINDOW,(('PowerBlocPrincipleSelectionWindow.GetAvailableGroups',''),('PowerBlocPrincipleGroup.GetLevels','ObjectsEqual(PowerBlocPrinciple.Self, {power_bloc_principle}.Self)')),
                    lambda values:['PowerBlocPrincipleSelectionWindow.TogglePrincipleSelection(PowerBlocPrinciple.Self)']))),
    act('upgrade_principle','power_bloc_principle','PowerBlocPrinciple.UpgradeToNextLevel',
        datamodels=(('AccessPlayer.AccessPowerBloc.GetPrinciples','ObjectsEqual(PowerBlocPrinciple.Self, {power_bloc_principle}.Self)'),)),
    act('create_company','company_type','GetPlayer.CreateCompany({company_type}.Self)'),
    act('remove_company','company_type','GetPlayer.RemoveCompany({company_type}.Self)'),
    act('toggle_charter','company charter','Company.ToggleCharter(CompanyCharterType.Self)',
        datamodels=(('AccessPlayer.GetCompanies','ObjectsEqual(Company.Self, {company}.Self)'),
                    ('GetCompanyCharterTypes','EqualTo_string(CompanyCharterType.GetNameNoFormatting, GetCompanyCharterType({charter}).GetNameNoFormatting)'))),
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
    act('pause','','TimeKeeper.TogglePause',valid='And(TimeKeeper.CanTogglePause, Not(TimeKeeper.IsPaused))',why=TIME_WHY),
    act('unpause','','TimeKeeper.TogglePause',valid='And(TimeKeeper.CanTogglePause, TimeKeeper.IsPaused)',why=TIME_WHY),
    act('set_speed','speed:choice',"TimeKeeper.SetGameSpeed('(int32){speed}')",valid='TimeKeeper.CanSetGameSpeed',choices=('0','1','2','3','4')),
    act('take_decision','decision','Decision.TakeDecision(GetPlayer)',
        datamodels=(('AccessPlayer.GetDecisions','EqualTo_string(Decision.GetName, Localize({decision}))'),)),
    act('toggle_ignore_formable','index:int','GetPlayer.ToggleIgnoreCountryFormation(CountryFormation.Self)',
        datamodels=(('AccessPlayer.AccessFormableCountries','EqualTo_int32(PdxGuiWidget.GetIndexInDataModel, {index})'),)),
    act('form_country','index:int','CountryFormation.FormCountry(GetPlayer)',
        datamodels=(('AccessPlayer.AccessFormableCountries','EqualTo_int32(PdxGuiWidget.GetIndexInDataModel, {index})'),)),
    Action('release_country',('index:int',),'ReleaseCountryWindow.ReleaseCountry',window=RELEASE_WINDOW,cleanup=('PopupManager.HideReleaseCountryConfirmation',),
           start=(('PopupManager.ShowReleaseCountryConfirmation(CountryCreation.Self)',),
                  ((('AccessPlayer.AccessReleasableCountries','EqualTo_int32(PdxGuiWidget.GetIndexInDataModel, {index})'),),))),
    act('toggle_ignore_decision','decision','GetPlayer.ToggleIgnoreDecision(Decision.Self)',
        datamodels=(('AccessPlayer.GetDecisions','EqualTo_string(Decision.GetName, Localize({decision}))'),)),
)


BY_NAME={action.name:action for action in ACTIONS}


GROUPS={
    'construction':('build','cancel_construction','downsize','pause_construction','resume_construction','pause_all_construction','resume_all_construction','pause_construction_output','resume_construction_output',
                    'cancel_queue_item','raise_queue_item','lower_queue_item','first_queue_item','last_queue_item'),
    'buildings':('nationalize','toggle_privatization','toggle_monopoly','subsidies_on','subsidies_off',
                 'auto_expand_on','auto_expand_off','switch_production_method',
                 *(f'bulk_{name}' for name,_ in BULK),*(f'subset_{name}{suffix}' for name,_ in SUBSET for suffix in ('','_state')),
                 'bulk_switch_production_method','bulk_switch_production_method_state','bulk_nationalize','bulk_nationalize_state'),
    'budget':('set_tax_level','set_government_wages','set_military_wages','toggle_consumption_tax','set_import_tariff','set_export_tariff',
              'set_import_subvention','set_export_subvention','declare_bankruptcy','set_strait_toll','set_strait_access','set_strait_allowed'),
    'politics':('enact_law','cancel_enactment','impose_law','repeal_amendment','toggle_bolster_movement','toggle_suppress_movement','negotiate','reform_government',
                'set_institution_level','stop_institution_change','issue_decree','remove_decree'),
    'research':('research','queue_research','dequeue_research'),
    'army':('defend_invasion','set_formation_flag','station_selected','deploy_selected_to_front','mobilize_selected','demobilize_selected','raise_conscripts_selected','cancel_strategic_objective_selected','set_borrow_setting','transfer_battalions','upgrade_all_units','create_army','recruit_from_formation','activate_conscription_center','disembark','deploy_to_front','station_formation','rehome_formation','set_strategic_objective','cancel_invasion','recruit','mobilize','demobilize','raise_conscripts','disband_formation','mobilize_all','demobilize_all','toggle_mobilization_option',
            'set_supply_priority','disband_regulars','disband_conscripts','upgrade_regulars','upgrade_conscripts','set_default_unit_type'),
    'navy':('recall_fleet','raise_ship_item','lower_ship_item','first_ship_item','last_ship_item','cancel_ship_item','set_default_construction_fleet','clear_default_construction_fleet','decommission_ship','build_ship','build_ship_for','cancel_ship','start_naval_mission','end_naval_mission','start_naval_mission_selected','end_naval_mission_selected','pause_ship_construction','resume_ship_construction','set_supply_ship_construction','design_ship_template','edit_ship_template','retrofit_fleet','cancel_retrofit_fleet','retrofit_all','cancel_retrofit_all',
            'set_default_ship_template','set_fleet_ship_template','delete_ship_template'),
    'characters':('commander_order','hire_commander','hire_commander_for','promote_commander','assign_commander','unassign_commander','character_interaction'),
    'diplomacy':('diplomatic_action','diplomatic_action_obligation','diplomatic_action_state','start_play_confirmed','withdraw_treaty','accept_treaty','decline_treaty','accept_demand','reject_demand','accept_action_proposal',
                 'decline_action_proposal','quick_decline_proposal','request_join_power_bloc','form_power_bloc','kick_from_power_bloc','leave_power_bloc','upgrade_principle','pick_principle'),
    'plays':('start_play_country','start_play_state','support_initiator','support_target','lean_initiator','lean_target','stay_on_fence',
             'declare_neutrality','back_down','accept_sway','reject_sway','toggle_press_war_goal','make_primary_demand','add_war_goal'),
    'war':('propose_peace','white_peace','capitulate','toggle_accept_peace'),
    'companies':('create_company','remove_company','toggle_charter'),
    'expansion':('colonize','toggle_pause_colonization','abandon_colony','incorporate','unincorporate'),
    'journal':('press_journal_button','choose_event_option','take_decision','toggle_ignore_decision','toggle_ignore_formable','form_country','release_country'),
    'time':('pause','unpause','set_speed'),
}


GROUP={name:group for group,names in GROUPS.items() for name in names}
