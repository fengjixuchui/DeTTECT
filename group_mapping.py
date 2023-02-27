import simplejson
from eql_yaml import techniques_search
from generic import *
from navigator_layer import *
from file_output import *

CG_GROUPS = {}


def _is_in_group(json_groups, argument_groups):
    """
    Check if the two dicts (json_groups and argument_groups) have any groups in common based on their names/aliases.
    :param json_groups: group aliases from ATT&CK
    :param argument_groups: group names provided via the command line by the user
    :return: true or false
    """
    if json_groups:
        json_groups = list(map(lambda x: x.lower(), json_groups))

        for group in argument_groups:
            if group in json_groups:
                return True

    return False


def _are_groups_found(groups_found, argument_groups):
    """
    Check if the groups that are provided using '-g/--groups'/'-o/--overlay' are present within MITRE ATT&CK.
    :param groups_found: groups that are found in the ATT&CK data
    :param argument_groups: groups provided via the command line by the user
    :return: returns boolean that indicates if all of the groups are found
    """
    group_attack_data = load_attack_data(DATA_TYPE_STIX_ALL_GROUPS)
    group_found = True

    for group_arg in argument_groups:
        if group_arg == 'all':  # this one will be ignored as it does not make any sense for this function
            return True

        group_id = None
        for group in group_attack_data:  # is the group provided via the command line known in ATT&CK?
            group_aliases_lower = []
            if 'aliases' in group:
                group_aliases_lower = list(map(lambda x: x.lower(), group['aliases']))
            if group_arg in group_aliases_lower or group_arg == get_attack_id(group).lower() or group_arg == group['name'].lower():
                group_id = get_attack_id(group)
        if not group_id:  # the group that has been provided through the command line cannot be found in ATT&CK
            print('[!] Unknown ATT&CK group: ' + group_arg)
            group_found = False
        elif group_id not in groups_found:  # group not present in filtered (platform) data set
            print('[!] Group not part of the data set: ' + group_arg)
            group_found = False

    return group_found


def _are_campaigns_found(campaigns_found, argument_campaigns):
    """
    Check if the campaigns that are provided using -c/--campaigns or -o/--overlay are present within MITRE ATT&CK.
    :param campaigns_found: campaigns that are found in the ATT&CK data
    :param argument_campaigns: campaigns provided via the command line by the user
    :return: returns boolean that indicates if all of the groups are found
    """
    campaign_attack_data = load_attack_data(DATA_TYPE_STIX_ALL_CAMPAIGNS)
    campaign_found = True

    for campaign_arg in argument_campaigns:
        if campaign_arg == 'all':  # this one will be ignored as it does not make any sense for this function
            return True

        campaign_id = None
        for campaign in campaign_attack_data:  # is the campaign provided via the command line known in ATT&CK?
            if campaign_arg == get_attack_id(campaign).lower() or campaign_arg == campaign['name'].lower():
                campaign_id = get_attack_id(campaign)
        if not campaign_id:  # the campaign that has been provided through the command line cannot be found in ATT&CK
            print('[!] Unknown ATT&CK campaign: ' + campaign_arg)
            campaign_found = False
        elif campaign_id not in campaigns_found:  # group not present in filtered (platform) data set
            print('[!] Campaign not part of the data set: ' + campaign_arg)
            campaign_found = False

    return campaign_found


def _get_software_techniques(groups, campaigns, platform, domain):
    """
    Get all techniques (in a dict) from the provided list of groups in relation to the software these groups use,
    and hence techniques they support.
    :param groups: ATT&CK groups
    :param campaigns: ATT&CK campaigns
    :param platform: one or multiple values from PLATFORMS constant
    :param domain: the specified domain
    :return: dictionary with info on groups
    """
    # { group_id: {group_name: NAME, techniques: set{id, ...} } }
    groups_dict = {}

    tech_by_software = load_attack_data(DATA_TYPE_CUSTOM_TECH_BY_SOFTWARE)

    # { software_id: [technique, ...] }
    software_dict = {}
    for tech in tech_by_software:
        if tech['software_id'] not in software_dict:
            # noinspection PySetFunctionToLiteral
            software_dict[tech['software_id']] = set([tech['technique_id']])
        else:
            software_dict[tech['software_id']].add(tech['technique_id'])

    # groups is a YAML file
    if os.path.isfile(str(groups)):
        _yaml = init_yaml()
        with open(groups, 'r') as yaml_file:
            config = _yaml.load(yaml_file)

        for group in config['groups']:
            if group['enabled']:
                campaign = group.get('campaign', None)
                campaign = str(campaign) if campaign else ''
                group_id = _generate_group_id(str(group['group_name']), campaign)
                groups_dict[group_id] = dict()

                groups_dict[group_id]['group_name'] = str(group['group_name'])
                groups_dict[group_id]['techniques'] = set()
                if campaign != '':
                    groups_dict[group_id]['campaign'] = str(campaign)
                groups_dict[group_id]['software'] = group.get('software_id', None)

                if 'software_id' in group and group['software_id']:
                    for soft_id in group['software_id']:
                        try:
                            groups_dict[group_id]['techniques'].update(software_dict[soft_id])
                        except KeyError:
                            print('[!] Unknown ATT&CK software ID: ' + soft_id)

    # groups are provided as arguments via the command line
    else:
        if groups is not None:
            software_by_group = load_attack_data(DATA_TYPE_CUSTOM_SOFTWARE_BY_GROUP)
            for s in software_by_group:
                # software matches the ATT&CK Matrix and platform
                # and the group is a group we are interested in
                if s['x_mitre_platforms']:  # there is software that do not have a platform, skip those
                    if domain in s['x_mitre_domains'] and len(set(s['x_mitre_platforms']).intersection(set(platform))) > 0 and \
                            (groups[0] == 'all' or s['group_id'].lower() in groups or _is_in_group(s['aliases'], groups) or s['name'].lower() in groups):
                        if s['group_id'] not in groups_dict:
                            groups_dict[s['group_id']] = {'group_name': s['name']}
                            groups_dict[s['group_id']]['techniques'] = set()
                            groups_dict[s['group_id']]['weight'] = dict()
                        groups_dict[s['group_id']]['techniques'].update(software_dict[s['software_id']])
                        for t in groups_dict[s['group_id']]['techniques']:
                            groups_dict[s['group_id']]['weight'][t] = 1

        if campaigns is not None:
            software_in_campaign = load_attack_data(DATA_TYPE_CUSTOM_SOFTWARE_IN_CAMPAIGN)
            for s in software_in_campaign:
                # software matches the ATT&CK Matrix and platform
                # and the campaign is a campaign we are interested in
                if s['x_mitre_platforms']:  # there is software that do not have a platform, skip those
                    if domain in s['x_mitre_domains'] and len(set(s['x_mitre_platforms']).intersection(set(platform))) > 0 and \
                            (campaigns[0] == 'all' or s['campaign_id'].lower() in campaigns or s['name'].lower() in campaigns):
                        if s['campaign_id'] not in groups_dict:
                            groups_dict[s['campaign_id']] = {'group_name': s['name']}
                            groups_dict[s['campaign_id']]['techniques'] = set()
                            groups_dict[s['campaign_id']]['weight'] = dict()
                        groups_dict[s['campaign_id']]['techniques'].update(software_dict[s['software_id']])
                        for t in groups_dict[s['campaign_id']]['techniques']:
                            groups_dict[s['campaign_id']]['weight'][t] = 1

    return groups_dict


def _generate_group_id(group_name, campaign):
    # CG_GROUPS = { group_name+campaign: id } }
    """
    Generate a custom group id.
    :param group_name: group name as used within the YAML file
    :param campaign: campaign as used within the YAML file
    :return: custom group identifier string (e.g. CG0001)
    """
    global CG_GROUPS

    if not CG_GROUPS:
        new_id = 1
    elif group_name + campaign not in CG_GROUPS:
        new_id = len(CG_GROUPS) + 1

    if group_name + campaign not in CG_GROUPS:
        length = len(str(new_id))
        if length > 9:
            cg_id = 'CG00' + str(new_id)
        elif length > 99:
            cg_id = 'CG0' + str(new_id)
        elif length > 999:
            cg_id = 'CG' + str(new_id)
        else:
            cg_id = 'CG000' + str(new_id)

        CG_GROUPS[group_name + campaign] = cg_id

    return CG_GROUPS[group_name + campaign]


def _get_group_techniques(groups, platform, file_type, domain):
    """
    Get all techniques (in a dict) from the provided list of groups
    :param groups: group ID, group name/alias or a YAML file with group(s) data
    :param platform: one or multiple values from PLATFORMS constant
    :param file_type: the file type of the YAML file as present in the key 'file_type'
    :param domain: the specified domain
    :return: returns dictionary with all techniques from the provided list of groups or -1 when group is not found
    """
    if groups is None:
        return {}

    # { group_id: {group_name: NAME, techniques: set{id, ...} } }
    groups_dict = {}
    groups_found = set()

    # groups is a YAML file
    if file_type == FILE_TYPE_GROUP_ADMINISTRATION:
        _yaml = init_yaml()
        with open(groups, 'r') as yaml_file:
            config = _yaml.load(yaml_file)

        domain_in_file = 'enterprise-attack' if 'domain' not in config.keys() else config['domain']
        if domain_in_file != domain:
            print('[!] The domain specified in the overlay YAML file conflicts with the given value for the -d/--domain argument, or the domain specified in the Group YAML file.')
            return -1

        for group in config['groups']:
            if group['enabled']:
                campaign = group.get('campaign', None)
                campaign = str(campaign) if campaign else ''
                group_id = _generate_group_id(str(group['group_name']), campaign)
                groups_dict[group_id] = dict()

                groups_dict[group_id]['group_name'] = str(group['group_name'])
                if isinstance(group['technique_id'], list):
                    groups_dict[group_id]['techniques'] = set(group['technique_id'])
                    groups_dict[group_id]['weight'] = dict((i, 1) for i in group['technique_id'])
                elif isinstance(group['technique_id'], dict):
                    groups_dict[group_id]['techniques'] = set(group['technique_id'].keys())
                    groups_dict[group_id]['weight'] = group['technique_id']
                if campaign != '':
                    groups_dict[group_id]['campaign'] = str(campaign)
                groups_dict[group_id]['software'] = group.get('software_id', None)
    else:
        # groups are provided as arguments via the command line
        all_groups_tech = load_attack_data(DATA_TYPE_CUSTOM_TECH_BY_GROUP)

        for gr in all_groups_tech:
            platforms = gr['x_mitre_platforms']
            if not platforms:
                # we just set this to an random legit value, because for pre-attack 'platform' is not used
                platforms = ['Windows']

            # group matches the: matrix/stage, platform and the group(s) we are interested in
            if domain in gr['x_mitre_domains'] and len(set(platforms).intersection(set(platform))) > 0 and \
                    (groups[0] == 'all' or gr['group_id'].lower() in groups or _is_in_group(gr['aliases'], groups) or gr['name'].lower() in groups):
                if gr['group_id'] not in groups_dict:
                    groups_found.add(gr['group_id'])
                    groups_dict[gr['group_id']] = {'group_name': gr['name']}
                    groups_dict[gr['group_id']]['techniques'] = set()
                    groups_dict[gr['group_id']]['weight'] = dict()

                groups_dict[gr['group_id']]['techniques'].add(gr['technique_id'])
                groups_dict[gr['group_id']]['weight'][gr['technique_id']] = 1

        # do not call '_are_groups_found' when groups is a YAML file
        # (this could contain groups that do not exists within ATT&CK)
        if not os.path.isfile(str(groups)):
            found = _are_groups_found(groups_found, groups)
            if not found:
                return -1

    return groups_dict


def _get_campaign_techniques(campaigns, platform, domain):
    """
    Get all techniques (in a dict) from the provided list of campaigns. Uses the groups data structure to fit in campaigns.
    :param campaigns: campaign ID or name
    :param platform: one or multiple values from PLATFORMS constant
    :param domain: the specified domain
    :return: returns dictionary with all techniques from the provided list of campaigns or -1 when campaign is not found
    """
    if campaigns is None:
        return {}

    # { group_id: {group_name: NAME, techniques: set{id, ...} } }
    groups_dict = {}
    campaigns_found = set()

    all_campaigns = load_attack_data(DATA_TYPE_CUSTOM_TECH_IN_CAMPAIGN)

    for c in all_campaigns:
        platforms = c['x_mitre_platforms']
        if not platforms:
            # we just set this to an random legit value, because for pre-attack 'platform' is not used
            platforms = ['Windows']

        # campaign matches the: matrix/stage, platform and the campaign(s) we are interested in
        if domain in c['x_mitre_domains'] and len(set(platforms).intersection(set(platform))) > 0 and \
                (campaigns[0] == 'all' or c['campaign_id'].lower() in campaigns or c['name'].lower() in campaigns):
            if c['campaign_id'] not in groups_dict:
                campaigns_found.add(c['campaign_id'])
                groups_dict[c['campaign_id']] = {'group_name': c['name']}
                groups_dict[c['campaign_id']]['techniques'] = set()
                groups_dict[c['campaign_id']]['weight'] = dict()

            groups_dict[c['campaign_id']]['techniques'].add(c['technique_id'])
            groups_dict[c['campaign_id']]['weight'][c['technique_id']] = 1

    found = _are_campaigns_found(campaigns_found, campaigns)
    if not found:
        return -1

    return groups_dict


def _get_detection_techniques(filename):
    """
    Get all techniques (in a dict) from the detection administration
    :param filename: path to the YAML technique administration file
    :return: groups dictionary, loaded techniques from administration YAML file
    """
    # { group_id: {group_name: NAME, techniques: set{id, ...} } }
    groups_dict = {}

    detection_techniques, name, platform, domain = load_techniques(filename)

    group_id = 'DETECTION'
    groups_dict[group_id] = {}
    groups_dict[group_id]['group_name'] = 'Detection'
    groups_dict[group_id]['techniques'] = set()
    groups_dict[group_id]['weight'] = dict()
    for t, v in detection_techniques.items():
        s = calculate_score(v['detection'], zero_value=-1)
        if s >= 0:
            groups_dict[group_id]['techniques'].add(t)
            groups_dict[group_id]['weight'][t] = 1

    return groups_dict, detection_techniques, domain


def _get_visibility_techniques(filename):
    """
    Get all techniques (in a dict) from the technique administration
    :param filename: path to the YAML technique administration file
    :return: dictionary
    """
    # { group_id: {group_name: NAME, techniques: set{id, ...} } }
    groups_dict = {}

    visibility_techniques, name, platform, domain = load_techniques(filename)

    group_id = 'VISIBILITY'
    groups_dict[group_id] = {}
    groups_dict[group_id]['group_name'] = 'Visibility'
    groups_dict[group_id]['techniques'] = set()
    groups_dict[group_id]['weight'] = dict()
    for t, v in visibility_techniques.items():
        s = calculate_score(v['visibility'])
        if s > 0:
            groups_dict[group_id]['techniques'].add(t)
            groups_dict[group_id]['weight'][t] = 1

    return groups_dict, visibility_techniques, domain


def _get_technique_count(groups, groups_overlay, groups_software, overlay_type, all_techniques):
    """
    Create a dict with all involved techniques and their relevant count/score
    :param groups: a dict with data on groups/campaigns
    :param groups_overlay: a dict with data on the groups/campaigns to overlay
    :param groups_software: a dict with with data on which techniques are used within related software
    :param overlay_type: group, campaign, visibility or detection
    :param all_techniques: dict containing all technique data for visibility or detection
    :return: dictionary, max_count
    """
    # { technique_id: {count: ..., groups: set{} }
    techniques_dict = {}

    for group, v in groups.items():
        for tech in v['techniques']:
            if tech not in techniques_dict:
                techniques_dict[tech] = dict()
                techniques_dict[tech]['groups'] = set()
                techniques_dict[tech]['count'] = v['weight'][tech]

            # We only want to increase the score when comparing groups/campaigns and not for visibility or detection.
            # This allows to have proper sorting of the heat map, which in turn improves the ability to visually
            # compare this heat map with the detection/visibility ATT&CK Navigator layers.
            else:
                techniques_dict[tech]['count'] += v['weight'][tech]
            techniques_dict[tech]['groups'].add(group)

    max_count = max(techniques_dict.values(), key=lambda k: k['count'])['count']

    # create dict {tech_id: score+max_tech_count} to be used for when doing an overlay of the type visibility or detection
    if overlay_type not in [OVERLAY_TYPE_GROUP, OVERLAY_TYPE_CAMPAIGN]:
        dict_tech_score = {}
        list_tech = groups_overlay[overlay_type.upper()]['techniques']
        for tech in list_tech:
            if overlay_type == OVERLAY_TYPE_VISIBILITY:
                dict_tech_score[tech] = calculate_score(all_techniques[tech]['visibility']) + max_count
            elif overlay_type == OVERLAY_TYPE_DETECTION:
                dict_tech_score[tech] = calculate_score(all_techniques[tech]['detection'], zero_value=-1) + max_count

    for group, v in groups_overlay.items():
        for tech in v['techniques']:
            if tech not in techniques_dict:
                techniques_dict[tech] = dict()
                techniques_dict[tech]['groups'] = set()
                if overlay_type in [OVERLAY_TYPE_GROUP, OVERLAY_TYPE_CAMPAIGN]:
                    techniques_dict[tech]['count'] = v['weight'][tech]
                else:
                    techniques_dict[tech]['count'] = dict_tech_score[tech]
            elif group in groups:
                if tech not in groups[group]['techniques']:
                    if overlay_type in [OVERLAY_TYPE_GROUP, OVERLAY_TYPE_CAMPAIGN]:
                        techniques_dict[tech]['count'] += v['weight'][tech]
                    else:
                        techniques_dict[tech]['count'] = dict_tech_score[tech]
                    # Only do this when it was not already counted by being part of 'groups'.
                    # Meaning the group in 'groups_overlay' was also part of 'groups' (match on Group ID) and the
                    # technique was already counted for that group / it is not a new technique for that group coming
                    # from a YAML file
            else:
                if overlay_type in [OVERLAY_TYPE_GROUP, OVERLAY_TYPE_CAMPAIGN]:
                    # increase count when the group in the YAML file is a custom group
                    techniques_dict[tech]['count'] += v['weight'][tech]
                else:
                    techniques_dict[tech]['count'] = dict_tech_score[tech]

            techniques_dict[tech]['groups'].add(group)

    for group, v in groups_software.items():
        for tech in v['techniques']:
            if tech not in techniques_dict:
                techniques_dict[tech] = dict()
                techniques_dict[tech]['count'] = 0
                # we will not adjust the scoring for groups_software. We will just set the the score to 0.
                # This will later be used for the colouring of the heat map.
            if 'groups' not in techniques_dict[tech]:
                techniques_dict[tech]['groups'] = set()
            techniques_dict[tech]['groups'].add(group)

    return techniques_dict, max_count


def _get_technique_layer(techniques_count, groups, overlay, groups_software, overlay_file_type, overlay_type,
                         all_techniques, count_detections):
    """
    Create the technique layer that will be part of the ATT&CK navigator json file
    :param techniques_count: involved techniques with count (to be used within the scores)
    :param groups: a dict with data on groups
    :param overlay: a dict with data on the groups to overlay
    :param groups_software: a dict with with data on which techniques are used within related software
    :param overlay_file_type: the file type of the YAML file as present in the key 'file_type'
    :param overlay_type: group, visibility or detection
    :param all_techniques: dictionary with all techniques loaded from techniques administration YAML file
    :param count_detections: option for the Navigator layer output: count detections instead of listing detections
    :return: dictionary
    """
    techniques_layer = []

    group_campaign_title = 'Group / Campaign'

    # { technique_id: {count: ..., groups: set{} }
    # add the technique count/scoring
    for tech, v in techniques_count.items():
        t = dict()
        t['techniqueID'] = tech
        t['score'] = v['count']
        t['metadata'] = []
        metadata_dict = dict()

        for group, values in groups.items():
            if tech in values['techniques']:  # we do not color this one because that's done using the scoring
                if group_campaign_title not in metadata_dict:
                    metadata_dict[group_campaign_title] = set()
                metadata_dict[group_campaign_title].add(values['group_name'])

                # this will only be effective when loading a YAML files that have a value for the key 'campaign'
                if 'campaign' in values:
                    if 'Campaign' not in metadata_dict:
                        metadata_dict['Campaign'] = set()
                    metadata_dict['Campaign'].add(values['campaign'])

        # change the color and add metadata to make the groups overlay visible
        for group, values in overlay.items():
            if tech in values['techniques']:
                # Determine color:
                if len(v['groups'].intersection(set(groups.keys()))) > 0:
                    # if the technique is both present in the group (-g/--groups) and the groups overlay (-o/--overlay)
                    metadata_dict[group_campaign_title].add(values['group_name'])

                    # determine the color of the overlay:
                    # - using groups, it's normal orange
                    # - using detections, it's 6 variations or orange (score 0 to 5)
                    # - using visibility, it's 4 variations of orange (score 1 to 4)
                    if overlay_file_type == FILE_TYPE_TECHNIQUE_ADMINISTRATION:
                        if overlay_type == OVERLAY_TYPE_VISIBILITY:
                            s = calculate_score(all_techniques[tech]['visibility'])
                            t['color'] = COLOR_O_1 if s == 1 else COLOR_O_2 if s == 2 else COLOR_O_3 if s == 3 else COLOR_O_4 if s == 4 else ''
                        elif overlay_type == OVERLAY_TYPE_DETECTION:
                            s = calculate_score(all_techniques[tech]['detection'], zero_value=-1)
                            t['color'] = COLOR_O_0 if s == 0 else COLOR_O_1 if s == 1 else COLOR_O_2 if s == 2 else COLOR_O_3 if s == 3 else COLOR_O_4 if s == 4 else COLOR_O_5 if s == 5 else ''
                    else:
                        t['color'] = COLOR_GROUP_OVERLAY_MATCH
                else:
                    # the technique is only present in the overlay and not in the provided groups (-g/--groups)
                    if overlay_file_type == FILE_TYPE_TECHNIQUE_ADMINISTRATION:
                        if overlay_type == OVERLAY_TYPE_VISIBILITY:
                            s = calculate_score(all_techniques[tech]['visibility'])
                            t['color'] = COLOR_V_1 if s == 1 else COLOR_V_2 if s == 2 else COLOR_V_3 if s == 3 else COLOR_V_4 if s == 4 else ''
                        elif overlay_type == OVERLAY_TYPE_DETECTION:
                            s = calculate_score(all_techniques[tech]['detection'], zero_value=-1)
                            t['color'] = COLOR_D_0 if s == 0 else COLOR_D_1 if s == 1 else COLOR_D_2 if s == 2 else COLOR_D_3 if s == 3 else COLOR_D_4 if s == 4 else COLOR_D_5 if s == 5 else ''
                    else:
                        t['color'] = COLOR_GROUP_OVERLAY_NO_MATCH
                        if group_campaign_title not in metadata_dict:
                            metadata_dict[group_campaign_title] = set()
                        metadata_dict[group_campaign_title].add(values['group_name'])

                # Add applicable_to to metadata in case of overlay for detection/visibility:
                if overlay_file_type == FILE_TYPE_TECHNIQUE_ADMINISTRATION:
                    t['metadata'].append({'name': 'Overlay', 'value': overlay_type})
                    for obj_type in ['detection', 'visibility']:
                        t['metadata'] = add_metadata_technique_object(all_techniques[tech], obj_type, t['metadata'], count_detections)

        # change the color and add metadata to make the groups software overlay visible
        for group, values in groups_software.items():
            if tech in values['techniques']:
                if t['score'] > 0:
                    t['color'] = COLOR_GROUP_AND_SOFTWARE
                else:
                    t['color'] = COLOR_SOFTWARE

                if 'Software groups' not in metadata_dict:
                    metadata_dict['Software groups'] = set()
                metadata_dict['Software groups'].add(values['group_name'])
                if 'campaign' in values:
                    if 'Software campaign' not in metadata_dict:
                        metadata_dict['Software campaign'] = set()
                    metadata_dict['Software campaign'].add(values['campaign'])

        # create the metadata based on the dict 'metadata_dict'
        i = 0
        for metadata, values in metadata_dict.items():
            tmp_dict = {'name': metadata, 'value': ', '.join(values)}
            t['metadata'].insert(i, tmp_dict)
            i += 1

        t['metadata'] = make_layer_metadata_compliant(t['metadata'])
        techniques_layer.append(t)

    determine_and_set_show_sub_techniques(techniques_layer)

    return techniques_layer


def _get_group_list(groups, file_type):
    """
    Make a list of group names for the involved groups.
    :param groups: a dict with data on groups
    :param file_type: the file type of the YAML file as present in the key 'file_type'
    :return: list
    """
    if file_type == FILE_TYPE_GROUP_ADMINISTRATION:
        groups_list = []
        for group, values in groups.items():
            if 'campaign' in values and values['campaign'] != '':
                groups_list.append(values['group_name'] + ' (' + values['campaign'] + ')')
            else:
                groups_list.append(values['group_name'])

        return groups_list
    else:
        return groups


def generate_group_heat_map(groups, campaigns, overlay, overlay_type, platform, overlay_software, include_software,
                            search_visibility, search_detection, health_is_called, output_filename, layer_name, domain,
                            layer_settings, include_all_score_objs, count_detections):
    """
    Calls all functions that are necessary for the generation of the heat map and write a json layer to disk.
    :param groups: threat actor groups
    :param campaigns: threat actor campaigns
    :param overlay: group(s), visibility or detections to overlay (group ID, group name/alias, YAML file with
    group(s), detections or visibility)
    :param overlay_type: group, visibility or detection
    :param platform: one or multiple ATT&CK platform values or None
    :param overlay_software: specify if techniques from related software should be overlayed (not included in scores)
    :param include_software: specify if techniques from related software should be included in the scores
    :param search_visibility: visibility EQL search query
    :param search_detection: detection EQL search query
    :param health_is_called: boolean that specifies if detailed errors in the file will be printed
    :param output_filename: output filename defined by the user
    :param layer_name: the name of the Navigator layer
    :param domain: the specified domain
    :param layer_settings: settings for the Navigator layer
    :param include_all_score_objs: include all score objects within the score_logbook for the EQL query
    :param count_detections: option for the Navigator layer output: count detections instead of listing detections
    :return: returns None when something went wrong
    """
    original_groups_argument = groups
    overlay_dict = {}
    groups_software_dict = {}
    include_software_dict = {}

    groups_file_type = None
    if groups is None:
        # Only set groups to all when no campaigns are specified:
        if campaigns is None:
            groups = ['all']
    elif os.path.isfile(groups[0]):
        groups = groups[0]
        groups_file_type = check_file(groups, file_type=FILE_TYPE_GROUP_ADMINISTRATION,
                                      health_is_called=health_is_called)
        if not groups_file_type:
            return None  # the groups_file_type is not of the type FILE_TYPE_GROUP_ADMINISTRATION
    elif isinstance(groups[0], str) and len(groups) == 1:
        # reached when when the CLI only contained one argument
        groups = list(map(lambda x: x.strip().lower(), groups[0].split(',')))
    else:  # reached when the groups are provided via CLI arguments
        groups = list(map(lambda x: x.strip().lower(), groups))

    if campaigns is None and original_groups_argument is None:
        # Only set campaigns to all when no groups are specified:
        campaigns = ['all']
    elif campaigns is not None and isinstance(campaigns[0], str) and len(campaigns) == 1:
        campaigns = list(map(lambda x: x.strip().lower(), campaigns[0].split(',')))
    elif campaigns is not None:
        campaigns = list(map(lambda x: x.strip().lower(), campaigns))

    # set the correct value for platform
    platform_yaml = None
    if groups_file_type == FILE_TYPE_GROUP_ADMINISTRATION:
        _yaml = init_yaml()
        with open(groups, 'r') as yaml_file:
            group_file = _yaml.load(yaml_file)

        domain_in_file = 'enterprise-attack' if 'domain' not in group_file.keys() else group_file['domain']
        domain_in_argument = 'enterprise-attack' if domain == 'enterprise' else 'ics-attack' if domain == 'ics' else 'mobile-attack' if domain == 'mobile' else None
        if (domain_in_argument and domain_in_file != domain_in_argument):
            print('[!] The domain specified in Group YAML file conflicts with the given value of the -d/--domain argument.')
            return None
        domain = domain_in_file
        platform_yaml = get_platform_from_yaml(group_file, domain)
    else:
        domain = 'mobile-attack' if domain == 'mobile' else 'ics-attack' if domain == 'ics' else 'enterprise-attack'  # if no domain is given, enterprise is default

    if platform == None and platform_yaml != None:
        platform = platform_yaml
    elif platform == None:  # 'all'
        platform = list(PLATFORMS_ENTERPRISE.values()) if domain == 'enterprise-attack' else list(PLATFORMS_ICS.values()
                                                                                                  if domain == 'ics-attack' else list(PLATFORMS_MOBILE.values()))
    elif 'all' in [p.lower() for p in platform if p is not None]:
        platform = list(PLATFORMS_ENTERPRISE.values()) if domain == 'enterprise-attack' else list(PLATFORMS_ICS.values()
                                                                                                  if domain == 'ics-attack' else list(PLATFORMS_MOBILE.values()))
    elif isinstance(platform, list):
        if not check_platform(platform, domain=domain):
            return None
        platform = get_platform_in_correct_capitalisation(platform, domain)

    overlay_file_type = None
    if overlay:
        if overlay_type in [OVERLAY_TYPE_DETECTION, OVERLAY_TYPE_VISIBILITY]:
            if os.path.isfile(overlay[0]):
                overlay = overlay[0]
                expected_file_type = FILE_TYPE_TECHNIQUE_ADMINISTRATION if overlay_type in [OVERLAY_TYPE_VISIBILITY, OVERLAY_TYPE_DETECTION] else None
                overlay_file_type = check_file(overlay, expected_file_type, health_is_called=health_is_called)
                if not overlay_file_type:
                    return None  # the overlay_file_type is not of the expected type
            else:
                print('[!] The given file does not exist: ' + overlay[0])
                return None
        elif overlay_type == OVERLAY_TYPE_GROUP and os.path.isfile(overlay[0]):
            overlay = overlay[0]
            expected_file_type = FILE_TYPE_GROUP_ADMINISTRATION
            overlay_file_type = check_file(overlay, expected_file_type, health_is_called=health_is_called)
            if not overlay_file_type:
                return None  # the overlay_file_type is not of the expected type
        else:  # reached when the groups/campaigns are provided via CLI arguments
            overlay = list(map(lambda x: x.strip().lower(), overlay))
    else:
        overlay = []

    # load the techniques (visibility or detection) from the YAML file
    all_techniques = None
    if overlay_file_type == FILE_TYPE_TECHNIQUE_ADMINISTRATION:
        # filter out visibility and/or detection objects using EQL
        if search_detection or search_visibility:
            overlay = techniques_search(overlay, search_visibility, search_detection,
                                        include_all_score_objs=include_all_score_objs)
            if not overlay:
                return None  # something went wrong in executing the search or 0 results where returned

        if overlay_type == OVERLAY_TYPE_VISIBILITY:
            overlay_dict, all_techniques, domain_overlay = _get_visibility_techniques(overlay)
            if domain_overlay != domain:
                print('[!] The domain specified in the overlay YAML file conflicts with the given value for the -d/--domain argument, or the domain specified in the Group YAML file.')
                return None
        elif overlay_type == OVERLAY_TYPE_DETECTION:
            overlay_dict, all_techniques, domain_overlay = _get_detection_techniques(overlay)
            if domain_overlay != domain:
                print('[!] The domain specified in the overlay YAML file conflicts with the given value for the -d/--domain argument, or the domain specified in the Group YAML file.')
                return None

    # we are not overlaying visibility or detection, overlay group will therefore contain information on another group
    elif len(overlay) > 0:
        if overlay_type == OVERLAY_TYPE_GROUP:
            overlay_dict = _get_group_techniques(overlay, platform, overlay_file_type, domain)
        elif overlay_type == OVERLAY_TYPE_CAMPAIGN:
            overlay_dict = _get_campaign_techniques(overlay, platform, domain)
        if overlay_dict == -1:
            return None  # returns None when the provided Group(s) to be overlaid, contains Groups not part of ATT&CK

    groups_dict = _get_group_techniques(groups, platform, groups_file_type, domain)
    campaigns_dict = _get_campaign_techniques(campaigns, platform, domain)

    if groups_dict == -1 or campaigns_dict == -1:
        return None  # return None when the provided Groups/Campaigns are not part of ATT&CK
    else:
        # Treat campaigns like groups, merge groups_dict with campaigns_dict:
        groups_dict |= campaigns_dict

    if len(groups_dict) == 0:
        print('[!] Empty layer.')  # the provided groups dit not result in any techniques
        return None

    # check if we are doing a software group overlay
    if overlay_software and overlay:
        # if a group or campaign overlay is provided, get the software techniques for the overlay
        if overlay_type == OVERLAY_TYPE_GROUP:
            groups_software_dict = _get_software_techniques(overlay, None, platform, domain)
        elif overlay_type == OVERLAY_TYPE_CAMPAIGN:
            groups_software_dict = _get_software_techniques(None, overlay, platform, domain)
    elif overlay_software:
        groups_software_dict = _get_software_techniques(groups, campaigns, platform, domain)

    if include_software:
        include_software_dict = _get_software_techniques(groups, campaigns, platform, domain)
        merge_group_dict(groups_dict, include_software_dict)

    technique_count, max_count = _get_technique_count(groups_dict, overlay_dict, groups_software_dict, overlay_type, all_techniques)
    technique_layer = _get_technique_layer(technique_count, groups_dict, overlay_dict, groups_software_dict,
                                           overlay_file_type, overlay_type, all_techniques, count_detections)

    # make a list group names for the involved groups.
    groups_list = []
    if groups == ['all']:
        groups_list.append('all_groups')
    if campaigns == ['all']:
        groups_list.append('all_campaigns')

    if groups != ['all'] and campaigns != ['all']:
        groups_list = _get_group_list(groups_dict, groups_file_type)
    overlay_list = _get_group_list(overlay_dict, overlay_file_type)

    desc = 'stage: attack | platform(s): ' + platform_to_name(platform, domain, separator=', ') + ' | group(s): ' \
        + ', '.join(groups_list) + ' | overlay group(s): ' + ', '.join(overlay_list)

    if not layer_name:
        layer_name = 'Attack - ' + platform_to_name(platform, domain, separator=', ')

    layer = get_layer_template_groups(layer_name, max_count, desc, platform, overlay_type, domain, layer_settings)
    layer['techniques'] = technique_layer

    json_string = simplejson.dumps(layer).replace('}, ', '},\n')

    if not output_filename:
        filename = '_'.join(groups_list)
        if overlay:
            filename += '-overlay_' + '_'.join(overlay_list)

        filename = create_output_filename('attack', filename)
        write_file(filename, json_string)
    else:
        write_file(output_filename, json_string)
